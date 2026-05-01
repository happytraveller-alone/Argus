use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashSet},
    env, fs,
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

pub const SCANNER_MOUNT_PATH: &str = "/scan";
const MAX_RETAINED_LOG_CHARS: usize = 12_000;
const DEFAULT_SCAN_WORKSPACE_ROOT: &str = "/tmp/Argus/scans";
const DEFAULT_SCAN_WORKSPACE_VOLUME: &str = "Argus_scan_workspace";

#[derive(Clone, Debug, Serialize, Deserialize)]
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
    #[serde(default)]
    pub capture_stdout_path: Option<String>,
    #[serde(default)]
    pub capture_stderr_path: Option<String>,
    #[serde(default)]
    pub completion_summary_path: Option<String>,
    #[serde(default)]
    pub workspace_root_override: Option<String>,
    #[serde(default)]
    pub memory_limit_mb: Option<u64>,
    #[serde(default)]
    pub memory_swap_limit_mb: Option<u64>,
    #[serde(default)]
    pub cpu_limit: Option<f64>,
    #[serde(default)]
    pub pids_limit: Option<u64>,
    #[serde(default)]
    pub network_disabled: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
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

fn scan_workspace_root() -> PathBuf {
    env::var("SCAN_WORKSPACE_ROOT")
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from(DEFAULT_SCAN_WORKSPACE_ROOT))
}

fn scan_workspace_volume() -> String {
    env::var("SCAN_WORKSPACE_VOLUME")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| DEFAULT_SCAN_WORKSPACE_VOLUME.to_string())
}

fn docker_bin_with_priority(keys: &[&str]) -> String {
    keys.iter()
        .find_map(|key| {
            env::var(key)
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
        })
        .unwrap_or_else(|| "docker".to_string())
}

fn docker_bin(_scanner_type: Option<&str>) -> String {
    docker_bin_with_priority(&["Argus_DOCKER_BIN", "BACKEND_DOCKER_BIN"])
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

fn resolve_shared_workspace(
    workspace: &Path,
    workspace_root_override: Option<&str>,
) -> Result<(PathBuf, PathBuf)> {
    let workspace_root = workspace_root_override
        .map(PathBuf::from)
        .unwrap_or_else(scan_workspace_root);
    let resolved_workspace = workspace
        .canonicalize()
        .with_context(|| format!("canonicalize workspace_dir: {}", workspace.display()))?;
    let resolved_root = workspace_root
        .canonicalize()
        .with_context(|| format!("canonicalize workspace root: {}", workspace_root.display()))?;
    if !resolved_workspace.starts_with(&resolved_root) {
        bail!(
            "workspace_dir must stay inside shared workspace root: workspace={} root={}",
            resolved_workspace.display(),
            resolved_root.display()
        );
    }
    Ok((resolved_root, resolved_workspace))
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
    if limit.fract() == 0.0 {
        format!("{limit:.0}")
    } else {
        limit.to_string()
    }
}

fn run_command_capture(binary: &str, args: &[String]) -> Result<Output> {
    Command::new(binary)
        .args(args)
        .output()
        .with_context(|| format!("run docker command: {}", args.join(" ")))
}

struct CommandCapture {
    timed_out: bool,
    success: bool,
    stdout: String,
    stderr: String,
}

struct SummaryGateOutcome {
    summary_observed: bool,
    timed_out: bool,
}

fn run_command_capture_with_timeout(
    binary: &str,
    args: &[String],
    timeout: Option<Duration>,
) -> Result<CommandCapture> {
    let mut child = Command::new(binary)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("run docker command: {}", args.join(" ")))?;

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
    let exit_status = loop {
        if let Some(status) = child.try_wait().context("poll docker child status")? {
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
        timed_out,
        success: exit_status.as_ref().is_some_and(|status| status.success()),
        stdout,
        stderr,
    })
}

fn docker_logs(binary: &str, container_id: &str, stdout: bool) -> Result<String> {
    let mut args = vec!["logs".to_string()];
    args.push(if stdout { "--stdout" } else { "--stderr" }.to_string());
    args.push(container_id.to_string());
    let output = run_command_capture(binary, &args)?;
    if !output.status.success() {
        return Ok(String::new());
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn output_error_text(output: &Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !stderr.is_empty() {
        return stderr;
    }
    String::from_utf8_lossy(&output.stdout).trim().to_string()
}

fn parse_exit_code(output: &Output) -> Result<i32> {
    let text = String::from_utf8_lossy(&output.stdout);
    parse_wait_exit_code_text(&text)
}

fn parse_wait_exit_code_text(text: &str) -> Result<i32> {
    let line = text
        .lines()
        .find(|line| !line.trim().is_empty())
        .unwrap_or("")
        .trim();
    line.parse::<i32>()
        .with_context(|| format!("parse docker wait exit code from `{line}`"))
}

fn inspect_container_running(binary: &str, container_id: &str) -> Result<bool> {
    let inspect = run_command_capture(
        binary,
        &[
            "inspect".to_string(),
            "--format".to_string(),
            "{{.State.Running}}".to_string(),
            container_id.to_string(),
        ],
    )?;
    if !inspect.status.success() {
        bail!("docker inspect failed: {}", output_error_text(&inspect));
    }
    Ok(String::from_utf8_lossy(&inspect.stdout)
        .trim()
        .eq_ignore_ascii_case("true"))
}

fn request_container_stop(binary: &str, container_id: &str) -> Result<()> {
    let stop_output = run_command_capture(
        binary,
        &[
            "stop".to_string(),
            "-t".to_string(),
            "2".to_string(),
            container_id.to_string(),
        ],
    )?;
    if stop_output.status.success() {
        return Ok(());
    }
    let inspect = run_command_capture(
        binary,
        &[
            "inspect".to_string(),
            "--format".to_string(),
            "{{.State.Running}}".to_string(),
            container_id.to_string(),
        ],
    )?;
    if !inspect.status.success() {
        return Ok(());
    }
    if !String::from_utf8_lossy(&inspect.stdout)
        .trim()
        .eq_ignore_ascii_case("true")
    {
        return Ok(());
    }
    bail!("docker stop failed: {}", output_error_text(&stop_output));
}

fn summary_gate_exit_timeout() -> Duration {
    env::var("Argus_SUMMARY_GATE_EXIT_TIMEOUT_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .filter(|value| *value > 0)
        .map(Duration::from_secs)
        .unwrap_or_else(|| Duration::from_secs(15))
}

fn summary_gate_post_exit_grace() -> Duration {
    env::var("Argus_SUMMARY_GATE_POST_EXIT_GRACE_MS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .filter(|value| *value > 0)
        .map(Duration::from_millis)
        .unwrap_or_else(|| Duration::from_millis(1_000))
}

fn wait_for_summary_path(summary_path: &Path, timeout: Duration) -> bool {
    let started_at = Instant::now();
    loop {
        if summary_path.is_file() {
            return true;
        }
        if started_at.elapsed() >= timeout {
            return false;
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn poll_summary_gate(
    binary: &str,
    container_id: &str,
    summary_path: &Path,
    timeout: Option<Duration>,
) -> Result<SummaryGateOutcome> {
    let started_at = Instant::now();
    loop {
        if summary_path.is_file() {
            return Ok(SummaryGateOutcome {
                summary_observed: true,
                timed_out: false,
            });
        }

        if !inspect_container_running(binary, container_id)? {
            return Ok(SummaryGateOutcome {
                summary_observed: wait_for_summary_path(
                    summary_path,
                    summary_gate_post_exit_grace(),
                ),
                timed_out: false,
            });
        }

        if timeout.is_some_and(|limit| started_at.elapsed() >= limit) {
            request_container_stop(binary, container_id)?;
            return Ok(SummaryGateOutcome {
                summary_observed: false,
                timed_out: true,
            });
        }
        thread::sleep(Duration::from_millis(100));
    }
}

struct RunnerMetaContext<'a> {
    runner_command: &'a [String],
    runner_environment: &'a BTreeMap<String, String>,
    workspace_volume: &'a str,
    workspace_root: Option<&'a Path>,
    result: &'a RunnerResult,
    log_retention: &'a str,
}

fn write_runner_meta(
    runner_meta_path: &Path,
    spec: &RunnerSpec,
    context: &RunnerMetaContext<'_>,
) -> Result<()> {
    let payload = serde_json::json!({
        "spec": spec,
        "runner_command": context.runner_command,
        "runner_environment": context.runner_environment,
        "workspace_volume": context.workspace_volume,
        "workspace_root": context.workspace_root.map(|path| path.display().to_string()),
        "container_id": context.result.container_id,
        "exit_code": context.result.exit_code,
        "success": context.result.success,
        "stdout_path": context.result.stdout_path,
        "stderr_path": context.result.stderr_path,
        "error": context.result.error,
        "log_retention": context.log_retention,
    });
    fs::write(
        runner_meta_path,
        serde_json::to_string_pretty(&payload).context("serialize runner meta")?,
    )
    .with_context(|| format!("write runner meta: {}", runner_meta_path.display()))
}

fn cleanup_container(binary: &str, container_id: Option<&str>) {
    if let Some(container_id) = container_id {
        let _ = run_command_capture(
            binary,
            &["rm".to_string(), "-f".to_string(), container_id.to_string()],
        );
    }
}

pub fn execute(spec: RunnerSpec) -> RunnerResult {
    let (workspace, logs_dir, meta_dir) = match ensure_workspace_artifacts(&spec.workspace_dir) {
        Ok(value) => value,
        Err(err) => {
            return RunnerResult {
                success: false,
                container_id: None,
                exit_code: 1,
                stdout_path: None,
                stderr_path: None,
                error: Some(err.to_string()),
            };
        }
    };

    let stdout_log_path = logs_dir.join("stdout.log");
    let stderr_log_path = logs_dir.join("stderr.log");
    let runner_meta_path = meta_dir.join("runner.json");
    let workspace_volume = scan_workspace_volume();
    let docker_binary = docker_bin(Some(&spec.scanner_type));
    let expected_exit_codes = spec
        .expected_exit_codes
        .iter()
        .copied()
        .collect::<HashSet<_>>();

    let mut container_id: Option<String> = None;
    let mut workspace_root: Option<PathBuf> = None;
    let mut runner_command = spec.command.clone();
    let mut runner_environment = spec.env.clone();

    let execution = (|| -> Result<RunnerResult> {
        let (resolved_root, resolved_workspace) =
            resolve_shared_workspace(&workspace, spec.workspace_root_override.as_deref())?;
        workspace_root = Some(resolved_root.clone());
        runner_command = rewrite_runner_command(&spec.command, &resolved_workspace);
        runner_environment = rewrite_runner_env(&spec.env, &resolved_workspace);

        let mut create_args = vec![
            "create".to_string(),
            "-w".to_string(),
            resolved_workspace.display().to_string(),
            "-v".to_string(),
            format!("{}:{}:rw", workspace_volume, resolved_root.display()),
        ];
        if let Some(limit_mb) = spec.memory_limit_mb {
            create_args.push("--memory".to_string());
            create_args.push(format_memory_limit_mb(limit_mb));
        }
        if let Some(limit_mb) = spec.memory_swap_limit_mb {
            create_args.push("--memory-swap".to_string());
            create_args.push(format_memory_limit_mb(limit_mb));
        }
        if let Some(limit) = spec.cpu_limit {
            create_args.push("--cpus".to_string());
            create_args.push(format_cpu_limit(limit));
        }
        if let Some(limit) = spec.pids_limit {
            create_args.push("--pids-limit".to_string());
            create_args.push(limit.to_string());
        }
        if spec.network_disabled {
            create_args.push("--network".to_string());
            create_args.push("none".to_string());
        }
        for (key, value) in &runner_environment {
            create_args.push("-e".to_string());
            create_args.push(format!("{key}={value}"));
        }
        create_args.push(spec.image.clone());
        create_args.extend(runner_command.clone());

        let create_output = run_command_capture(&docker_binary, &create_args)?;
        if !create_output.status.success() {
            bail!(
                "docker create failed: {}",
                output_error_text(&create_output)
            );
        }
        let created_id = String::from_utf8_lossy(&create_output.stdout)
            .trim()
            .to_string();
        if created_id.is_empty() {
            bail!("docker create returned empty container id");
        }
        container_id = Some(created_id.clone());

        let start_timeout = if spec.timeout_seconds == 0 {
            None
        } else {
            Some(Duration::from_secs(spec.timeout_seconds))
        };

        let mut summary_observed = false;
        let start_output = if let Some(summary_path) = &spec.completion_summary_path {
            let start_output =
                run_command_capture(&docker_binary, &["start".to_string(), created_id.clone()])?;
            if !start_output.status.success() {
                bail!("docker start failed: {}", output_error_text(&start_output));
            }
            let gate = poll_summary_gate(
                &docker_binary,
                &created_id,
                &workspace.join(summary_path),
                start_timeout,
            )?;
            if gate.timed_out {
                bail!(
                    "docker summary gate timed out after {}s",
                    spec.timeout_seconds
                );
            }
            summary_observed = gate.summary_observed;
            CommandCapture {
                timed_out: false,
                success: true,
                stdout: String::new(),
                stderr: String::new(),
            }
        } else {
            let start_args = vec!["start".to_string(), "-a".to_string(), created_id.clone()];
            let start_output =
                run_command_capture_with_timeout(&docker_binary, &start_args, start_timeout)?;
            if start_output.timed_out {
                let _ = run_command_capture(
                    &docker_binary,
                    &[
                        "stop".to_string(),
                        "-t".to_string(),
                        "2".to_string(),
                        created_id.clone(),
                    ],
                );
                bail!("docker start timed out after {}s", spec.timeout_seconds);
            }
            start_output
        };

        let exit_code = if summary_observed {
            let wait_output = run_command_capture_with_timeout(
                &docker_binary,
                &["wait".to_string(), created_id.clone()],
                Some(summary_gate_exit_timeout()),
            )?;
            if wait_output.timed_out {
                cleanup_container(&docker_binary, Some(&created_id));
                bail!(
                    "docker wait timed out after summary gate after {}s",
                    summary_gate_exit_timeout().as_secs()
                );
            }
            if !wait_output.success {
                let error_text = if !wait_output.stderr.trim().is_empty() {
                    wait_output.stderr.trim().to_string()
                } else {
                    wait_output.stdout.trim().to_string()
                };
                bail!("docker wait failed: {error_text}");
            }
            parse_wait_exit_code_text(&wait_output.stdout)?
        } else {
            let wait_output =
                run_command_capture(&docker_binary, &["wait".to_string(), created_id.clone()])?;
            if !wait_output.status.success() {
                bail!("docker wait failed: {}", output_error_text(&wait_output));
            }
            parse_exit_code(&wait_output)?
        };
        let summary_required = spec.completion_summary_path.is_some();
        let success =
            expected_exit_codes.contains(&exit_code) && (!summary_required || summary_observed);
        let needs_debug_capture = exit_code != 0 || !success;
        let should_capture_stdout = spec.capture_stdout_path.is_some() || needs_debug_capture;
        let should_capture_stderr = spec.capture_stderr_path.is_some() || needs_debug_capture;
        let mut stdout_text = if should_capture_stdout {
            start_output.stdout.clone()
        } else {
            String::new()
        };
        let mut stderr_text = if should_capture_stderr {
            start_output.stderr.clone()
        } else {
            String::new()
        };
        if stdout_text.is_empty() && should_capture_stdout {
            stdout_text = docker_logs(&docker_binary, &created_id, true)?;
        }
        if stderr_text.is_empty() && should_capture_stderr {
            stderr_text = docker_logs(&docker_binary, &created_id, false)?;
        }

        let captured_stdout_path = spec
            .capture_stdout_path
            .as_ref()
            .map(|relative| write_full_text(&workspace.join(relative), &stdout_text))
            .transpose()?;
        let captured_stderr_path = spec
            .capture_stderr_path
            .as_ref()
            .map(|relative| write_full_text(&workspace.join(relative), &stderr_text))
            .transpose()?;

        let keep_logs = needs_debug_capture;
        let retained_stdout_path = if keep_logs {
            write_retained_log(&stdout_log_path, &stdout_text)?
        } else {
            None
        };
        let retained_stderr_path = if keep_logs {
            write_retained_log(&stderr_log_path, &stderr_text)?
        } else {
            None
        };

        Ok(RunnerResult {
            success,
            container_id: Some(created_id),
            exit_code,
            stdout_path: captured_stdout_path.or(retained_stdout_path),
            stderr_path: captured_stderr_path.or(retained_stderr_path),
            error: if success {
                None
            } else if summary_required
                && !summary_observed
                && expected_exit_codes.contains(&exit_code)
            {
                Some("scanner completion summary was not observed".to_string())
            } else {
                Some(format!("scanner container exited with code {exit_code}"))
            },
        })
    })();

    let (result, log_retention) = match execution {
        Ok(result) => {
            let log_retention = if result.success && result.exit_code != 0 {
                "accepted_nonzero_exit"
            } else if result.success {
                "dropped"
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
                RunnerResult {
                    success: false,
                    container_id: container_id.clone(),
                    exit_code: 1,
                    stdout_path: None,
                    stderr_path,
                    error: Some(err.to_string()),
                },
                "failure_only".to_string(),
            )
        }
    };

    let meta_context = RunnerMetaContext {
        runner_command: &runner_command,
        runner_environment: &runner_environment,
        workspace_volume: &workspace_volume,
        workspace_root: workspace_root.as_deref(),
        result: &result,
        log_retention: &log_retention,
    };
    let _ = write_runner_meta(&runner_meta_path, &spec, &meta_context);
    cleanup_container(&docker_binary, container_id.as_deref());
    result
}

pub fn execute_spec_file(spec_path: &Path) -> Result<RunnerResult> {
    let raw = fs::read_to_string(spec_path)
        .with_context(|| format!("read runner spec: {}", spec_path.display()))?;
    let spec: RunnerSpec = serde_json::from_str(&raw)
        .with_context(|| format!("parse runner spec: {}", spec_path.display()))?;
    Ok(execute(spec))
}

pub fn execute_from_spec_path(spec_path: &Path) -> RunnerResult {
    execute_spec_file(spec_path).unwrap_or_else(|error| RunnerResult {
        success: false,
        container_id: None,
        exit_code: 1,
        stdout_path: None,
        stderr_path: None,
        error: Some(error.to_string()),
    })
}

pub fn stop_container_sync(container_id: &str) -> bool {
    let docker_binary = docker_bin(None);
    let inspect = run_command_capture(
        &docker_binary,
        &["inspect".to_string(), container_id.to_string()],
    );
    let Ok(inspect) = inspect else {
        return false;
    };
    if !inspect.status.success() {
        return false;
    }

    let _ = run_command_capture(
        &docker_binary,
        &[
            "stop".to_string(),
            "-t".to_string(),
            "2".to_string(),
            container_id.to_string(),
        ],
    );
    let remove = run_command_capture(
        &docker_binary,
        &["rm".to_string(), "-f".to_string(), container_id.to_string()],
    );
    matches!(remove, Ok(output) if output.status.success())
}

pub fn stop_container(container_id: &str) -> bool {
    stop_container_sync(container_id)
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

    fn fake_docker_script(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-docker.sh");
        let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_DOCKER_LOG:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  create)
    printf '%s\n' "${FAKE_CONTAINER_ID:-container-xyz}"
    ;;
  start)
    if [ -n "${FAKE_START_SLEEP:-}" ]; then
      sleep "${FAKE_START_SLEEP}"
    fi
    if [ -n "${FAKE_COMPLETION_SUMMARY_PATH:-}" ]; then
      mkdir -p "$(dirname "${FAKE_COMPLETION_SUMMARY_PATH}")"
      printf '{"status":"%s"}\n' "${FAKE_COMPLETION_SUMMARY_STATUS:-scan_completed}" > "${FAKE_COMPLETION_SUMMARY_PATH}"
    fi
    printf '%s' "${FAKE_START_STDOUT:-}"
    printf '%s' "${FAKE_START_STDERR:-}" >&2
    ;;
  wait)
    if [ -n "${FAKE_WAIT_SLEEP:-}" ]; then
      sleep "${FAKE_WAIT_SLEEP}"
    fi
    printf '%s\n' "${FAKE_WAIT_EXIT_CODE:-0}"
    ;;
  logs)
    if [ "${1:-}" = "--stdout" ]; then
      printf '%s' "${FAKE_STDOUT:-}"
      exit 0
    fi
    if [ "${1:-}" = "--stderr" ]; then
      printf '%s' "${FAKE_STDERR:-}"
      exit 0
    fi
    ;;
  inspect)
    if [ "${FAKE_INSPECT_MISSING:-0}" = "1" ]; then
      exit 1
    fi
    if [ "${1:-}" = "--format" ]; then
      printf '%s\n' "${FAKE_INSPECT_RUNNING:-false}"
      exit 0
    fi
    printf '[]\n'
    ;;
  stop)
    if [ -n "${FAKE_STOP_EXIT_CODE:-}" ]; then
      exit "${FAKE_STOP_EXIT_CODE}"
    fi
    printf 'stopped\n'
    ;;
  rm)
    printf 'removed\n'
    ;;
esac
"#;
        fs::write(&script_path, script).expect("write fake docker script");
        let mut permissions = fs::metadata(&script_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).unwrap();
        script_path
    }

    #[test]
    fn execute_passes_mounts_env_and_rewritten_command() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("yasa/task-1");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

        let result = execute(RunnerSpec {
            scanner_type: "yasa".to_string(),
            image: "Argus/yasa-runner:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "/opt/yasa/bin/yasa".to_string(),
                "--project".to_string(),
                "/scan/project".to_string(),
                "--help".to_string(),
            ],
            timeout_seconds: 123,
            env: BTreeMap::from([(
                "YASA_RESOURCE_DIR".to_string(),
                "/scan/resource".to_string(),
            )]),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.container_id.as_deref(), Some("container-xyz"));
        assert_eq!(result.exit_code, 0);
        assert!(result.stdout_path.is_none());
        assert!(result.stderr_path.is_none());
        assert!(!workspace_dir.join("logs/stdout.log").exists());
        assert!(!workspace_dir.join("logs/stderr.log").exists());

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("create|"));
        assert!(logged.contains(&format!(
            "-v Argus_scan_workspace:{}:rw",
            workspace_root.display()
        )));
        assert!(logged.contains(&format!(
            "-e YASA_RESOURCE_DIR={}/resource",
            workspace_dir.display()
        )));
        assert!(logged.contains(&format!("-w {}", workspace_dir.display())));
        assert!(logged.contains(&format!("--project {}/project", workspace_dir.display())));

        let runner_meta = fs::read_to_string(workspace_dir.join("meta/runner.json")).unwrap();
        assert!(runner_meta.contains("\"exit_code\": 0"));
        assert!(runner_meta.contains("\"stdout_path\": null"));
        assert!(runner_meta.contains("\"stderr_path\": null"));
    }

    #[test]
    fn execute_can_disable_container_network() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("codeql-compile-sandbox/task-network");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

        let result = execute(RunnerSpec {
            scanner_type: "codeql-compile-sandbox".to_string(),
            image: "Argus/codeql-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "codeql-compile-sandbox".to_string(),
                "--self-test".to_string(),
            ],
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: true,
        });

        assert!(result.success);
        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("--network none"), "{logged}");
    }

    #[test]
    fn execute_failure_keeps_truncated_error_logs() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("phpstan/task-1");
        fs::create_dir_all(&workspace_dir).unwrap();
        let long_stderr = "fatal stderr line ".repeat(1_200);

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _wait_exit = EnvVarGuard::set("FAKE_WAIT_EXIT_CODE", "2");
        let _stderr = EnvVarGuard::set("FAKE_STDERR", &long_stderr);

        let result = execute(RunnerSpec {
            scanner_type: "phpstan".to_string(),
            image: "Argus/phpstan-runner:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "phpstan".to_string(),
                "analyse".to_string(),
                "/scan/project".to_string(),
            ],
            timeout_seconds: 90,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(!result.success);
        assert_eq!(result.exit_code, 2);
        let stderr_path = PathBuf::from(result.stderr_path.unwrap());
        let stderr_text = fs::read_to_string(stderr_path).unwrap();
        assert!(stderr_text.contains("fatal stderr line"));
        assert!(stderr_text.len() < long_stderr.len());

        let runner_meta = fs::read_to_string(workspace_dir.join("meta/runner.json")).unwrap();
        assert!(runner_meta.contains("\"exit_code\": 2"));
        assert!(runner_meta.contains("\"stderr_path\":"));
    }

    #[test]
    fn execute_expected_nonzero_exit_keeps_logs() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("phpstan/task-1");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _wait_exit = EnvVarGuard::set("FAKE_WAIT_EXIT_CODE", "1");
        let _stdout = EnvVarGuard::set("FAKE_STDOUT", "runner stdout");
        let _stderr = EnvVarGuard::set("FAKE_STDERR", "runner stderr");

        let result = execute(RunnerSpec {
            scanner_type: "phpstan".to_string(),
            image: "Argus/phpstan-runner:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "phpstan".to_string(),
                "analyse".to_string(),
                "/scan/project".to_string(),
            ],
            timeout_seconds: 90,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 1);
        assert_eq!(
            fs::read_to_string(result.stdout_path.clone().unwrap()).unwrap(),
            "runner stdout"
        );
        assert_eq!(
            fs::read_to_string(result.stderr_path.clone().unwrap()).unwrap(),
            "runner stderr"
        );

        let runner_meta = fs::read_to_string(workspace_dir.join("meta/runner.json")).unwrap();
        assert!(runner_meta.contains("\"success\": true"));
        assert!(runner_meta.contains("\"log_retention\": \"accepted_nonzero_exit\""));
    }

    #[test]
    fn execute_rejects_workspace_outside_shared_root() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        fs::create_dir_all(&workspace_root).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());

        let result = execute(RunnerSpec {
            scanner_type: "phpstan".to_string(),
            image: "Argus/phpstan-runner:latest".to_string(),
            workspace_dir: temp_dir
                .path()
                .join("elsewhere/task-1")
                .display()
                .to_string(),
            command: vec![
                "phpstan".to_string(),
                "analyse".to_string(),
                "/scan/project".to_string(),
            ],
            timeout_seconds: 90,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(!result.success);
        assert!(result
            .error
            .as_deref()
            .is_some_and(|error| error.contains("shared workspace root")));
    }

    #[test]
    fn execute_allows_disabling_hard_timeout_with_zero_seconds() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-1");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _start_sleep = EnvVarGuard::set("FAKE_START_SLEEP", "2");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep".to_string(), "--version".to_string()],
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 0);
    }

    #[test]
    fn execute_opengrep_includes_container_resource_limits() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-resource-limits");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "opengrep".to_string(),
                "scan".to_string(),
                "--config".to_string(),
                "/scan/opengrep-rules".to_string(),
                "--json".to_string(),
                "/scan/source".to_string(),
            ],
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: Some(500),
            memory_swap_limit_mb: Some(500),
            cpu_limit: Some(1.5),
            pids_limit: Some(256),
            network_disabled: false,
        });

        assert!(result.success);

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("--memory 500m"), "{logged}");
        assert!(logged.contains("--memory-swap 500m"), "{logged}");
        assert!(logged.contains("--cpus 1.5"), "{logged}");
        assert!(logged.contains("--pids-limit 256"), "{logged}");
    }

    #[test]
    fn execute_uses_attached_start_output_without_followup_logs_roundtrip() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-attached-output");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _start_stdout = EnvVarGuard::set("FAKE_START_STDOUT", "attached stdout");
        let _start_stderr = EnvVarGuard::set("FAKE_START_STDERR", "attached stderr");
        let _stdout = EnvVarGuard::set("FAKE_STDOUT", "docker logs stdout");
        let _stderr = EnvVarGuard::set("FAKE_STDERR", "docker logs stderr");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep".to_string(), "scan".to_string()],
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            artifact_paths: vec![],
            capture_stdout_path: Some("output/results.txt".to_string()),
            capture_stderr_path: Some("output/stderr.txt".to_string()),
            completion_summary_path: None,
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(
            fs::read_to_string(result.stdout_path.clone().unwrap()).unwrap(),
            "attached stdout"
        );
        assert_eq!(
            fs::read_to_string(result.stderr_path.clone().unwrap()).unwrap(),
            "attached stderr"
        );

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(!logged.contains("logs|--stdout"), "{logged}");
        assert!(!logged.contains("logs|--stderr"), "{logged}");
    }

    #[test]
    fn execute_waits_for_container_exit_after_completion_summary_marker() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-summary-gate");
        fs::create_dir_all(&workspace_dir).unwrap();
        let summary_path = workspace_dir.join("output/scan-summary.json");

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _summary_path = EnvVarGuard::set(
            "FAKE_COMPLETION_SUMMARY_PATH",
            summary_path.to_str().unwrap(),
        );
        let _wait_exit = EnvVarGuard::set("FAKE_WAIT_EXIT_CODE", "0");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
            timeout_seconds: 30,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: Some("output/scan-summary.json".to_string()),
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 0);
        assert!(summary_path.is_file());

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("start|container-xyz"), "{logged}");
        assert!(logged.contains("wait|container-xyz"), "{logged}");
        assert!(logged.contains("rm|-f container-xyz"), "{logged}");
        assert!(!logged.contains("start|-a"), "{logged}");
        assert!(!logged.contains("stop|-t 2 container-xyz"), "{logged}");
        assert!(!logged.contains("logs|--stdout"), "{logged}");
        assert!(!logged.contains("logs|--stderr"), "{logged}");
    }

    #[test]
    fn poll_summary_gate_waits_briefly_for_post_exit_summary_flush() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-summary-race");
        fs::create_dir_all(&workspace_dir).unwrap();
        let summary_path = workspace_dir.join("output/scan-summary.json");

        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _post_exit_grace = EnvVarGuard::set("Argus_SUMMARY_GATE_POST_EXIT_GRACE_MS", "200");

        let summary_path_for_writer = summary_path.clone();
        let writer = thread::spawn(move || {
            thread::sleep(Duration::from_millis(50));
            fs::create_dir_all(summary_path_for_writer.parent().unwrap()).unwrap();
            fs::write(summary_path_for_writer, "{\"status\":\"scan_completed\"}\n").unwrap();
        });

        let outcome = poll_summary_gate(
            fake_docker.to_str().unwrap(),
            "container-xyz",
            &summary_path,
            Some(Duration::from_secs(1)),
        )
        .unwrap();

        writer.join().unwrap();

        assert!(
            outcome.summary_observed,
            "summary should still be observed when it flushes immediately after container exit"
        );
        assert!(!outcome.timed_out);
    }

    #[test]
    fn execute_summary_observed_does_not_override_unexpected_exit() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-unexpected-exit");
        fs::create_dir_all(&workspace_dir).unwrap();
        let summary_path = workspace_dir.join("output/scan-summary.json");

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _summary_path = EnvVarGuard::set(
            "FAKE_COMPLETION_SUMMARY_PATH",
            summary_path.to_str().unwrap(),
        );
        let _wait_exit = EnvVarGuard::set("FAKE_WAIT_EXIT_CODE", "143");
        let _stderr = EnvVarGuard::set("FAKE_STDERR", "unexpected detached stderr");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
            timeout_seconds: 30,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: Some("output/scan-summary.json".to_string()),
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(!result.success);
        assert_eq!(result.exit_code, 143);
        assert!(
            result
                .error
                .as_deref()
                .is_some_and(|error| error.contains("scanner container exited with code 143")),
            "{result:?}"
        );
        assert!(
            result
                .stderr_path
                .as_ref()
                .is_some_and(|path| fs::read_to_string(path)
                    .unwrap()
                    .contains("unexpected detached stderr")),
            "{result:?}"
        );

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("wait|container-xyz"), "{logged}");
        assert!(!logged.contains("stop|-t 2 container-xyz"), "{logged}");
        assert!(logged.contains("logs|--stderr"), "{logged}");
    }

    #[test]
    fn execute_summary_gate_wait_has_bounded_cleanup_timeout() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-wait-timeout");
        fs::create_dir_all(&workspace_dir).unwrap();
        let summary_path = workspace_dir.join("output/scan-summary.json");

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _summary_path = EnvVarGuard::set(
            "FAKE_COMPLETION_SUMMARY_PATH",
            summary_path.to_str().unwrap(),
        );
        let _wait_sleep = EnvVarGuard::set("FAKE_WAIT_SLEEP", "2");
        let _wait_timeout = EnvVarGuard::set("Argus_SUMMARY_GATE_EXIT_TIMEOUT_SECONDS", "1");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: Some("output/scan-summary.json".to_string()),
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(!result.success);
        assert!(
            result
                .error
                .as_deref()
                .is_some_and(|error| error.contains("docker wait timed out after summary gate")),
            "{result:?}"
        );

        let logged = fs::read_to_string(&fake_log).unwrap();
        assert!(logged.contains("wait|container-xyz"), "{logged}");
        assert!(logged.contains("rm|-f container-xyz"), "{logged}");
        assert!(!logged.contains("stop|-t 2 container-xyz"), "{logged}");
    }

    #[test]
    fn execute_requires_completion_summary_for_summary_gated_success() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);
        let workspace_root = temp_dir.path().join("scan-root");
        let workspace_dir = workspace_root.join("opengrep/task-missing-summary");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _workspace_root =
            EnvVarGuard::set("SCAN_WORKSPACE_ROOT", workspace_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");
        let _stdout = EnvVarGuard::set("FAKE_STDOUT", "detached stdout without summary");

        let result = execute(RunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "Argus/opengrep-runner-local:latest".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string(), "--self-test".to_string()],
            timeout_seconds: 30,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            artifact_paths: vec![],
            capture_stdout_path: None,
            capture_stderr_path: None,
            completion_summary_path: Some("output/scan-summary.json".to_string()),
            workspace_root_override: None,
            memory_limit_mb: None,
            memory_swap_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
        });

        assert!(!result.success);
        assert_eq!(result.exit_code, 0);
        assert!(
            result
                .error
                .as_deref()
                .is_some_and(|error| error.contains("completion summary was not observed")),
            "{result:?}"
        );
        assert!(
            result
                .stdout_path
                .as_ref()
                .is_some_and(|path| fs::read_to_string(path)
                    .unwrap()
                    .contains("detached stdout without summary")),
            "{result:?}"
        );
    }

    #[test]
    fn stop_container_handles_missing_container_gracefully() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_docker_script(&temp_dir);

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _inspect_missing = EnvVarGuard::set("FAKE_INSPECT_MISSING", "1");

        assert!(!stop_container_sync("missing-container"));
    }
}
