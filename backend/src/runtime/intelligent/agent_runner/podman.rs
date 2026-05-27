use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use std::process::Stdio;
use tokio::process::Command;
use tokio::time::{timeout, Duration};
use tracing::warn;
use uuid::Uuid;

use super::llm_runner::ToolExecutor;
use super::ToolResult;

const MAX_OUTPUT_BYTES: usize = 100 * 1024;

pub struct PodmanSession {
    pub container_id: String,
    pub workspace_path: String,
    pub default_exec_timeout_ms: u64,
    archive_path: String,
    image: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CodegraphSourceMountMode {
    /// Use rootless Podman's keep-id mapping so the non-root auditor user can
    /// write `.codegraph/` into the extracted staging copy and the index dir.
    KeepIdWritable,
    /// Fallback for nested/backend-container deployments where the caller is not
    /// in a user namespace that can be preserved with keep-id.
    RootWritable,
}

impl PodmanSession {
    pub async fn create(archive_path: &str, image: &str) -> Result<Self> {
        let vol = format!("{archive_path}:/workspace:ro");
        let output = Command::new("podman")
            .args([
                "run",
                "-d",
                "--rm",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,size=512m",
                "-v",
                &vol,
                image,
                "sleep",
                "infinity",
            ])
            .output()
            .await
            .context("podman run failed")?;

        if !output.status.success() {
            bail!("podman run: {}", String::from_utf8_lossy(&output.stderr));
        }

        let container_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if container_id.is_empty() {
            bail!("podman run returned empty container ID");
        }

        let session = Self {
            container_id,
            workspace_path: "/workspace".to_string(),
            default_exec_timeout_ms: 30_000,
            archive_path: archive_path.to_string(),
            image: image.to_string(),
        };

        let running = session
            .health_check()
            .await
            .context("health check failed")?;
        if !running {
            bail!("container not running after create");
        }
        Ok(session)
    }

    pub async fn health_check(&self) -> Result<bool> {
        let output = Command::new("podman")
            .args([
                "inspect",
                "--format",
                "{{.State.Running}}",
                &self.container_id,
            ])
            .output()
            .await
            .context("podman inspect failed")?;
        let s = String::from_utf8_lossy(&output.stdout).trim().to_string();
        Ok(s == "true")
    }

    pub async fn exec_command(&self, cmd: &str, timeout_ms: u64) -> Result<(String, String, i32)> {
        let fut = Command::new("podman")
            .args(["exec", &self.container_id, "sh", "-c", cmd])
            .output();
        let output = timeout(Duration::from_millis(timeout_ms), fut)
            .await
            .context("exec timed out")?
            .context("podman exec failed")?;
        let stdout = truncate(String::from_utf8_lossy(&output.stdout).into_owned());
        let stderr = truncate(String::from_utf8_lossy(&output.stderr).into_owned());
        let code = output.status.code().unwrap_or(-1);
        Ok((stdout, stderr, code))
    }

    pub async fn destroy(&self) -> Result<()> {
        Command::new("podman")
            .args(["rm", "-f", "-t", "0", &self.container_id])
            .output()
            .await
            .context("podman rm failed")?;
        Ok(())
    }

    pub async fn restart(&mut self) -> Result<()> {
        let _ = self.destroy().await;
        let new = PodmanSession::create(&self.archive_path, &self.image).await?;
        self.container_id = new.container_id.clone();
        Ok(())
    }

    /// Create a PodmanSession variant for codegraph indexing/querying.
    ///
    /// Differs from `create()` in three ways:
    ///   1. Source is a host-extracted staging copy bind-mounted at
    ///      `/codegraph/src:rw` (NOT a raw archive file at `/workspace`)
    ///   2. A writable index directory is bind-mounted at `/codegraph/index:rw` so
    ///      `codegraph init` can write the SQLite database
    ///   3. A read-only cache directory at `/codegraph/cache_in:ro` lets the client
    ///      check for an existing cached index before re-indexing
    ///
    /// Tmpfs raised to 1GB (vs 512MB default) — codegraph uses /tmp for SQLite WAL.
    /// Prefers auditor (uid 1000) plus `--userns keep-id` so rootless Podman
    /// bind mounts remain writable; retries as container root when keep-id is
    /// unavailable in nested deployments.
    ///
    /// See `.omc/plans/ralplan-codegraph-integration-v2.md` §Step 2.2.
    pub async fn create_for_codegraph(
        staging_dir: &str,
        index_dir: &str,
        cache_dir: &str,
        image: &str,
    ) -> Result<Self> {
        let first = run_codegraph_container(
            CodegraphSourceMountMode::KeepIdWritable,
            staging_dir,
            index_dir,
            cache_dir,
            image,
        )
        .await?;
        let output = if first.status.success() {
            first
        } else {
            let stderr = String::from_utf8_lossy(&first.stderr);
            if should_retry_codegraph_without_keep_id(&stderr) {
                warn!(
                    stderr = %truncate(stderr.into_owned()),
                    "codegraph podman keep-id create failed; retrying rootful-in-container fallback"
                );
                run_codegraph_container(
                    CodegraphSourceMountMode::RootWritable,
                    staging_dir,
                    index_dir,
                    cache_dir,
                    image,
                )
                .await?
            } else {
                first
            }
        };

        if !output.status.success() {
            bail!(
                "podman run (codegraph variant): {}",
                String::from_utf8_lossy(&output.stderr)
            );
        }

        let container_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if container_id.is_empty() {
            bail!("podman run (codegraph variant) returned empty container ID");
        }

        let session = Self {
            container_id,
            workspace_path: "/codegraph/src".to_string(),
            default_exec_timeout_ms: 60_000,
            // archive_path is reused as staging_dir for symmetry with restart()
            // (not currently called for codegraph sessions but kept consistent).
            archive_path: staging_dir.to_string(),
            image: image.to_string(),
        };

        let running = session
            .health_check()
            .await
            .context("codegraph container health check failed")?;
        if !running {
            bail!("codegraph container not running after create");
        }
        Ok(session)
    }
}

async fn run_codegraph_container(
    mode: CodegraphSourceMountMode,
    staging_dir: &str,
    index_dir: &str,
    cache_dir: &str,
    image: &str,
) -> Result<std::process::Output> {
    let vol_src = format!("{staging_dir}:/codegraph/src:rw");
    let vol_index = format!("{index_dir}:/codegraph/index:rw");
    let vol_cache = format!("{cache_dir}:/codegraph/cache_in:ro");
    let mut command = Command::new("podman");
    command.args(["run", "-d", "--rm"]);
    if mode == CodegraphSourceMountMode::KeepIdWritable {
        command.args(["--userns", "keep-id", "--user", "1000"]);
    } else {
        command.args(["--user", "0"]);
    }
    command
        .args([
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=1g",
            "--label",
            "argus-codegraph=true",
            "-v",
            &vol_src,
            "-v",
            &vol_index,
            "-v",
            &vol_cache,
            image,
            "sleep",
            "infinity",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .context("podman run (codegraph variant) failed")
}

fn should_retry_codegraph_without_keep_id(stderr: &str) -> bool {
    let stderr = stderr.to_ascii_lowercase();
    stderr.contains("keep-id")
        || stderr.contains("user namespace")
        || stderr.contains("cannot set uid")
        || stderr.contains("cannot setgid")
        || stderr.contains("not enough ids")
        || stderr.contains("invalid internal status")
}

fn truncate(mut s: String) -> String {
    if s.len() > MAX_OUTPUT_BYTES {
        s.truncate(MAX_OUTPUT_BYTES);
        s.push_str("\n... [truncated]");
    }
    s
}

/// Single-quote escape for shell arguments passed via `sh -c`.
fn sh_quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

fn validate_path(path: &str) -> Result<()> {
    if path.contains("..") {
        bail!("path traversal not allowed: {path}");
    }
    if path.starts_with('/') {
        bail!("absolute paths not allowed: {path}");
    }
    Ok(())
}

fn generate_id() -> String {
    Uuid::new_v4().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, os::unix::fs::PermissionsExt, sync::Mutex};

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    struct PathGuard {
        previous: Option<String>,
    }

    impl PathGuard {
        fn prepend(path: &std::path::Path) -> Self {
            let previous = std::env::var("PATH").ok();
            let next = match previous.as_deref() {
                Some(existing) if !existing.is_empty() => format!("{}:{existing}", path.display()),
                _ => path.display().to_string(),
            };
            std::env::set_var("PATH", next);
            Self { previous }
        }
    }

    impl Drop for PathGuard {
        fn drop(&mut self) {
            if let Some(previous) = &self.previous {
                std::env::set_var("PATH", previous);
            } else {
                std::env::remove_var("PATH");
            }
        }
    }

    fn make_executable(path: &std::path::Path) {
        let mut perms = fs::metadata(path).expect("metadata").permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path, perms).expect("chmod");
    }

    #[tokio::test]
    async fn create_for_codegraph_uses_keep_id_and_writable_source_mounts() {
        let _lock = ENV_LOCK.lock().expect("env lock");
        let temp = tempfile::tempdir().expect("tempdir");
        let bin = temp.path().join("bin");
        fs::create_dir_all(&bin).expect("mkdir bin");
        let log = temp.path().join("podman.log");
        let script = bin.join("podman");
        fs::write(
            &script,
            format!(
                r#"#!/usr/bin/env sh
printf '%s
' "$*" >> {log}
case "$1" in
  run) printf 'fake-codegraph-container
' ;;
  inspect) printf 'true
' ;;
  rm) exit 0 ;;
esac
"#,
                log = sh_quote(log.to_str().unwrap())
            ),
        )
        .expect("write fake podman");
        make_executable(&script);
        let _path = PathGuard::prepend(&bin);

        let session = PodmanSession::create_for_codegraph(
            "/host/staging",
            "/host/index",
            "/host/cache",
            "argus/audit-sandbox:test",
        )
        .await
        .expect("create codegraph session");
        assert_eq!(session.container_id, "fake-codegraph-container");

        let logged = fs::read_to_string(log).expect("read log");
        assert!(logged.contains("--userns keep-id"), "{logged}");
        assert!(logged.contains("--user 1000"), "{logged}");
        assert!(
            logged.contains("/host/staging:/codegraph/src:rw"),
            "{logged}"
        );
        assert!(
            logged.contains("/host/index:/codegraph/index:rw"),
            "{logged}"
        );
        assert!(
            logged.contains("/host/cache:/codegraph/cache_in:ro"),
            "{logged}"
        );
    }
}

impl Drop for PodmanSession {
    fn drop(&mut self) {
        let id = self.container_id.clone();
        // Fire-and-forget synchronous spawn — does not depend on a live tokio
        // runtime. The child process detaches and podman cleans up the container
        // even if this process is shutting down.
        let _ = std::process::Command::new("podman")
            .args(["rm", "-f", "-t", "0", &id])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn();
    }
}

#[async_trait]
impl ToolExecutor for PodmanSession {
    async fn execute(&self, tool_name: &str, input: serde_json::Value) -> ToolResult {
        let id = generate_id();
        match self.run_tool(tool_name, &input).await {
            Ok(output) => ToolResult {
                tool_use_id: id,
                content: output,
                is_error: false,
            },
            Err(e) => ToolResult {
                tool_use_id: id,
                content: e.to_string(),
                is_error: true,
            },
        }
    }
}

impl PodmanSession {
    async fn run_tool(&self, tool_name: &str, input: &serde_json::Value) -> Result<String> {
        match tool_name {
            "read_file" => {
                let path = input["path"].as_str().context("missing path")?;
                validate_path(path)?;
                let cmd = format!("cat /workspace/{}", sh_quote(path));
                let (stdout, stderr, code) = self
                    .exec_command(&cmd, self.default_exec_timeout_ms)
                    .await?;
                if code != 0 {
                    bail!("{stderr}");
                }
                Ok(stdout)
            }
            "grep" => {
                let pattern = input["pattern"].as_str().context("missing pattern")?;
                let scope = match input["path"].as_str() {
                    Some(p) => {
                        validate_path(p)?;
                        format!("/workspace/{p}")
                    }
                    None => "/workspace".to_string(),
                };
                let cmd = format!("grep -rn {} {}", sh_quote(pattern), sh_quote(&scope));
                let (stdout, _stderr, _code) = self
                    .exec_command(&cmd, self.default_exec_timeout_ms)
                    .await?;
                Ok(stdout)
            }
            "glob" => {
                let pattern = input["pattern"].as_str().context("missing pattern")?;
                // Use find -path for patterns with /, else -name
                let cmd = if pattern.contains('/') {
                    format!(
                        "find /workspace -path {}",
                        sh_quote(&format!("/workspace/{pattern}"))
                    )
                } else {
                    format!("find /workspace -name {}", sh_quote(pattern))
                };
                let (stdout, _stderr, _code) = self
                    .exec_command(&cmd, self.default_exec_timeout_ms)
                    .await?;
                Ok(stdout)
            }
            "exec" => {
                let command = input["command"].as_str().context("missing command")?;
                let timeout_ms = input["timeout_ms"]
                    .as_u64()
                    .unwrap_or(self.default_exec_timeout_ms);
                match self.exec_command(command, timeout_ms).await {
                    Ok((stdout, stderr, code)) => {
                        if code != 0 {
                            bail!("exit {code}\n{stderr}");
                        }
                        Ok(stdout)
                    }
                    Err(e) if e.to_string().contains("timed out") => {
                        bail!("Command timed out");
                    }
                    Err(e) => {
                        warn!("exec failed, checking container health");
                        match self.health_check().await {
                            Ok(false) | Err(_) => bail!("container dead: {e}"),
                            Ok(true) => bail!("{e}"),
                        }
                    }
                }
            }
            other => bail!("unknown tool: {other}"),
        }
    }
}
