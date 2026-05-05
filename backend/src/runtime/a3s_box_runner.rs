use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashSet},
    env, fs,
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

const MAX_RETAINED_LOG_CHARS: usize = 12_000;
const SCANNER_MOUNT_PATH: &str = "/scan";
const DEFAULT_A3S_BOX_BIN: &str = "a3s-box";
const DEFAULT_A3S_BOX_TIMEOUT_SECONDS: u64 = 900;
const DEFAULT_A3S_BOX_RUNNER_ROOT: &str = "/tmp/argus/a3s-box-runs";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct A3sBoxRunnerSpec {
    pub scanner_type: String,
    pub image: String,
    pub workspace_dir: String,
    pub command: Vec<String>,
    pub timeout_seconds: u64,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    #[serde(default = "default_expected_exit_codes")]
    pub expected_exit_codes: Vec<i32>,
    #[serde(default)]
    pub capture_stdout_path: Option<String>,
    #[serde(default)]
    pub capture_stderr_path: Option<String>,
    #[serde(default)]
    pub memory_limit_mb: Option<u64>,
    #[serde(default)]
    pub cpu_limit: Option<f64>,
    #[serde(default)]
    pub pids_limit: Option<u64>,
    #[serde(default)]
    pub network_disabled: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct A3sBoxRunnerResult {
    pub success: bool,
    pub box_name: Option<String>,
    pub exit_code: i32,
    pub stdout_path: Option<String>,
    pub stderr_path: Option<String>,
    pub error: Option<String>,
}

fn default_expected_exit_codes() -> Vec<i32> {
    vec![0]
}

struct CommandCapture {
    timed_out: bool,
    status_code: Option<i32>,
    stdout: String,
    stderr: String,
}

struct RunnerMetaContext<'a> {
    runner_command: &'a [String],
    runner_environment: &'a BTreeMap<String, String>,
    result: &'a A3sBoxRunnerResult,
    log_retention: &'a str,
}

fn a3s_box_bin() -> String {
    env::var("A3S_BOX_BIN")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| DEFAULT_A3S_BOX_BIN.to_string())
}

fn a3s_box_runner_root() -> PathBuf {
    env::var("A3S_BOX_RUNNER_ROOT")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_A3S_BOX_RUNNER_ROOT))
}

fn a3s_box_cleanup_timeout() -> u64 {
    env::var("A3S_BOX_CLEANUP_TIMEOUT_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(30)
}

fn ensure_workspace_artifacts(workspace_dir: &str) -> Result<(PathBuf, PathBuf, PathBuf)> {
    let workspace = PathBuf::from(workspace_dir);
    let logs_dir = workspace.join("logs");
    let meta_dir = workspace.join("meta");
    fs::create_dir_all(&logs_dir)
        .with_context(|| format!("create logs dir: {}", logs_dir.display()))?;
    fs::create_dir_all(&meta_dir)
        .with_context(|| format!("create meta dir: {}", meta_dir.display()))?;
    Ok((workspace, logs_dir, meta_dir))
}

fn truncate_log_text(text: &str) -> String {
    if text.len() <= MAX_RETAINED_LOG_CHARS {
        return text.to_string();
    }
    let tail_chars = MAX_RETAINED_LOG_CHARS.saturating_sub(64);
    let omitted_chars = text.len().saturating_sub(tail_chars);
    format!(
        "[truncated {omitted_chars} chars]\n{}",
        &text[text.len() - tail_chars..]
    )
}

fn write_retained_log(path: &Path, text: &str) -> Result<Option<String>> {
    let content = truncate_log_text(text);
    if content.trim().is_empty() {
        return Ok(None);
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create retained log parent: {}", parent.display()))?;
    }
    fs::write(path, content).with_context(|| format!("write retained log: {}", path.display()))?;
    Ok(Some(path.display().to_string()))
}

fn write_full_text(path: &Path, text: &str) -> Result<String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create output parent: {}", parent.display()))?;
    }
    fs::write(path, text).with_context(|| format!("write output file: {}", path.display()))?;
    Ok(path.display().to_string())
}

fn format_memory_limit_mb(limit_mb: u64) -> String {
    format!("{limit_mb}m")
}

fn format_cpu_limit(limit: f64) -> String {
    if !limit.is_finite() || limit <= 0.0 {
        return "1".to_string();
    }
    limit.ceil().to_string()
}

fn run_command_capture(
    binary: &str,
    args: &[String],
    timeout: Option<Duration>,
) -> Result<CommandCapture> {
    let mut child = Command::new(binary)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("run a3s-box command: {}", args.join(" ")))?;

    let stdout = child.stdout.take().context("capture a3s-box stdout")?;
    let stderr = child.stderr.take().context("capture a3s-box stderr")?;

    let stdout_handle = thread::spawn(move || -> Result<Vec<u8>> {
        let mut reader = stdout;
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .context("read a3s-box stdout")?;
        Ok(bytes)
    });
    let stderr_handle = thread::spawn(move || -> Result<Vec<u8>> {
        let mut reader = stderr;
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .context("read a3s-box stderr")?;
        Ok(bytes)
    });

    let started_at = Instant::now();
    let mut timed_out = false;
    let exit_status = loop {
        if let Some(status) = child.try_wait().context("poll a3s-box child status")? {
            break Some(status);
        }
        if timeout.is_some_and(|limit| started_at.elapsed() >= limit) {
            timed_out = true;
            let _ = child.kill();
            break child.wait().ok();
        }
        thread::sleep(Duration::from_millis(50));
    };

    let stdout = String::from_utf8_lossy(
        &stdout_handle
            .join()
            .map_err(|_| anyhow::anyhow!("join a3s-box stdout reader"))??,
    )
    .to_string();
    let stderr = String::from_utf8_lossy(
        &stderr_handle
            .join()
            .map_err(|_| anyhow::anyhow!("join a3s-box stderr reader"))??,
    )
    .to_string();

    Ok(CommandCapture {
        timed_out,
        status_code: exit_status.and_then(|status| status.code()),
        stdout,
        stderr,
    })
}

fn rewrite_mount_path(value: &str, workspace: &Path) -> String {
    if value == SCANNER_MOUNT_PATH {
        return workspace.display().to_string();
    }
    if let Some(rest) = value.strip_prefix(&(SCANNER_MOUNT_PATH.to_string() + "/")) {
        return workspace.join(rest).display().to_string();
    }
    value.to_string()
}

fn rewrite_runner_command(command: &[String], workspace: &Path) -> Vec<String> {
    command
        .iter()
        .map(|value| rewrite_mount_path(value, workspace))
        .collect()
}

fn rewrite_runner_env(
    env_map: &BTreeMap<String, String>,
    workspace: &Path,
) -> BTreeMap<String, String> {
    env_map
        .iter()
        .map(|(key, value)| (key.clone(), rewrite_mount_path(value, workspace)))
        .collect()
}

fn write_runner_meta(
    runner_meta_path: &Path,
    spec: &A3sBoxRunnerSpec,
    context: &RunnerMetaContext<'_>,
) -> Result<()> {
    let payload = serde_json::json!({
        "spec": spec,
        "runner_command": context.runner_command,
        "runner_environment": context.runner_environment,
        "box_name": context.result.box_name,
        "exit_code": context.result.exit_code,
        "success": context.result.success,
        "stdout_path": context.result.stdout_path,
        "stderr_path": context.result.stderr_path,
        "error": context.result.error,
        "log_retention": context.log_retention,
    });
    fs::write(
        runner_meta_path,
        serde_json::to_string_pretty(&payload).context("serialize a3s-box runner meta")?,
    )
    .with_context(|| format!("write a3s-box runner meta: {}", runner_meta_path.display()))
}

fn cleanup_box(binary: &str, box_name: Option<&str>) {
    let Some(box_name) = box_name else {
        return;
    };
    let _ = run_command_capture(
        binary,
        &[
            "rm".to_string(),
            "--force".to_string(),
            box_name.to_string(),
        ],
        Some(Duration::from_secs(a3s_box_cleanup_timeout())),
    );
}

pub fn stop_box_sync(box_name: &str) -> bool {
    let binary = a3s_box_bin();
    let output = run_command_capture(
        &binary,
        &[
            "rm".to_string(),
            "--force".to_string(),
            box_name.to_string(),
        ],
        Some(Duration::from_secs(a3s_box_cleanup_timeout())),
    );
    matches!(output, Ok(capture) if capture.status_code == Some(0))
}

pub fn execute(spec: A3sBoxRunnerSpec) -> A3sBoxRunnerResult {
    let (workspace, logs_dir, meta_dir) = match ensure_workspace_artifacts(&spec.workspace_dir) {
        Ok(value) => value,
        Err(err) => {
            return A3sBoxRunnerResult {
                success: false,
                box_name: None,
                exit_code: 1,
                stdout_path: None,
                stderr_path: None,
                error: Some(err.to_string()),
            };
        }
    };

    let stdout_log_path = logs_dir.join("a3s-box-stdout.log");
    let stderr_log_path = logs_dir.join("a3s-box-stderr.log");
    let runner_meta_path = meta_dir.join("a3s-box-runner.json");
    let binary = a3s_box_bin();
    let expected_exit_codes = spec
        .expected_exit_codes
        .iter()
        .copied()
        .collect::<HashSet<_>>();
    let box_name = format!("argus-{}-{}", spec.scanner_type, Uuid::new_v4());
    let mut runner_command = spec.command.clone();
    let mut runner_environment = spec.env.clone();
    let mut active_box_name = None;

    let execution = (|| -> Result<A3sBoxRunnerResult> {
        let resolved_workspace = workspace
            .canonicalize()
            .with_context(|| format!("canonicalize workspace_dir: {}", workspace.display()))?;
        if spec.network_disabled {
            bail!("a3s-box CLI does not support network_disabled yet; refusing to start without a verified no-network mode");
        }
        runner_command = rewrite_runner_command(&spec.command, &resolved_workspace);
        runner_environment = rewrite_runner_env(&spec.env, &resolved_workspace);

        let mut args = vec![
            "run".to_string(),
            "--rm".to_string(),
            "--name".to_string(),
            box_name.clone(),
            "--volume".to_string(),
            format!(
                "{}:{}:rw",
                resolved_workspace.display(),
                resolved_workspace.display()
            ),
            "--workdir".to_string(),
            resolved_workspace.display().to_string(),
        ];
        if let Some(limit_mb) = spec.memory_limit_mb {
            args.push("--memory".to_string());
            args.push(format_memory_limit_mb(limit_mb));
        }
        if let Some(limit) = spec.cpu_limit {
            args.push("--cpus".to_string());
            args.push(format_cpu_limit(limit));
        }
        if let Some(limit) = spec.pids_limit {
            args.push("--pids-limit".to_string());
            args.push(limit.to_string());
        }
        for (key, value) in &runner_environment {
            args.push("--env".to_string());
            args.push(format!("{key}={value}"));
        }
        args.push(spec.image.clone());
        args.push("--".to_string());
        args.extend(runner_command.clone());

        let timeout = if spec.timeout_seconds == 0 {
            Some(Duration::from_secs(DEFAULT_A3S_BOX_TIMEOUT_SECONDS))
        } else {
            Some(Duration::from_secs(spec.timeout_seconds))
        };
        active_box_name = Some(box_name.clone());
        let capture = run_command_capture(&binary, &args, timeout)?;
        if capture.timed_out {
            cleanup_box(&binary, active_box_name.as_deref());
            bail!(
                "a3s-box run timed out after {}s",
                timeout
                    .map(|d| d.as_secs())
                    .unwrap_or(DEFAULT_A3S_BOX_TIMEOUT_SECONDS)
            );
        }
        let exit_code = capture.status_code.unwrap_or(1);
        let success = expected_exit_codes.contains(&exit_code);

        let should_capture_stdout = spec.capture_stdout_path.is_some() || !success;
        let should_capture_stderr = spec.capture_stderr_path.is_some() || !success;
        let captured_stdout_path = if should_capture_stdout {
            spec.capture_stdout_path
                .as_ref()
                .map(|relative| write_full_text(&workspace.join(relative), &capture.stdout))
                .transpose()?
                .or(write_retained_log(&stdout_log_path, &capture.stdout)?)
        } else {
            None
        };
        let captured_stderr_path = if should_capture_stderr {
            spec.capture_stderr_path
                .as_ref()
                .map(|relative| write_full_text(&workspace.join(relative), &capture.stderr))
                .transpose()?
                .or(write_retained_log(&stderr_log_path, &capture.stderr)?)
        } else {
            None
        };

        active_box_name = None;
        Ok(A3sBoxRunnerResult {
            success,
            box_name: Some(box_name.clone()),
            exit_code,
            stdout_path: captured_stdout_path,
            stderr_path: captured_stderr_path,
            error: if success {
                None
            } else {
                Some(format!("a3s-box workload exited with code {exit_code}"))
            },
        })
    })();

    let (result, log_retention) = match execution {
        Ok(result) => {
            let log_retention = if result.success && result.exit_code != 0 {
                "accepted_nonzero_exit"
            } else if result.success {
                "captured"
            } else {
                "failure_retained"
            };
            (result, log_retention.to_string())
        }
        Err(err) => {
            let stderr_path = write_retained_log(&stderr_log_path, &err.to_string())
                .ok()
                .flatten();
            (
                A3sBoxRunnerResult {
                    success: false,
                    box_name: Some(box_name.clone()),
                    exit_code: 1,
                    stdout_path: None,
                    stderr_path,
                    error: Some(err.to_string()),
                },
                "failure_only".to_string(),
            )
        }
    };

    cleanup_box(&binary, active_box_name.as_deref());
    let meta_context = RunnerMetaContext {
        runner_command: &runner_command,
        runner_environment: &runner_environment,
        result: &result,
        log_retention: &log_retention,
    };
    let _ = write_runner_meta(&runner_meta_path, &spec, &meta_context);
    result
}

pub fn default_runner_root() -> PathBuf {
    a3s_box_runner_root()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{os::unix::fs::PermissionsExt, sync::Mutex};
    use tempfile::TempDir;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    struct EnvVarGuard {
        key: String,
        original: Option<String>,
    }

    impl EnvVarGuard {
        fn set(key: &str, value: &str) -> Self {
            let original = env::var(key).ok();
            env::set_var(key, value);
            Self {
                key: key.to_string(),
                original,
            }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            if let Some(original) = &self.original {
                env::set_var(&self.key, original);
            } else {
                env::remove_var(&self.key);
            }
        }
    }

    fn fake_a3s_box_script(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-a3s-box.sh");
        let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_A3S_BOX_LOG:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  run)
    printf '%s' "${FAKE_A3S_BOX_STDOUT:-}"
    printf '%s' "${FAKE_A3S_BOX_STDERR:-}" >&2
    exit "${FAKE_A3S_BOX_EXIT_CODE:-0}"
    ;;
  rm)
    printf 'removed\n'
    ;;
esac
"#;
        fs::write(&script_path, script).expect("write fake a3s-box script");
        let mut permissions = fs::metadata(&script_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).unwrap();
        script_path
    }

    #[test]
    fn execute_runs_a3s_box_with_workspace_mount_env_and_capture_paths() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let fake_a3s_box = fake_a3s_box_script(&temp_dir);
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());
        let _stdout = EnvVarGuard::set("FAKE_A3S_BOX_STDOUT", "scan ok\n");
        let _stderr = EnvVarGuard::set("FAKE_A3S_BOX_STDERR", "warn\n");

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "opengrep-scan".to_string(),
                "--target".to_string(),
                "/scan/source".to_string(),
            ],
            timeout_seconds: 60,
            env: BTreeMap::from([("RULE_ROOT".to_string(), "/scan/rules".to_string())]),
            expected_exit_codes: vec![0, 1],
            capture_stdout_path: Some("output/stdout.txt".to_string()),
            capture_stderr_path: Some("output/stderr.txt".to_string()),
            memory_limit_mb: Some(2048),
            cpu_limit: Some(2.0),
            pids_limit: Some(512),
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 0);
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/stdout.txt")).unwrap(),
            "scan ok\n"
        );
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/stderr.txt")).unwrap(),
            "warn\n"
        );
        let logged = fs::read_to_string(fake_log).unwrap();
        assert!(logged.contains("run|"));
        assert!(logged.contains("--rm --name argus-opengrep-"));
        assert!(logged.contains(&format!(
            "--volume {}:{}:rw",
            workspace_dir.display(),
            workspace_dir.display()
        )));
        assert!(logged.contains(&format!("--workdir {}", workspace_dir.display())));
        assert!(logged.contains("--memory 2048m"));
        assert!(logged.contains("--cpus 2"));
        assert!(logged.contains("--pids-limit 512"));
        assert!(!logged.contains("--network none"));
        assert!(logged.contains(&format!(
            "--env RULE_ROOT={}/rules",
            workspace_dir.display()
        )));
        assert!(logged.contains(&format!("--target {}/source", workspace_dir.display())));
        assert!(workspace_dir.join("meta/a3s-box-runner.json").exists());
    }

    #[test]
    fn execute_accepts_nonzero_expected_exit_code() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let fake_a3s_box = fake_a3s_box_script(&temp_dir);
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());
        let _exit = EnvVarGuard::set("FAKE_A3S_BOX_EXIT_CODE", "1");

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["true".to_string()],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            capture_stdout_path: None,
            capture_stderr_path: None,
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 1);
    }

    #[test]
    fn execute_rejects_unsupported_network_disabled_mode() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let fake_a3s_box = fake_a3s_box_script(&temp_dir);
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["true".to_string()],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            capture_stdout_path: None,
            capture_stderr_path: None,
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: true,
        });

        assert!(!result.success);
        assert!(result
            .error
            .as_deref()
            .unwrap_or_default()
            .contains("network_disabled"));
        assert!(!fake_log.exists(), "a3s-box must not start after rejection");
    }

    #[test]
    fn cpu_limit_is_rounded_up_for_a3s_cli_integer_cpus() {
        assert_eq!(format_cpu_limit(3.5), "4");
        assert_eq!(format_cpu_limit(2.0), "2");
        assert_eq!(format_cpu_limit(0.0), "1");
    }
}
