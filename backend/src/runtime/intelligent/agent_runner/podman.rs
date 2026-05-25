use anyhow::{bail, Context, Result};
use async_trait::async_trait;
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

impl PodmanSession {
    pub async fn create(archive_path: &str, image: &str) -> Result<Self> {
        let vol = format!("{}:/workspace:ro", archive_path);
        let output = Command::new("podman")
            .args([
                "run", "-d", "--rm", "--read-only",
                "--tmpfs", "/tmp:rw,size=512m",
                "-v", &vol,
                image, "sleep", "infinity",
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

        let running = session.health_check().await.context("health check failed")?;
        if !running {
            bail!("container not running after create");
        }
        Ok(session)
    }

    pub async fn health_check(&self) -> Result<bool> {
        let output = Command::new("podman")
            .args(["inspect", "--format", "{{.State.Running}}", &self.container_id])
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
            .args(["rm", "-f", &self.container_id])
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
    ///   1. Source is a host-extracted directory bind-mounted at `/codegraph/src:ro`
    ///      (NOT a raw archive file at `/workspace`)
    ///   2. A writable index directory is bind-mounted at `/codegraph/index:rw` so
    ///      `codegraph init` can write the SQLite database
    ///   3. A read-only cache directory at `/codegraph/cache_in:ro` lets the client
    ///      check for an existing cached index before re-indexing
    ///
    /// Tmpfs raised to 1GB (vs 512MB default) — codegraph uses /tmp for SQLite WAL.
    /// Runs as auditor (uid 1000), matches existing image user.
    ///
    /// See `.omc/plans/ralplan-codegraph-integration-v2.md` §Step 2.2.
    pub async fn create_for_codegraph(
        staging_dir: &str,
        index_dir: &str,
        cache_dir: &str,
        image: &str,
    ) -> Result<Self> {
        let vol_src = format!("{staging_dir}:/codegraph/src:ro");
        let vol_index = format!("{index_dir}:/codegraph/index:rw");
        let vol_cache = format!("{cache_dir}:/codegraph/cache_in:ro");
        let output = Command::new("podman")
            .args([
                "run", "-d", "--rm",
                "--read-only",
                "--tmpfs", "/tmp:rw,size=1g",
                "--user", "1000",
                "--label", "argus-codegraph=true",
                "-v", &vol_src,
                "-v", &vol_index,
                "-v", &vol_cache,
                image, "sleep", "infinity",
            ])
            .output()
            .await
            .context("podman run (codegraph variant) failed")?;

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

impl Drop for PodmanSession {
    fn drop(&mut self) {
        let id = self.container_id.clone();
        tokio::spawn(async move {
            let _ = Command::new("podman").args(["rm", "-f", &id]).output().await;
        });
    }
}

#[async_trait]
impl ToolExecutor for PodmanSession {
    async fn execute(&self, tool_name: &str, input: serde_json::Value) -> ToolResult {
        let id = generate_id();
        match self.run_tool(tool_name, &input).await {
            Ok(output) => ToolResult { tool_use_id: id, content: output, is_error: false },
            Err(e) => ToolResult { tool_use_id: id, content: e.to_string(), is_error: true },
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
                let (stdout, stderr, code) =
                    self.exec_command(&cmd, self.default_exec_timeout_ms).await?;
                if code != 0 {
                    bail!("{}", stderr);
                }
                Ok(stdout)
            }
            "grep" => {
                let pattern = input["pattern"].as_str().context("missing pattern")?;
                let scope = match input["path"].as_str() {
                    Some(p) => {
                        validate_path(p)?;
                        format!("/workspace/{}", p)
                    }
                    None => "/workspace".to_string(),
                };
                let cmd = format!("grep -rn {} {}", sh_quote(pattern), sh_quote(&scope));
                let (stdout, _stderr, _code) =
                    self.exec_command(&cmd, self.default_exec_timeout_ms).await?;
                Ok(stdout)
            }
            "glob" => {
                let pattern = input["pattern"].as_str().context("missing pattern")?;
                // Use find -path for patterns with /, else -name
                let cmd = if pattern.contains('/') {
                    format!("find /workspace -path {}", sh_quote(&format!("/workspace/{}", pattern)))
                } else {
                    format!("find /workspace -name {}", sh_quote(pattern))
                };
                let (stdout, _stderr, _code) =
                    self.exec_command(&cmd, self.default_exec_timeout_ms).await?;
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
