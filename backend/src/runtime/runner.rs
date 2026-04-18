use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    env, fs,
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

pub const SCANNER_MOUNT_PATH: &str = "/scan";
const MAX_RETAINED_LOG_CHARS: usize = 12_000;
const DOCKER_STOP_TIMEOUT_SECONDS: u64 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RunnerSpec {
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
    pub artifact_paths: Vec<String>,
    pub capture_stdout_path: Option<String>,
    pub capture_stderr_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RunnerResult {
    pub success: bool,
    pub container_id: Option<String>,
    pub exit_code: i32,
    pub stdout_path: Option<String>,
    pub stderr_path: Option<String>,
    pub error: Option<String>,
}

fn default_expected_exit_codes() -> Vec<i32> {
    vec![0]
}

pub fn execute_from_spec_path(spec_path: &Path) -> RunnerResult {
    match fs::read_to_string(spec_path)
        .with_context(|| format!("read spec {}", spec_path.display()))
        .and_then(|raw| serde_json::from_str::<RunnerSpec>(&raw).context("parse runner spec"))
    {
        Ok(spec) => execute(spec),
        Err(error) => RunnerResult {
            success: false,
            container_id: None,
            exit_code: 1,
            stdout_path: None,
            stderr_path: None,
            error: Some(error.to_string()),
        },
    }
}

pub fn stop_container(container_id: &str) -> bool {
    let trimmed = container_id.trim();
    if trimmed.is_empty() {
        return false;
    }

    let inspect = docker_command(["inspect", trimmed]);
    let Ok(inspect_output) = inspect else {
        return false;
    };
    if !inspect_output.status.success() {
        return false;
    }

    let stop = docker_command(["stop", "-t", "2", trimmed]);
    let Ok(stop_output) = stop else {
        return false;
    };
    if !stop_output.status.success() {
        return false;
    }

    let remove = docker_command(["rm", "-f", trimmed]);
    matches!(remove, Ok(output) if output.status.success())
}

pub fn execute(spec: RunnerSpec) -> RunnerResult {
    let workspace = PathBuf::from(&spec.workspace_dir);
    let (logs_dir, meta_dir) = match ensure_workspace_artifacts(&workspace) {
        Ok(paths) => paths,
        Err(error) => {
            return RunnerResult {
                success: false,
                container_id: None,
                exit_code: 1,
                stdout_path: None,
                stderr_path: None,
                error: Some(error.to_string()),
            };
        }
    };

    let stdout_log_path = logs_dir.join("stdout.log");
    let stderr_log_path = logs_dir.join("stderr.log");
    let runner_meta_path = meta_dir.join("runner.json");
    let outcome = run_spec(&spec, &workspace, &stdout_log_path, &stderr_log_path);

    let result = match outcome {
        RunOutcome::Success(success) => {
            let _ = write_meta(
                &runner_meta_path,
                &spec,
                success.workspace_volume.as_deref(),
                success.workspace_root.as_ref(),
                success.runner_command.as_slice(),
                &success.runner_environment,
                success.container_id.as_deref(),
                success.exit_code,
                success.success,
                success.stdout_path.as_deref(),
                success.stderr_path.as_deref(),
                Some(success.log_retention.as_str()),
                None,
            );
            RunnerResult {
                success: success.success,
                container_id: success.container_id,
                exit_code: success.exit_code,
                stdout_path: success.stdout_path,
                stderr_path: success.stderr_path,
                error: success.error,
            }
        }
        RunOutcome::Failure(failure) => {
            let retained_stderr_path = write_retained_log(&stderr_log_path, &failure.error);
            let _ = write_meta(
                &runner_meta_path,
                &spec,
                failure.workspace_volume.as_deref(),
                failure.workspace_root.as_ref(),
                &[],
                &BTreeMap::new(),
                failure.container_id.as_deref(),
                1,
                false,
                None,
                retained_stderr_path.as_deref(),
                Some("failure_only"),
                Some(&failure.error),
            );
            RunnerResult {
                success: false,
                container_id: failure.container_id,
                exit_code: 1,
                stdout_path: None,
                stderr_path: retained_stderr_path,
                error: Some(failure.error),
            }
        }
    };

    if let Some(container_id) = result.container_id.as_deref() {
        let _ = docker_command(["rm", "-f", container_id]);
    }

    result
}

enum RunOutcome {
    Success(SuccessfulRun),
    Failure(FailedRun),
}

struct SuccessfulRun {
    success: bool,
    workspace_volume: Option<String>,
    workspace_root: Option<PathBuf>,
    runner_command: Vec<String>,
    runner_environment: BTreeMap<String, String>,
    container_id: Option<String>,
    exit_code: i32,
    stdout_path: Option<String>,
    stderr_path: Option<String>,
    error: Option<String>,
    log_retention: String,
}

struct FailedRun {
    workspace_volume: Option<String>,
    workspace_root: Option<PathBuf>,
    container_id: Option<String>,
    error: String,
}

fn run_spec(
    spec: &RunnerSpec,
    workspace: &Path,
    stdout_log_path: &Path,
    stderr_log_path: &Path,
) -> RunOutcome {
    let (workspace_root, runner_workspace) = match resolve_shared_workspace(workspace) {
        Ok(paths) => paths,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(scan_workspace_volume()),
                workspace_root: None,
                container_id: None,
                error: error.to_string(),
            });
        }
    };
    let rewritten_command = rewrite_runner_command(&spec.command, &runner_workspace);
    let rewritten_env = rewrite_runner_env(&spec.env, &runner_workspace);
    let workspace_volume = scan_workspace_volume();

    let mut create_args = vec![
        "create".to_string(),
        "-w".to_string(),
        runner_workspace.display().to_string(),
        "-v".to_string(),
        format!("{}:{}:rw", workspace_volume, workspace_root.display()),
    ];
    for (key, value) in &rewritten_env {
        create_args.push("-e".to_string());
        create_args.push(format!("{key}={value}"));
    }
    create_args.push(spec.image.clone());
    create_args.extend(rewritten_command.iter().cloned());

    let create_output = match docker_command(create_args.iter().map(String::as_str)) {
        Ok(output) => output,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: None,
                error: error.to_string(),
            });
        }
    };
    if !create_output.status.success() {
        return RunOutcome::Failure(FailedRun {
            workspace_volume: Some(workspace_volume),
            workspace_root: Some(workspace_root),
            container_id: None,
            error: format!(
                "docker create failed: {}",
                String::from_utf8_lossy(&create_output.stderr).trim()
            ),
        });
    }

    let created_container_id = String::from_utf8_lossy(&create_output.stdout)
        .trim()
        .to_string();
    if created_container_id.is_empty() {
        return RunOutcome::Failure(FailedRun {
            workspace_volume: Some(workspace_volume),
            workspace_root: Some(workspace_root),
            container_id: None,
            error: "docker create returned empty container id".to_string(),
        });
    }

    let start_output = match docker_command_with_timeout(
        ["start", "-a", created_container_id.as_str()],
        Some(Duration::from_secs(spec.timeout_seconds.max(1))),
    ) {
        Ok(output) => output,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: Some(created_container_id),
                error: error.to_string(),
            });
        }
    };
    if start_output.timed_out {
        let stop_timeout = DOCKER_STOP_TIMEOUT_SECONDS.to_string();
        let _ = docker_command([
            "stop",
            "-t",
            stop_timeout.as_str(),
            created_container_id.as_str(),
        ]);
        return RunOutcome::Failure(FailedRun {
            workspace_volume: Some(workspace_volume),
            workspace_root: Some(workspace_root),
            container_id: Some(created_container_id),
            error: format!(
                "docker start timed out after {}s",
                spec.timeout_seconds.max(1)
            ),
        });
    }
    let wait_output = match docker_command(["wait", created_container_id.as_str()]) {
        Ok(output) => output,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: Some(created_container_id),
                error: error.to_string(),
            });
        }
    };
    let waited_exit_code =
        parse_exit_code_from_stdout(&String::from_utf8_lossy(&wait_output.stdout))
            .or_else(|| wait_output.status.code())
            .unwrap_or(1);
    let exit_code = match inspect_exit_code(&created_container_id) {
        Ok(value) => value.or(Some(waited_exit_code)).unwrap_or(1),
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: Some(created_container_id),
                error: error.to_string(),
            });
        }
    };

    let stdout_text = start_output.stdout;
    let stderr_text = start_output.stderr;
    let keep_logs = exit_code != 0;

    let captured_stdout_path = match spec
        .capture_stdout_path
        .as_deref()
        .map(|path| write_full_text(&workspace.join(path), &stdout_text))
        .transpose()
    {
        Ok(value) => value,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: Some(created_container_id),
                error: error.to_string(),
            });
        }
    };
    let captured_stderr_path = match spec
        .capture_stderr_path
        .as_deref()
        .map(|path| write_full_text(&workspace.join(path), &stderr_text))
        .transpose()
    {
        Ok(value) => value,
        Err(error) => {
            return RunOutcome::Failure(FailedRun {
                workspace_volume: Some(workspace_volume),
                workspace_root: Some(workspace_root),
                container_id: Some(created_container_id),
                error: error.to_string(),
            });
        }
    };

    let retained_stdout_path = if keep_logs {
        write_retained_log(stdout_log_path, &stdout_text)
    } else {
        None
    };
    let retained_stderr_path = if keep_logs {
        write_retained_log(stderr_log_path, &stderr_text)
    } else {
        None
    };

    let expected_exit_codes = if spec.expected_exit_codes.is_empty() {
        default_expected_exit_codes()
    } else {
        spec.expected_exit_codes.clone()
    };

    let success = expected_exit_codes.contains(&exit_code);

    RunOutcome::Success(SuccessfulRun {
        success,
        workspace_volume: Some(workspace_volume),
        workspace_root: Some(workspace_root),
        runner_command: rewritten_command,
        runner_environment: rewritten_env,
        container_id: Some(created_container_id),
        exit_code,
        stdout_path: captured_stdout_path.or(retained_stdout_path),
        stderr_path: captured_stderr_path.or(retained_stderr_path),
        error: if success {
            None
        } else {
            Some(format!("scanner container exited with code {exit_code}"))
        },
        log_retention: if keep_logs {
            "nonzero_exit".to_string()
        } else {
            "dropped".to_string()
        },
    })
}

fn ensure_workspace_artifacts(workspace: &Path) -> Result<(PathBuf, PathBuf)> {
    let logs_dir = workspace.join("logs");
    let meta_dir = workspace.join("meta");
    fs::create_dir_all(&logs_dir)
        .with_context(|| format!("create logs dir {}", logs_dir.display()))?;
    fs::create_dir_all(&meta_dir)
        .with_context(|| format!("create meta dir {}", meta_dir.display()))?;
    Ok((logs_dir, meta_dir))
}

fn scan_workspace_root() -> PathBuf {
    env::var("SCAN_WORKSPACE_ROOT")
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("/tmp/vulhunter/scans"))
}

fn scan_workspace_volume() -> String {
    env::var("SCAN_WORKSPACE_VOLUME")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "vulhunter_scan_workspace".to_string())
}

fn docker_bin() -> String {
    env::var("BACKEND_DOCKER_BIN")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "docker".to_string())
}

fn resolve_shared_workspace(workspace: &Path) -> Result<(PathBuf, PathBuf)> {
    let workspace_root = scan_workspace_root();
    let resolved_workspace = workspace
        .canonicalize()
        .with_context(|| format!("canonicalize workspace {}", workspace.display()))?;
    let resolved_root = workspace_root
        .canonicalize()
        .with_context(|| format!("canonicalize workspace root {}", workspace_root.display()))?;
    if !resolved_workspace.starts_with(&resolved_root) {
        anyhow::bail!(
            "workspace_dir must stay inside shared workspace root: workspace={} root={}",
            resolved_workspace.display(),
            resolved_root.display()
        );
    }
    Ok((resolved_root, resolved_workspace))
}

fn rewrite_runner_command(command: &[String], workspace: &Path) -> Vec<String> {
    command
        .iter()
        .map(|item| rewrite_mount_path(item, workspace))
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

fn rewrite_mount_path(value: &str, workspace: &Path) -> String {
    if value == SCANNER_MOUNT_PATH {
        return workspace.display().to_string();
    }
    if let Some(stripped) = value.strip_prefix(&format!("{SCANNER_MOUNT_PATH}/")) {
        return workspace.join(stripped).display().to_string();
    }
    value.to_string()
}

fn inspect_exit_code(container_id: &str) -> Result<Option<i32>> {
    let output = docker_command(["inspect", "--format", "{{.State.ExitCode}}", container_id])?;
    if !output.status.success() {
        return Ok(None);
    }
    let raw = String::from_utf8_lossy(&output.stdout);
    Ok(raw.trim().parse::<i32>().ok())
}

fn parse_exit_code_from_stdout(stdout: &str) -> Option<i32> {
    stdout
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .and_then(|line| line.parse::<i32>().ok())
}

fn docker_command<'a>(args: impl IntoIterator<Item = &'a str>) -> Result<Output> {
    let args_vec = args.into_iter().collect::<Vec<_>>();
    Command::new(docker_bin())
        .args(&args_vec)
        .output()
        .with_context(|| format!("run docker command: {}", args_vec.join(" ")))
}

struct CommandCapture {
    stdout: String,
    stderr: String,
    timed_out: bool,
}

fn docker_command_with_timeout<'a>(
    args: impl IntoIterator<Item = &'a str>,
    timeout: Option<Duration>,
) -> Result<CommandCapture> {
    let args_vec = args.into_iter().map(str::to_string).collect::<Vec<_>>();
    let mut child = Command::new(docker_bin())
        .args(&args_vec)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("run docker command: {}", args_vec.join(" ")))?;

    let stdout = child
        .stdout
        .take()
        .context("capture docker command stdout")?;
    let stderr = child
        .stderr
        .take()
        .context("capture docker command stderr")?;

    let stdout_handle = thread::spawn(move || -> Result<Vec<u8>> {
        let mut reader = stdout;
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .context("read docker stdout")?;
        Ok(bytes)
    });
    let stderr_handle = thread::spawn(move || -> Result<Vec<u8>> {
        let mut reader = stderr;
        let mut bytes = Vec::new();
        reader
            .read_to_end(&mut bytes)
            .context("read docker stderr")?;
        Ok(bytes)
    });

    let started_at = Instant::now();
    let mut timed_out = false;
    let _exit_code = loop {
        if let Some(status) = child.try_wait().context("poll docker child status")? {
            break status.code().unwrap_or(1);
        }
        if timeout.is_some_and(|limit| started_at.elapsed() >= limit) {
            timed_out = true;
            let _ = child.kill();
            let status = child.wait().context("wait killed docker child")?;
            break status.code().unwrap_or(1);
        }
        thread::sleep(Duration::from_millis(50));
    };

    let stdout = String::from_utf8_lossy(
        &stdout_handle
            .join()
            .map_err(|_| anyhow::anyhow!("join docker stdout reader"))??,
    )
    .to_string();
    let stderr = String::from_utf8_lossy(
        &stderr_handle
            .join()
            .map_err(|_| anyhow::anyhow!("join docker stderr reader"))??,
    )
    .to_string();

    Ok(CommandCapture {
        stdout,
        stderr,
        timed_out,
    })
}

fn truncate_log_text(text: &str) -> String {
    if text.chars().count() <= MAX_RETAINED_LOG_CHARS {
        return text.to_string();
    }

    let tail_chars = MAX_RETAINED_LOG_CHARS.saturating_sub(64);
    let total_chars = text.chars().count();
    let start_index = text
        .char_indices()
        .nth(total_chars.saturating_sub(tail_chars))
        .map(|(index, _)| index)
        .unwrap_or(0);
    format!(
        "[truncated {} chars]\n{}",
        total_chars.saturating_sub(tail_chars),
        &text[start_index..]
    )
}

fn write_retained_log(path: &Path, text: &str) -> Option<String> {
    let content = truncate_log_text(text);
    if content.trim().is_empty() {
        return None;
    }
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    fs::write(path, content).ok()?;
    Some(path.display().to_string())
}

fn write_full_text(path: &Path, text: &str) -> Result<String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create parent dir {}", parent.display()))?;
    }
    fs::write(path, text).with_context(|| format!("write {}", path.display()))?;
    Ok(path.display().to_string())
}

#[derive(Serialize)]
struct RunnerMeta<'a> {
    spec: &'a RunnerSpec,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    runner_command: Vec<String>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    runner_environment: BTreeMap<String, String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    workspace_volume: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    workspace_root: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    container_id: Option<String>,
    exit_code: i32,
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    stdout_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stderr_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    log_retention: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[allow(clippy::too_many_arguments)]
fn write_meta(
    runner_meta_path: &Path,
    spec: &RunnerSpec,
    workspace_volume: Option<&str>,
    workspace_root: Option<&PathBuf>,
    runner_command: &[String],
    runner_environment: &BTreeMap<String, String>,
    container_id: Option<&str>,
    exit_code: i32,
    success: bool,
    stdout_path: Option<&str>,
    stderr_path: Option<&str>,
    log_retention: Option<&str>,
    error: Option<&str>,
) -> Result<()> {
    let meta = RunnerMeta {
        spec,
        runner_command: runner_command.to_vec(),
        runner_environment: runner_environment.clone(),
        workspace_volume: workspace_volume.map(str::to_string),
        workspace_root: workspace_root.map(|path| path.display().to_string()),
        container_id: container_id.map(str::to_string),
        exit_code,
        success,
        stdout_path: stdout_path.map(str::to_string),
        stderr_path: stderr_path.map(str::to_string),
        log_retention: log_retention.map(str::to_string),
        error: error.map(str::to_string),
    };
    let payload = serde_json::to_string_pretty(&meta).context("serialize runner meta")?;
    fs::write(runner_meta_path, payload)
        .with_context(|| format!("write {}", runner_meta_path.display()))
}

#[cfg(test)]
mod tests {
    use super::{execute, stop_container, RunnerSpec};
    use std::{
        collections::BTreeMap,
        env, fs,
        path::{Path, PathBuf},
        sync::{Mutex, OnceLock},
    };
    use tempfile::TempDir;

    static ENV_MUTEX: OnceLock<Mutex<()>> = OnceLock::new();

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        ENV_MUTEX.get_or_init(|| Mutex::new(())).lock().unwrap()
    }

    fn write_fake_docker(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-docker.sh");
        let script = r#"#!/usr/bin/env bash
set -eu
cmd="${1:-}"
shift || true
case "${cmd}" in
  create)
    printf '%s\n' "$@" > "${FAKE_DOCKER_CREATE_ARGS_FILE}"
    printf '%s' "${FAKE_DOCKER_CONTAINER_ID:-container-xyz}"
    ;;
  start)
    if [ "${1:-}" = "-a" ]; then
      shift
    fi
    printf '%s' "${FAKE_DOCKER_START_STDOUT:-}"
    printf '%s' "${FAKE_DOCKER_START_STDERR:-}" >&2
    ;;
  inspect)
    if [ "${1:-}" = "--format" ]; then
      shift 2
    fi
    if [ "${FAKE_DOCKER_INSPECT_FAIL:-0}" = "1" ]; then
      echo "missing" >&2
      exit 1
    fi
    printf '%s' "${FAKE_DOCKER_EXIT_CODE:-0}"
    ;;
  wait)
    printf '%s' "${FAKE_DOCKER_WAIT_EXIT_CODE:-${FAKE_DOCKER_EXIT_CODE:-0}}"
    ;;
  stop)
    if [ "${FAKE_DOCKER_STOP_FAIL:-0}" = "1" ]; then
      exit 1
    fi
    ;;
  rm)
    ;;
  *)
    echo "unsupported command: ${cmd}" >&2
    exit 1
    ;;
esac
"#;
        fs::write(&script_path, script).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(&script_path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(&script_path, permissions).unwrap();
        }
        script_path
    }

    fn base_spec(workspace: &Path) -> RunnerSpec {
        RunnerSpec {
            scanner_type: "flow_parser".to_string(),
            image: "vulhunter/flow-parser-runner:test".to_string(),
            workspace_dir: workspace.display().to_string(),
            command: vec![
                "python3".to_string(),
                "/opt/flow-parser/flow_parser_runner.py".to_string(),
                "definitions-batch".to_string(),
                "--request".to_string(),
                "/scan/request.json".to_string(),
                "--response".to_string(),
                "/scan/response.json".to_string(),
            ],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: Vec::new(),
            capture_stdout_path: None,
            capture_stderr_path: None,
        }
    }

    #[test]
    fn runner_executes_with_rewritten_workspace_contract() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().unwrap();
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("flow-parser").join("task-1");
        fs::create_dir_all(&workspace_dir).unwrap();
        let fake_docker = write_fake_docker(&temp_dir);
        let args_file = temp_dir.path().join("create-args.txt");

        env::set_var("SCAN_WORKSPACE_ROOT", &workspace_root);
        env::set_var("SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace");
        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_CREATE_ARGS_FILE", &args_file);
        env::set_var("FAKE_DOCKER_EXIT_CODE", "0");
        env::set_var("FAKE_DOCKER_WAIT_EXIT_CODE", "0");

        let mut spec = base_spec(&workspace_dir);
        spec.env.insert(
            "FLOW_PARSER_CACHE_DIR".to_string(),
            "/scan/cache".to_string(),
        );

        let result = execute(spec);

        assert!(result.success);
        assert_eq!(result.container_id.as_deref(), Some("container-xyz"));
        assert_eq!(result.exit_code, 0);
        assert!(result.stdout_path.is_none());
        assert!(result.stderr_path.is_none());

        let args = fs::read_to_string(&args_file).unwrap();
        assert!(args.contains("-w"));
        assert!(args.contains(&workspace_dir.canonicalize().unwrap().display().to_string()));
        assert!(args.contains("-v"));
        assert!(args.contains(&format!(
            "vulhunter_scan_workspace:{}:rw",
            workspace_root.canonicalize().unwrap().display()
        )));
        assert!(args.contains(&format!(
            "FLOW_PARSER_CACHE_DIR={}",
            workspace_dir
                .canonicalize()
                .unwrap()
                .join("cache")
                .display()
        )));
        assert!(args.contains(
            &workspace_dir
                .canonicalize()
                .unwrap()
                .join("request.json")
                .display()
                .to_string()
        ));

        let runner_meta =
            fs::read_to_string(workspace_dir.join("meta").join("runner.json")).unwrap();
        assert!(runner_meta.contains("\"exit_code\": 0"));
        assert!(runner_meta.contains("\"success\": true"));
    }

    #[test]
    fn runner_keeps_truncated_logs_for_nonzero_exit() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().unwrap();
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("flow-parser").join("task-1");
        fs::create_dir_all(&workspace_dir).unwrap();
        let fake_docker = write_fake_docker(&temp_dir);
        let args_file = temp_dir.path().join("create-args.txt");
        let long_stderr = "fatal stderr line ".repeat(1200);

        env::set_var("SCAN_WORKSPACE_ROOT", &workspace_root);
        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_CREATE_ARGS_FILE", &args_file);
        env::set_var("FAKE_DOCKER_EXIT_CODE", "2");
        env::set_var("FAKE_DOCKER_WAIT_EXIT_CODE", "2");
        env::set_var("FAKE_DOCKER_START_STDERR", &long_stderr);

        let result = execute(base_spec(&workspace_dir));

        assert!(!result.success);
        assert_eq!(result.exit_code, 2);
        let stderr_path = PathBuf::from(result.stderr_path.unwrap());
        let stderr_text = fs::read_to_string(stderr_path).unwrap();
        assert!(stderr_text.contains("fatal stderr line"));
        assert!(stderr_text.len() < long_stderr.len());
    }

    #[test]
    fn runner_expected_nonzero_exit_is_success_and_keeps_logs() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().unwrap();
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("flow-parser").join("task-1");
        fs::create_dir_all(&workspace_dir).unwrap();
        let fake_docker = write_fake_docker(&temp_dir);
        let args_file = temp_dir.path().join("create-args.txt");

        env::set_var("SCAN_WORKSPACE_ROOT", &workspace_root);
        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_CREATE_ARGS_FILE", &args_file);
        env::set_var("FAKE_DOCKER_EXIT_CODE", "1");
        env::set_var("FAKE_DOCKER_WAIT_EXIT_CODE", "1");
        env::set_var("FAKE_DOCKER_START_STDOUT", "runner stdout");
        env::set_var("FAKE_DOCKER_START_STDERR", "runner stderr");

        let mut spec = base_spec(&workspace_dir);
        spec.expected_exit_codes = vec![0, 1];

        let result = execute(spec);

        assert!(result.success);
        assert_eq!(result.exit_code, 1);
        let stdout_text = fs::read_to_string(result.stdout_path.unwrap()).unwrap();
        let stderr_text = fs::read_to_string(result.stderr_path.unwrap()).unwrap();
        assert_eq!(stdout_text, "runner stdout");
        assert_eq!(stderr_text, "runner stderr");
    }

    #[test]
    fn runner_rejects_workspace_outside_shared_root() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().unwrap();
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = temp_dir.path().join("elsewhere").join("task-1");
        fs::create_dir_all(&workspace_root).unwrap();
        fs::create_dir_all(&workspace_dir).unwrap();

        env::set_var("SCAN_WORKSPACE_ROOT", &workspace_root);

        let result = execute(base_spec(&workspace_dir));

        assert!(!result.success);
        assert_eq!(result.exit_code, 1);
        assert!(result
            .error
            .as_deref()
            .unwrap_or_default()
            .contains("shared workspace root"));
    }

    #[test]
    fn runner_stop_handles_missing_container() {
        let _guard = env_lock();
        let temp_dir = TempDir::new().unwrap();
        let fake_docker = write_fake_docker(&temp_dir);

        env::set_var("BACKEND_DOCKER_BIN", &fake_docker);
        env::set_var("FAKE_DOCKER_INSPECT_FAIL", "1");

        assert!(!stop_container("missing-container"));
    }
}
