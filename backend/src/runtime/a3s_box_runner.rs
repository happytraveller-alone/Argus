use anyhow::{bail, Context, Result};
use flate2::{write::GzEncoder, Compression, GzBuilder};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    env, fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{LazyLock, Mutex},
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

use crate::core::hex;

const MAX_RETAINED_LOG_CHARS: usize = 12_000;
/// Byte cap for stdout/stderr of management commands (image-inspect, rm, save, load, info).
/// These produce small outputs; 1 MiB is generous while still bounding heap.
const MGMT_CMD_OUTPUT_LIMIT_BYTES: usize = 1_048_576;
const SCANNER_MOUNT_PATH: &str = "/scan";
const DEFAULT_A3S_BOX_BIN: &str = "a3s-box";
const DEFAULT_A3S_BOX_TIMEOUT_SECONDS: u64 = 900;
const DEFAULT_A3S_BOX_STARTUP_TIMEOUT_SECONDS: u64 = 45;
const DEFAULT_A3S_BOX_RUNNER_ROOT: &str = "/tmp/argus/a3s-box-runs";
const DEFAULT_CONTAINER_CLI_BIN: &str = "docker";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct A3sBoxRunnerSpec {
    #[serde(default)]
    pub task_id: Option<String>,
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
    /// When true, run the workload with the official `a3s-box run
    /// --network none` mode. When false, omit `--network` and let A3S Box use
    /// its default TSI networking. Keeping this as a runner-level flag lets
    /// OpenGrep stay offline today while future intelligent workloads can opt
    /// into the default outbound-capable mode without a separate runner.
    pub network_disabled: bool,
    /// Maximum bytes captured from a3s-box subprocess stdout.
    /// Defaults to 1 MiB. Excess output is replaced by a sentinel suffix.
    #[serde(default = "default_a3s_box_stdout_limit_bytes")]
    pub stdout_limit_bytes: usize,
    /// Maximum bytes captured from a3s-box subprocess stderr.
    /// Defaults to 1 MiB. Excess output is replaced by a sentinel suffix.
    #[serde(default = "default_a3s_box_stderr_limit_bytes")]
    pub stderr_limit_bytes: usize,
    /// Upper bound (bytes) on the workspace source directory for which the
    /// opengrep command is rewritten to copy source into the box-local
    /// `/tmp/argus-a3s-opengrep-{box_name}` (tmpfs) for faster reads.
    /// Workspaces above this size run opengrep directly against the
    /// virtiofs-mounted host workspace instead — this avoids the OOM that
    /// the tmpfs copy would otherwise cause on a memory-capped box (e.g.
    /// FFMPEG-scale projects). `None` keeps the legacy unconditional
    /// localization behaviour.
    #[serde(default)]
    pub localize_max_source_bytes: Option<u64>,
}

fn default_a3s_box_stdout_limit_bytes() -> usize {
    1_048_576
}

fn default_a3s_box_stderr_limit_bytes() -> usize {
    1_048_576
}

impl Default for A3sBoxRunnerSpec {
    fn default() -> Self {
        Self {
            scanner_type: String::new(),
            task_id: None,
            image: String::new(),
            workspace_dir: String::new(),
            command: Vec::new(),
            timeout_seconds: 0,
            env: BTreeMap::new(),
            expected_exit_codes: default_expected_exit_codes(),
            capture_stdout_path: None,
            capture_stderr_path: None,
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
            stdout_limit_bytes: default_a3s_box_stdout_limit_bytes(),
            stderr_limit_bytes: default_a3s_box_stderr_limit_bytes(),
            localize_max_source_bytes: None,
        }
    }
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

static ACTIVE_A3S_BOXES: LazyLock<Mutex<HashMap<String, String>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

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

fn a3s_home_dir() -> Option<PathBuf> {
    env::var_os("A3S_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".a3s")))
}

fn a3s_box_cleanup_timeout() -> u64 {
    env::var("A3S_BOX_CLEANUP_TIMEOUT_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(30)
}

fn a3s_box_startup_timeout() -> u64 {
    env::var("A3S_BOX_STARTUP_TIMEOUT_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u64>().ok())
        .unwrap_or(DEFAULT_A3S_BOX_STARTUP_TIMEOUT_SECONDS)
}

fn a3s_box_auto_load_docker_image() -> bool {
    env::var("A3S_BOX_AUTO_LOAD_DOCKER_IMAGE")
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(true)
}

fn container_cli_bin() -> String {
    env::var("CONTAINER_CLI")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| DEFAULT_CONTAINER_CLI_BIN.to_string())
}

fn register_active_task_box(task_id: Option<&str>, box_name: &str) {
    let Some(task_id) = task_id else {
        return;
    };
    ACTIVE_A3S_BOXES
        .lock()
        .expect("active a3s-box registry")
        .insert(task_id.to_string(), box_name.to_string());
}

fn unregister_active_task_box(task_id: Option<&str>, box_name: &str) {
    let Some(task_id) = task_id else {
        return;
    };
    let mut active = ACTIVE_A3S_BOXES.lock().expect("active a3s-box registry");
    if active
        .get(task_id)
        .is_some_and(|current| current == box_name)
    {
        active.remove(task_id);
    }
}

pub fn stop_active_task_sync(task_id: &str) -> bool {
    let box_name = ACTIVE_A3S_BOXES
        .lock()
        .expect("active a3s-box registry")
        .get(task_id)
        .cloned();
    match box_name {
        Some(box_name) => {
            let stopped = stop_box_sync(&box_name);
            if stopped {
                unregister_active_task_box(Some(task_id), &box_name);
            }
            stopped
        }
        None => false,
    }
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

/// Read at most `limit` bytes from `reader` into a newly allocated `Vec<u8>`.
/// If the stream contains more than `limit` bytes a sentinel suffix is appended
/// so the truncation is visible in debug logs.
fn read_limited(mut reader: impl std::io::Read, limit: usize) -> std::io::Result<Vec<u8>> {
    let cap = limit.min(64 * 1024);
    let mut bytes = Vec::with_capacity(cap);
    reader.by_ref().take(limit as u64).read_to_end(&mut bytes)?;
    if bytes.len() == limit {
        // Attempt to detect whether the stream had more data by reading one
        // additional byte.  If we get one the output was indeed truncated.
        let mut probe = [0u8; 1];
        if reader.read(&mut probe).unwrap_or(0) > 0 {
            let sentinel = format!("...[a3s-box output truncated to {limit} bytes]");
            bytes.extend_from_slice(sentinel.as_bytes());
        }
    }
    Ok(bytes)
}

/// Capture stdout and stderr of a subprocess with per-stream byte limits.
///
/// # Parameters
/// - `stdout_limit_bytes`: maximum bytes captured from stdout; excess is
///   replaced by a sentinel suffix so truncation is visible in logs.
/// - `stderr_limit_bytes`: same for stderr.
fn run_command_capture(
    binary: &str,
    args: &[String],
    timeout: Option<Duration>,
    stdout_limit_bytes: usize,
    stderr_limit_bytes: usize,
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
        read_limited(stdout, stdout_limit_bytes).context("read a3s-box stdout")
    });
    let stderr_handle = thread::spawn(move || -> Result<Vec<u8>> {
        read_limited(stderr, stderr_limit_bytes).context("read a3s-box stderr")
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

fn a3s_box_workload_exec_ready(binary: &str, box_name: &str) -> Result<(), String> {
    let args = vec!["top".to_string(), box_name.to_string()];
    let capture = run_command_capture(
        binary,
        &args,
        Some(Duration::from_secs(5)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    )
    .map_err(|error| error.to_string())?;
    if command_succeeded(&capture) {
        Ok(())
    } else {
        Err(command_failed_text(&capture))
    }
}

fn run_a3s_box_workload_capture(
    binary: &str,
    args: &[String],
    timeout: Option<Duration>,
    stdout_limit_bytes: usize,
    stderr_limit_bytes: usize,
    box_name: &str,
    startup_timeout: Duration,
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
        read_limited(stdout, stdout_limit_bytes).context("read a3s-box stdout")
    });
    let stderr_handle = thread::spawn(move || -> Result<Vec<u8>> {
        read_limited(stderr, stderr_limit_bytes).context("read a3s-box stderr")
    });

    let started_at = Instant::now();
    let mut timed_out = false;
    let mut startup_ready = startup_timeout.is_zero();
    let mut last_probe_at = Instant::now()
        .checked_sub(Duration::from_secs(5))
        .unwrap_or_else(Instant::now);
    let mut last_probe_error = String::new();
    let mut timeout_detail = String::new();
    let exit_status = loop {
        if let Some(status) = child.try_wait().context("poll a3s-box child status")? {
            if !startup_ready && last_probe_error.contains("Exec socket not found") {
                timed_out = true;
                timeout_detail = format!(
                    "a3s-box run exited before exec socket became ready; status={:?}; last_probe={}",
                    status.code(),
                    if last_probe_error.trim().is_empty() {
                        "no probe output"
                    } else {
                        last_probe_error.trim()
                    }
                );
                cleanup_box(binary, Some(box_name));
            }
            break Some(status);
        }

        let elapsed = started_at.elapsed();
        if !startup_ready && last_probe_at.elapsed() >= Duration::from_secs(2) {
            last_probe_at = Instant::now();
            match a3s_box_workload_exec_ready(binary, box_name) {
                Ok(()) => startup_ready = true,
                Err(error) => last_probe_error = error,
            }
        }
        if !startup_ready && elapsed >= startup_timeout {
            timed_out = true;
            timeout_detail = format!(
                "a3s-box startup timed out after {}s before exec socket became ready; last_probe={}",
                startup_timeout.as_secs(),
                if last_probe_error.trim().is_empty() {
                    "no probe output"
                } else {
                    last_probe_error.trim()
                }
            );
            let _ = child.kill();
            cleanup_box(binary, Some(box_name));
            break child.wait().ok();
        }
        if timeout.is_some_and(|limit| elapsed >= limit) {
            timed_out = true;
            timeout_detail = format!(
                "a3s-box run timed out after {}s",
                timeout
                    .map(|d| d.as_secs())
                    .unwrap_or(DEFAULT_A3S_BOX_TIMEOUT_SECONDS)
            );
            let _ = child.kill();
            cleanup_box(binary, Some(box_name));
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
    let mut stderr = String::from_utf8_lossy(
        &stderr_handle
            .join()
            .map_err(|_| anyhow::anyhow!("join a3s-box stderr reader"))??,
    )
    .to_string();
    if !timeout_detail.is_empty() {
        if !stderr.ends_with('\n') && !stderr.is_empty() {
            stderr.push('\n');
        }
        stderr.push_str(&timeout_detail);
        stderr.push('\n');
    }

    Ok(CommandCapture {
        timed_out,
        status_code: exit_status.and_then(|status| status.code()),
        stdout,
        stderr,
    })
}

fn command_failed_text(capture: &CommandCapture) -> String {
    let stderr = capture.stderr.trim();
    if !stderr.is_empty() {
        return stderr.to_string();
    }
    let stdout = capture.stdout.trim();
    if !stdout.is_empty() {
        return stdout.to_string();
    }
    match capture.status_code {
        Some(code) => format!("exit code {code}"),
        None => "process terminated without an exit code".to_string(),
    }
}

fn command_succeeded(capture: &CommandCapture) -> bool {
    !capture.timed_out && capture.status_code == Some(0)
}

fn a3s_box_virtualization_error_text(stdout: &str, stderr: &str) -> Option<String> {
    let combined = format!("{stdout}\n{stderr}");
    for needle in [
        "Virtualization: not available",
        "KVM is not available",
        "Error creating the Kvm object",
        "Exec socket did not appear",
    ] {
        if combined.contains(needle) {
            return Some(needle.to_string());
        }
    }
    None
}

fn a3s_box_image_inspect(binary: &str, image: &str) -> Option<CommandCapture> {
    let args = vec!["image-inspect".to_string(), image.to_string()];
    run_command_capture(
        binary,
        &args,
        Some(Duration::from_secs(30)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    )
    .ok()
    .filter(command_succeeded)
}

fn digest_sha256_hex(digest: &str) -> Option<&str> {
    let value = digest.strip_prefix("sha256:")?;
    if value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Some(value)
    } else {
        None
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    hex::encode_lower(digest)
}

fn gzip_bytes_for_oci_layer(bytes: &[u8]) -> Result<Vec<u8>> {
    let mut encoder: GzEncoder<Vec<u8>> = GzBuilder::new()
        .mtime(0)
        .write(Vec::new(), Compression::default());
    encoder.write_all(bytes).context("gzip OCI layer bytes")?;
    encoder.finish().context("finish gzip OCI layer")
}

fn append_path_recursive(
    builder: &mut tar::Builder<fs::File>,
    base_dir: &Path,
    path: &Path,
) -> Result<()> {
    let relative_path = path
        .strip_prefix(base_dir)
        .with_context(|| format!("derive archive path for {}", path.display()))?;
    if relative_path.as_os_str().is_empty() {
        return Ok(());
    }
    let metadata =
        fs::metadata(path).with_context(|| format!("stat archive path: {}", path.display()))?;
    if metadata.is_dir() {
        builder
            .append_dir(relative_path, path)
            .with_context(|| format!("append archive dir: {}", relative_path.display()))?;
        let mut children = fs::read_dir(path)
            .with_context(|| format!("read archive dir: {}", path.display()))?
            .collect::<std::result::Result<Vec<_>, _>>()
            .with_context(|| format!("collect archive dir entries: {}", path.display()))?;
        children.sort_by_key(|entry| entry.path());
        for child in children {
            append_path_recursive(builder, base_dir, &child.path())?;
        }
    } else if metadata.is_file() {
        builder
            .append_path_with_name(path, relative_path)
            .with_context(|| format!("append archive file: {}", relative_path.display()))?;
    }
    Ok(())
}

fn convert_docker_archive_to_a3s_oci_archive(input_path: &Path, output_path: &Path) -> Result<()> {
    let work_dir = tempfile::Builder::new()
        .prefix("argus-a3s-oci-")
        .tempdir()
        .context("create temporary OCI conversion directory")?;

    let input = fs::File::open(input_path)
        .with_context(|| format!("open Docker image archive: {}", input_path.display()))?;
    let mut archive = tar::Archive::new(input);
    archive
        .unpack(work_dir.path())
        .with_context(|| format!("unpack Docker image archive: {}", input_path.display()))?;

    let blobs_dir = work_dir.path().join("blobs").join("sha256");
    let index_path = work_dir.path().join("index.json");
    let index_bytes = fs::read(&index_path).with_context(|| {
        format!(
            "read OCI index from Docker archive: {}",
            index_path.display()
        )
    })?;
    let mut index_json: serde_json::Value =
        serde_json::from_slice(&index_bytes).context("parse OCI index from Docker archive")?;
    let manifests = index_json
        .get_mut("manifests")
        .and_then(serde_json::Value::as_array_mut)
        .context("OCI index missing manifests array")?;

    for manifest_entry in manifests {
        let manifest_digest = manifest_entry
            .get("digest")
            .and_then(serde_json::Value::as_str)
            .and_then(digest_sha256_hex)
            .context("OCI index manifest digest must be sha256")?
            .to_string();
        let manifest_path = blobs_dir.join(&manifest_digest);
        let manifest_bytes = fs::read(&manifest_path)
            .with_context(|| format!("read OCI manifest blob: {}", manifest_path.display()))?;
        let mut manifest_json: serde_json::Value =
            serde_json::from_slice(&manifest_bytes).context("parse OCI manifest blob")?;
        let layers = manifest_json
            .get_mut("layers")
            .and_then(serde_json::Value::as_array_mut)
            .context("OCI manifest missing layers array")?;

        let mut manifest_changed = false;
        for layer in layers {
            let media_type = layer
                .get("mediaType")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            let is_uncompressed_layer = matches!(
                media_type,
                "application/vnd.oci.image.layer.v1.tar"
                    | "application/vnd.docker.image.rootfs.diff.tar"
            );
            if !is_uncompressed_layer {
                continue;
            }

            let layer_digest = layer
                .get("digest")
                .and_then(serde_json::Value::as_str)
                .and_then(digest_sha256_hex)
                .context("OCI layer digest must be sha256")?
                .to_string();
            let layer_path = blobs_dir.join(&layer_digest);
            let layer_bytes = fs::read(&layer_path)
                .with_context(|| format!("read OCI layer blob: {}", layer_path.display()))?;
            let gzipped_layer = gzip_bytes_for_oci_layer(&layer_bytes)?;
            let gzipped_digest = sha256_hex(&gzipped_layer);
            let gzipped_path = blobs_dir.join(&gzipped_digest);
            fs::write(&gzipped_path, &gzipped_layer)
                .with_context(|| format!("write gzipped OCI layer: {}", gzipped_path.display()))?;
            if gzipped_path != layer_path {
                let _ = fs::remove_file(&layer_path);
            }

            layer["mediaType"] =
                serde_json::Value::String("application/vnd.oci.image.layer.v1.tar+gzip".into());
            layer["digest"] = serde_json::Value::String(format!("sha256:{gzipped_digest}"));
            layer["size"] =
                serde_json::Value::Number(serde_json::Number::from(gzipped_layer.len() as u64));
            manifest_changed = true;
        }

        if manifest_changed {
            let updated_manifest =
                serde_json::to_vec(&manifest_json).context("serialize updated OCI manifest")?;
            let updated_digest = sha256_hex(&updated_manifest);
            let updated_manifest_path = blobs_dir.join(&updated_digest);
            fs::write(&updated_manifest_path, &updated_manifest).with_context(|| {
                format!(
                    "write updated OCI manifest: {}",
                    updated_manifest_path.display()
                )
            })?;
            if updated_manifest_path != manifest_path {
                let _ = fs::remove_file(&manifest_path);
            }
            manifest_entry["digest"] =
                serde_json::Value::String(format!("sha256:{updated_digest}"));
            manifest_entry["size"] =
                serde_json::Value::Number(serde_json::Number::from(updated_manifest.len() as u64));
        }
    }

    fs::write(
        &index_path,
        serde_json::to_vec(&index_json).context("serialize updated OCI index")?,
    )
    .with_context(|| format!("write updated OCI index: {}", index_path.display()))?;
    let _ = fs::remove_file(work_dir.path().join("manifest.json"));
    let _ = fs::remove_file(work_dir.path().join("repositories"));

    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create OCI archive parent: {}", parent.display()))?;
    }
    let output = fs::File::create(output_path).with_context(|| {
        format!(
            "create A3S-compatible OCI archive: {}",
            output_path.display()
        )
    })?;
    let mut builder = tar::Builder::new(output);
    for relative in ["oci-layout", "index.json", "blobs"] {
        append_path_recursive(
            &mut builder,
            work_dir.path(),
            &work_dir.path().join(relative),
        )?;
    }
    builder.finish().with_context(|| {
        format!(
            "finish A3S-compatible OCI archive: {}",
            output_path.display()
        )
    })
}

fn a3s_box_cached_image_needs_reload(inspect_stdout: &str) -> Result<bool> {
    let inspect_json: serde_json::Value =
        serde_json::from_str(inspect_stdout).context("parse a3s-box image-inspect JSON")?;
    let digest = inspect_json
        .get("Digest")
        .and_then(serde_json::Value::as_str)
        .and_then(digest_sha256_hex)
        .context("a3s-box image-inspect JSON missing sha256 Digest")?;
    let Some(home_dir) = a3s_home_dir() else {
        return Ok(false);
    };
    let cache_dir = home_dir.join("images").join("sha256").join(digest);
    if !cache_dir.exists() {
        return Ok(false);
    }
    if cache_dir.join("manifest.json").exists() || cache_dir.join("repositories").exists() {
        return Ok(true);
    }
    let index_path = cache_dir.join("index.json");
    if !index_path.exists() {
        return Ok(false);
    }

    let index_json: serde_json::Value = serde_json::from_slice(
        &fs::read(&index_path)
            .with_context(|| format!("read cached a3s-box OCI index: {}", index_path.display()))?,
    )
    .context("parse cached a3s-box OCI index")?;
    let Some(manifests) = index_json
        .get("manifests")
        .and_then(serde_json::Value::as_array)
    else {
        return Ok(true);
    };
    for manifest_entry in manifests {
        let Some(manifest_digest) = manifest_entry
            .get("digest")
            .and_then(serde_json::Value::as_str)
            .and_then(digest_sha256_hex)
        else {
            return Ok(true);
        };
        let manifest_path = cache_dir.join("blobs").join("sha256").join(manifest_digest);
        let manifest_json: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest_path).with_context(|| {
                format!(
                    "read cached a3s-box OCI manifest: {}",
                    manifest_path.display()
                )
            })?)
            .context("parse cached a3s-box OCI manifest")?;
        let Some(layers) = manifest_json
            .get("layers")
            .and_then(serde_json::Value::as_array)
        else {
            return Ok(true);
        };
        for layer in layers {
            if matches!(
                layer
                    .get("mediaType")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default(),
                "application/vnd.oci.image.layer.v1.tar"
                    | "application/vnd.docker.image.rootfs.diff.tar"
            ) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn a3s_box_image_cached(binary: &str, image: &str) -> bool {
    let Some(capture) = a3s_box_image_inspect(binary, image) else {
        return false;
    };
    !a3s_box_cached_image_needs_reload(&capture.stdout).unwrap_or(false)
}

fn a3s_box_cache_marker_name(image: &str) -> String {
    image
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-') {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn a3s_box_argus_marker_dir() -> Option<PathBuf> {
    a3s_home_dir().map(|home| home.join("argus").join("source-images"))
}

fn read_trimmed_file(path: &Path) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
}

fn write_marker_file(path: &Path, value: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create a3s-box marker parent: {}", parent.display()))?;
    }
    fs::write(path, format!("{value}\n"))
        .with_context(|| format!("write a3s-box marker: {}", path.display()))
}

fn remove_a3s_box_rootfs_cache_for_image(image: &str) -> Result<usize> {
    let Some(home_dir) = a3s_home_dir() else {
        return Ok(0);
    };
    let cache_dir = home_dir.join("cache").join("rootfs");
    if !cache_dir.is_dir() {
        return Ok(0);
    }

    let mut removed = 0;
    for entry in fs::read_dir(&cache_dir)
        .with_context(|| format!("read a3s-box rootfs cache dir: {}", cache_dir.display()))?
    {
        let entry = entry.with_context(|| {
            format!(
                "read a3s-box rootfs cache entry under {}",
                cache_dir.display()
            )
        })?;
        let meta_path = entry.path();
        if !meta_path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.ends_with(".meta.json"))
        {
            continue;
        }
        let meta_json: serde_json::Value =
            match serde_json::from_slice(&fs::read(&meta_path).with_context(|| {
                format!(
                    "read a3s-box rootfs cache metadata: {}",
                    meta_path.display()
                )
            })?) {
                Ok(value) => value,
                Err(_) => continue,
            };
        if meta_json
            .get("description")
            .and_then(serde_json::Value::as_str)
            != Some(image)
        {
            continue;
        }
        let key = meta_json
            .get("key")
            .and_then(serde_json::Value::as_str)
            .map(str::to_string)
            .or_else(|| {
                meta_path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .and_then(|name| name.strip_suffix(".meta.json"))
                    .map(str::to_string)
            });
        if let Some(key) = key {
            let rootfs_path = cache_dir.join(key);
            if rootfs_path.exists() {
                fs::remove_dir_all(&rootfs_path).with_context(|| {
                    format!(
                        "remove stale a3s-box rootfs cache: {}",
                        rootfs_path.display()
                    )
                })?;
            }
        }
        let _ = fs::remove_file(&meta_path);
        removed += 1;
    }
    Ok(removed)
}

fn docker_image_id(container_cli: &str, image: &str) -> Option<String> {
    let args = vec![
        "image".to_string(),
        "inspect".to_string(),
        "--format".to_string(),
        "{{.Id}}".to_string(),
        image.to_string(),
    ];
    let capture = run_command_capture(
        container_cli,
        &args,
        Some(Duration::from_secs(30)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    )
    .ok()?;
    if !command_succeeded(&capture) {
        return None;
    }
    let image_id = capture.stdout.trim();
    (!image_id.is_empty()).then(|| image_id.to_string())
}

fn legacy_docker_image_source(image: &str) -> Option<String> {
    image
        .strip_prefix("argus/")
        .map(|rest| format!("Argus/{rest}"))
}

fn ensure_a3s_box_image_cached(binary: &str, image: &str, meta_dir: &Path) -> Result<()> {
    let container_cli = container_cli_bin();
    let mut source_image = image.to_string();
    let mut source_image_id = docker_image_id(&container_cli, &source_image);
    if source_image_id.is_none() {
        if let Some(legacy_source) = legacy_docker_image_source(image) {
            if let Some(legacy_id) = docker_image_id(&container_cli, &legacy_source) {
                source_image_id = Some(legacy_id);
                source_image = legacy_source;
            }
        }
    }

    let mut force_reload = false;
    if let (Some(marker_dir), Some(source_id)) =
        (a3s_box_argus_marker_dir(), source_image_id.as_deref())
    {
        let marker_name = a3s_box_cache_marker_name(image);
        let image_marker = marker_dir.join(format!("{marker_name}.id"));
        let rootfs_marker = marker_dir.join(format!("{marker_name}.rootfs.id"));
        if read_trimmed_file(&rootfs_marker).as_deref() != Some(source_id) {
            remove_a3s_box_rootfs_cache_for_image(image)?;
            write_marker_file(&rootfs_marker, source_id)?;
        }
        if read_trimmed_file(&image_marker).as_deref() != Some(source_id) {
            force_reload = true;
        }
    }

    if a3s_box_image_cached(binary, image) && !force_reload {
        return Ok(());
    }
    if !a3s_box_auto_load_docker_image() {
        return Ok(());
    }

    if source_image_id.is_none() {
        let inspect_args = vec![
            "image".to_string(),
            "inspect".to_string(),
            source_image.clone(),
        ];
        let inspect = run_command_capture(
            &container_cli,
            &inspect_args,
            Some(Duration::from_secs(30)),
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
        )
        .unwrap_or(CommandCapture {
            timed_out: false,
            status_code: Some(1),
            stdout: String::new(),
            stderr: String::new(),
        });
        if !command_succeeded(&inspect) {
            if let Some(legacy_source) = legacy_docker_image_source(image) {
                let legacy_inspect_args = vec![
                    "image".to_string(),
                    "inspect".to_string(),
                    legacy_source.clone(),
                ];
                let legacy_inspect = run_command_capture(
                    &container_cli,
                    &legacy_inspect_args,
                    Some(Duration::from_secs(30)),
                    MGMT_CMD_OUTPUT_LIMIT_BYTES,
                    MGMT_CMD_OUTPUT_LIMIT_BYTES,
                )
                .unwrap_or(CommandCapture {
                    timed_out: false,
                    status_code: Some(1),
                    stdout: String::new(),
                    stderr: String::new(),
                });
                if !command_succeeded(&legacy_inspect) {
                    return Ok(());
                }
                source_image = legacy_source;
            } else {
                return Ok(());
            }
        }
    }

    remove_a3s_box_rootfs_cache_for_image(image)?;
    let rmi_args = vec!["rmi".to_string(), image.to_string()];
    let _ = run_command_capture(
        binary,
        &rmi_args,
        Some(Duration::from_secs(60)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    );

    if source_image_id.is_none() {
        source_image_id = docker_image_id(&container_cli, &source_image);
    }

    if source_image_id.is_none() {
        let inspect_args = vec![
            "image".to_string(),
            "inspect".to_string(),
            source_image.clone(),
        ];
        let inspect = run_command_capture(
            &container_cli,
            &inspect_args,
            Some(Duration::from_secs(30)),
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
        )
        .unwrap_or(CommandCapture {
            timed_out: false,
            status_code: Some(1),
            stdout: String::new(),
            stderr: String::new(),
        });
        if !command_succeeded(&inspect) {
            if let Some(legacy_source) = legacy_docker_image_source(image) {
                let legacy_inspect_args = vec![
                    "image".to_string(),
                    "inspect".to_string(),
                    legacy_source.clone(),
                ];
                let legacy_inspect = run_command_capture(
                    &container_cli,
                    &legacy_inspect_args,
                    Some(Duration::from_secs(30)),
                    MGMT_CMD_OUTPUT_LIMIT_BYTES,
                    MGMT_CMD_OUTPUT_LIMIT_BYTES,
                )
                .unwrap_or(CommandCapture {
                    timed_out: false,
                    status_code: Some(1),
                    stdout: String::new(),
                    stderr: String::new(),
                });
                if !command_succeeded(&legacy_inspect) {
                    return Ok(());
                }
                source_image = legacy_source;
            } else {
                return Ok(());
            }
        }
    }

    let docker_tar_path = meta_dir.join(format!("a3s-box-image-docker-{}.tar", Uuid::new_v4()));
    let oci_tar_path = meta_dir.join(format!("a3s-box-image-oci-{}.tar", Uuid::new_v4()));
    let mut save_args = vec![
        "save".to_string(),
        source_image,
        "-o".to_string(),
        docker_tar_path.display().to_string(),
    ];
    if container_cli.contains("podman") {
        save_args.insert(1, "--format".to_string());
        save_args.insert(2, "oci-archive".to_string());
    }
    let save = run_command_capture(
        &container_cli,
        &save_args,
        Some(Duration::from_secs(300)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    )
    .with_context(|| format!("save Docker image for a3s-box cache: {image}"))?;
    if !command_succeeded(&save) {
        let _ = fs::remove_file(&docker_tar_path);
        bail!(
            "save Docker image for a3s-box cache failed: {}",
            command_failed_text(&save)
        );
    }
    convert_docker_archive_to_a3s_oci_archive(&docker_tar_path, &oci_tar_path)
        .with_context(|| format!("convert Docker image archive to A3S-compatible OCI: {image}"))?;
    let _ = fs::remove_file(&docker_tar_path);

    let load_args = vec![
        "load".to_string(),
        "-i".to_string(),
        oci_tar_path.display().to_string(),
        "--tag".to_string(),
        image.to_string(),
    ];
    let load = run_command_capture(
        binary,
        &load_args,
        Some(Duration::from_secs(300)),
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
    )
    .with_context(|| format!("load Docker image into a3s-box cache: {image}"))?;
    let _ = fs::remove_file(&oci_tar_path);
    if !command_succeeded(&load) {
        bail!(
            "load Docker image into a3s-box cache failed: {}",
            command_failed_text(&load)
        );
    }

    if !a3s_box_image_cached(binary, image) {
        bail!("a3s-box image cache did not retain loaded image: {image}");
    }
    if let (Some(marker_dir), Some(source_id)) =
        (a3s_box_argus_marker_dir(), source_image_id.as_deref())
    {
        let marker_name = a3s_box_cache_marker_name(image);
        write_marker_file(&marker_dir.join(format!("{marker_name}.id")), source_id)?;
        write_marker_file(
            &marker_dir.join(format!("{marker_name}.rootfs.id")),
            source_id,
        )?;
    }
    Ok(())
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

fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".to_string();
    }
    let mut quoted = String::from("'");
    for ch in value.chars() {
        if ch == '\'' {
            quoted.push_str("'\\''");
        } else {
            quoted.push(ch);
        }
    }
    quoted.push('\'');
    quoted
}

fn shell_command_array(command: &[String]) -> String {
    command
        .iter()
        .map(|value| shell_quote(value))
        .collect::<Vec<_>>()
        .join(" ")
}

fn is_workspace_path(value: &str, workspace: &Path) -> bool {
    let path = Path::new(value);
    path.is_absolute() && (path == workspace || path.starts_with(workspace))
}

/// Returns the value passed to `--target` in an opengrep-scan invocation, or
/// `None` if absent. Used by the localization size gate to measure the source
/// directory before deciding whether to copy it into box-local tmpfs.
fn extract_opengrep_target(command: &[String]) -> Option<&str> {
    let mut idx = 0;
    while idx + 1 < command.len() {
        if command[idx] == "--target" {
            return Some(command[idx + 1].as_str());
        }
        idx += 1;
    }
    None
}

fn local_file_path(local_root: &str, original_path: &str, fallback_name: &str) -> String {
    let file_name = Path::new(original_path)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .unwrap_or(fallback_name);
    format!("{local_root}/output/{file_name}")
}

/// Walk `dir` recursively, summing regular-file sizes. Returns early once the
/// running total strictly exceeds `cap_bytes` — the caller does not need an
/// exact size, only a yes/no answer to "is this directory bigger than the
/// localization limit?". Symlinks and other non-regular entries are ignored;
/// IO errors are treated as zero-cost (i.e. we err on the side of localizing
/// when the source dir is unreadable, matching legacy behaviour).
fn measured_dir_size_capped(dir: &Path, cap_bytes: u64) -> u64 {
    let mut total: u64 = 0;
    let mut stack: Vec<PathBuf> = vec![dir.to_path_buf()];
    while let Some(current) = stack.pop() {
        let Ok(entries) = fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let Ok(file_type) = entry.file_type() else {
                continue;
            };
            if file_type.is_dir() {
                stack.push(entry.path());
            } else if file_type.is_file() {
                if let Ok(meta) = entry.metadata() {
                    total = total.saturating_add(meta.len());
                    if total > cap_bytes {
                        return total;
                    }
                }
            }
        }
    }
    total
}

/// Localizes opengrep-scan commands by copying workspace inputs into the
/// box-local `/tmp/argus-a3s-opengrep-{box_name}` (tmpfs) for fast reads,
/// then copies output files back to the host-mounted workspace. When the
/// `--target` argument resolves to an existing directory inside the workspace
/// and that directory's recursive size exceeds `localize_max_source_bytes`,
/// localization is skipped and the original command is returned unchanged so
/// opengrep reads source directly via the virtiofs-mounted workspace. This
/// preserves the perf optimisation introduced in commit 22fbb587 for typical
/// projects while avoiding tmpfs OOM on FFMPEG-scale workloads.
fn build_localized_opengrep_command_with_limit(
    command: &[String],
    workspace: &Path,
    box_name: &str,
    localize_max_source_bytes: Option<u64>,
    task_id: Option<&str>,
) -> Vec<String> {
    if command.first().map(String::as_str) != Some("opengrep-scan") {
        return command.to_vec();
    }

    if let Some(limit) = localize_max_source_bytes {
        if limit == 0 {
            tracing::info!(
                stage = "a3s_localize_decision",
                localize = false,
                reason = "limit_zero",
                limit_bytes = limit,
                task_id = task_id.unwrap_or(""),
                "a3s opengrep localization disabled by zero limit"
            );
            return command.to_vec();
        }
        if let Some(target) = extract_opengrep_target(command) {
            let target_path = Path::new(target);
            if target_path.is_absolute()
                && target_path.starts_with(workspace)
                && target_path.is_dir()
            {
                let measured = measured_dir_size_capped(target_path, limit);
                if measured > limit {
                    tracing::info!(
                        stage = "a3s_localize_decision",
                        localize = false,
                        reason = "source_exceeds_limit",
                        source_bytes = measured,
                        limit_bytes = limit,
                        task_id = task_id.unwrap_or(""),
                        "a3s opengrep source dir exceeds localization limit; running on virtiofs mount"
                    );
                    return command.to_vec();
                } else {
                    tracing::info!(
                        stage = "a3s_localize_decision",
                        localize = true,
                        source_bytes = measured,
                        limit_bytes = limit,
                        task_id = task_id.unwrap_or(""),
                        "a3s opengrep localizing workspace source to box-local /tmp"
                    );
                }
            }
        }
    }

    let mut localized = command.to_vec();
    let mut copy_pairs: Vec<(String, String)> = Vec::new();
    let mut copy_back_pairs: Vec<(String, String)> = Vec::new();
    let local_root = format!("/tmp/argus-a3s-opengrep-{box_name}");
    let mut config_index = 0usize;

    let mut index = 0usize;
    while index + 1 < command.len() {
        match command[index].as_str() {
            "--target" => {
                let source = &command[index + 1];
                if is_workspace_path(source, workspace) {
                    let local_source = format!("{local_root}/source");
                    copy_pairs.push((source.clone(), local_source.clone()));
                    localized[index + 1] = local_source;
                }
                index += 2;
            }
            "--config" => {
                let source = &command[index + 1];
                if is_workspace_path(source, workspace) {
                    let local_config = format!("{local_root}/config-{config_index}");
                    config_index += 1;
                    copy_pairs.push((source.clone(), local_config.clone()));
                    localized[index + 1] = local_config;
                }
                index += 2;
            }
            "--manifest" => {
                let source = &command[index + 1];
                if is_workspace_path(source, workspace) {
                    let local_manifest = format!("{local_root}/image-rules.manifest");
                    copy_pairs.push((source.clone(), local_manifest.clone()));
                    localized[index + 1] = local_manifest;
                }
                index += 2;
            }
            "--output" => {
                let target = &command[index + 1];
                if is_workspace_path(target, workspace) {
                    let local_output = local_file_path(&local_root, target, "results.json");
                    copy_back_pairs.push((local_output.clone(), target.clone()));
                    localized[index + 1] = local_output;
                }
                index += 2;
            }
            "--summary" => {
                let target = &command[index + 1];
                if is_workspace_path(target, workspace) {
                    let local_summary = local_file_path(&local_root, target, "summary.json");
                    copy_back_pairs.push((local_summary.clone(), target.clone()));
                    localized[index + 1] = local_summary;
                }
                index += 2;
            }
            "--log" => {
                let target = &command[index + 1];
                if is_workspace_path(target, workspace) {
                    let local_log = local_file_path(&local_root, target, "opengrep.log");
                    copy_back_pairs.push((local_log.clone(), target.clone()));
                    localized[index + 1] = local_log;
                }
                index += 2;
            }
            _ => {
                index += 1;
            }
        }
    }

    if copy_pairs.is_empty() && copy_back_pairs.is_empty() {
        return command.to_vec();
    }

    let mut script = String::from(
        r#"set -Eeuo pipefail
copy_path() {
  src="$1"
  dst="$2"
  if [ -d "$src" ]; then
    rm -rf "$dst"
    mkdir -p "$dst"
    (cd "$src" && tar -cf - .) | (cd "$dst" && tar -xf -)
  elif [ -f "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -p -- "$src" "$dst"
  else
    echo "missing localized opengrep input: $src" >&2
    exit 2
  fi
}
copy_back_file() {
  src="$1"
  dst="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -f -- "$src" "$dst"
  fi
}
"#,
    );
    script.push_str(&format!("local_root={}\n", shell_quote(&local_root)));
    script.push_str("rm -rf \"$local_root\"\nmkdir -p \"$local_root/output\"\n");
    script.push_str("trap 'rm -rf \"$local_root\"' EXIT\n");
    script.push_str("echo 'ARGUS_A3S_LOCALIZE copy_start' >&2\n");
    for (source, target) in &copy_pairs {
        script.push_str(&format!(
            "copy_path {} {}\n",
            shell_quote(source),
            shell_quote(target)
        ));
    }
    script.push_str("echo 'ARGUS_A3S_LOCALIZE scan_start' >&2\n");
    script.push_str("set +e\n");
    script.push_str(&shell_command_array(&localized));
    script.push_str("\nstatus=$?\nset -e\n");
    script.push_str("echo \"ARGUS_A3S_LOCALIZE scan_done status=${status}\" >&2\n");
    for (source, target) in &copy_back_pairs {
        script.push_str(&format!(
            "copy_back_file {} {}\n",
            shell_quote(source),
            shell_quote(target)
        ));
    }
    script.push_str("exit \"$status\"\n");

    vec!["bash".to_string(), "-lc".to_string(), script]
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
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
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
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
        MGMT_CMD_OUTPUT_LIMIT_BYTES,
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
        ensure_a3s_box_image_cached(&binary, &spec.image, &meta_dir)?;
        runner_command = rewrite_runner_command(&spec.command, &resolved_workspace);
        runner_command = build_localized_opengrep_command_with_limit(
            &runner_command,
            &resolved_workspace,
            &box_name,
            spec.localize_max_source_bytes,
            spec.task_id.as_deref(),
        );
        runner_environment = rewrite_runner_env(&spec.env, &resolved_workspace);

        let mut args = vec![
            "run".to_string(),
            "--rm".to_string(),
            "--name".to_string(),
            box_name.clone(),
            "-v".to_string(),
            format!(
                "{}:{}:rw",
                resolved_workspace.display(),
                resolved_workspace.display()
            ),
            "-w".to_string(),
            resolved_workspace.display().to_string(),
        ];
        if spec.network_disabled {
            args.push("--network".to_string());
            args.push("none".to_string());
        }
        if let Some(limit_mb) = spec.memory_limit_mb {
            args.push("--memory".to_string());
            args.push(format_memory_limit_mb(limit_mb));
        }
        if let Some(limit) = spec.cpu_limit {
            args.push("--cpus".to_string());
            args.push(format_cpu_limit(limit));
        }
        for (key, value) in &runner_environment {
            args.push("-e".to_string());
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
        let info_capture = run_command_capture(
            &binary,
            &["info".to_string()],
            Some(Duration::from_secs(30)),
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
            MGMT_CMD_OUTPUT_LIMIT_BYTES,
        )?;
        if !command_succeeded(&info_capture) {
            bail!(
                "a3s-box info failed before run: {}",
                command_failed_text(&info_capture)
            );
        }
        if let Some(error) =
            a3s_box_virtualization_error_text(&info_capture.stdout, &info_capture.stderr)
        {
            bail!("a3s-box virtualization unavailable before run: {error}");
        }
        active_box_name = Some(box_name.clone());
        register_active_task_box(spec.task_id.as_deref(), &box_name);
        let capture = run_a3s_box_workload_capture(
            &binary,
            &args,
            timeout,
            spec.stdout_limit_bytes,
            spec.stderr_limit_bytes,
            &box_name,
            Duration::from_secs(a3s_box_startup_timeout()),
        )?;
        if let Some(error) = a3s_box_virtualization_error_text(&capture.stdout, &capture.stderr) {
            cleanup_box(&binary, active_box_name.as_deref());
            unregister_active_task_box(spec.task_id.as_deref(), &box_name);
            bail!("a3s-box virtualization failed during run: {error}");
        }
        if capture.timed_out {
            cleanup_box(&binary, active_box_name.as_deref());
            unregister_active_task_box(spec.task_id.as_deref(), &box_name);
            let detail = command_failed_text(&capture);
            if !detail.trim().is_empty() {
                bail!("{detail}");
            }
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
        unregister_active_task_box(spec.task_id.as_deref(), &box_name);
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
    unregister_active_task_box(spec.task_id.as_deref(), &box_name);
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

/// Ensure the a3s-box OCI image cache is warm for `image`, for use by the pool factory.
///
/// This is the public entry-point used by `A3sBoxFactory::create()` (Phase C.1).
/// It creates a temporary meta directory under `a3s_box_runner_root()`, calls
/// `ensure_a3s_box_image_cached`, and returns the path to the argus marker file
/// that serves as proof of cache warmth.
///
/// Returns `Ok(marker_path)` where `marker_path` is the `.id` marker file
/// written by the cache routine, or an empty `PathBuf` when no marker dir is
/// configured (i.e. `HOME` is unset) — the cache is still warm in that case;
/// the caller records the path for observability only.
pub fn ensure_image_cached_for_pool(image: &str) -> anyhow::Result<std::path::PathBuf> {
    let runner_root = a3s_box_runner_root();
    let meta_dir = runner_root.join("pool-warmup");
    fs::create_dir_all(&meta_dir).with_context(|| {
        format!(
            "ensure_image_cached_for_pool: create meta dir: {}",
            meta_dir.display()
        )
    })?;

    let binary = a3s_box_bin();
    ensure_a3s_box_image_cached(&binary, image, &meta_dir)?;

    // Return the marker file path for observability (may not exist when HOME is unset).
    let marker_path = a3s_box_argus_marker_dir()
        .map(|dir| {
            let marker_name = a3s_box_cache_marker_name(image);
            dir.join(format!("{marker_name}.id"))
        })
        .unwrap_or_default();
    Ok(marker_path)
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
  info)
    printf 'Virtualization: available\n'
    ;;
  run)
    if [ "${FAKE_A3S_BOX_EXEC_RUN:-0}" = "1" ]; then
      while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
        shift
      done
      [ "$#" -gt 0 ] || exit 69
      shift
      exec "$@"
    fi
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

    fn fake_a3s_box_cache_script(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-a3s-box-cache.sh");
        let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_A3S_BOX_LOG:?}"
cache_marker="${FAKE_A3S_BOX_CACHE_MARKER:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  info)
    printf 'Virtualization: available\n'
    ;;
  image-inspect)
    [ -f "$cache_marker" ]
    ;;
  load)
    loaded_archive="${FAKE_A3S_BOX_LOADED_ARCHIVE:-}"
    if [ -n "$loaded_archive" ]; then
      input=""
      while [ "$#" -gt 0 ]; do
        if [ "$1" = "-i" ]; then
          shift
          input="${1:-}"
        fi
        shift || true
      done
      [ -n "$input" ] || exit 68
      cp "$input" "$loaded_archive"
    fi
    touch "$cache_marker"
    printf 'loaded\n'
    ;;
  run)
    printf 'scan ok\n'
    ;;
  rm)
    printf 'removed\n'
    ;;
  *)
    exit 67
    ;;
esac
"#;
        fs::write(&script_path, script).expect("write fake a3s-box cache script");
        let mut permissions = fs::metadata(&script_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).unwrap();
        script_path
    }

    fn fake_container_cli_script(temp_dir: &TempDir) -> PathBuf {
        let script_path = temp_dir.path().join("fake-docker.sh");
        let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_CONTAINER_CLI_LOG:?}"
archive="${FAKE_CONTAINER_CLI_ARCHIVE:?}"
printf '%s\n' "$*" >> "$log_file"
case "${1:-}" in
  image)
    [ "${2:-}" = "inspect" ] || exit 64
    exit 0
    ;;
  save)
    output=""
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "-o" ]; then
        shift
        output="${1:-}"
      fi
      shift || true
    done
    [ -n "$output" ] || exit 65
    mkdir -p "$(dirname "$output")"
    cp "$archive" "$output"
    ;;
  *)
    exit 66
    ;;
esac
"#;
        fs::write(&script_path, script).expect("write fake container cli script");
        let mut permissions = fs::metadata(&script_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).unwrap();
        script_path
    }

    fn append_test_tar_bytes(builder: &mut tar::Builder<fs::File>, path: &str, bytes: &[u8]) {
        let mut header = tar::Header::new_gnu();
        header.set_mode(0o644);
        header.set_size(bytes.len() as u64);
        header.set_cksum();
        builder.append_data(&mut header, path, bytes).unwrap();
    }

    fn write_fake_docker_oci_archive(temp_dir: &TempDir) -> PathBuf {
        let mut layer_bytes = Vec::new();
        {
            let mut layer_builder = tar::Builder::new(&mut layer_bytes);
            let payload = b"fake layer payload\n";
            let mut header = tar::Header::new_gnu();
            header.set_path("fake.txt").unwrap();
            header.set_mode(0o644);
            header.set_size(payload.len() as u64);
            header.set_cksum();
            layer_builder.append(&header, &payload[..]).unwrap();
            layer_builder.finish().unwrap();
        }

        let layer_digest = sha256_hex(&layer_bytes);
        let config = serde_json::json!({
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "Cmd": ["opengrep-scan", "--self-test"],
                "WorkingDir": "/scan"
            },
            "rootfs": {
                "type": "layers",
                "diff_ids": [format!("sha256:{layer_digest}")]
            }
        });
        let config_bytes = serde_json::to_vec(&config).unwrap();
        let config_digest = sha256_hex(&config_bytes);
        let manifest = serde_json::json!({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": format!("sha256:{config_digest}"),
                "size": config_bytes.len()
            },
            "layers": [{
                "mediaType": "application/vnd.oci.image.layer.v1.tar",
                "digest": format!("sha256:{layer_digest}"),
                "size": layer_bytes.len()
            }]
        });
        let manifest_bytes = serde_json::to_vec(&manifest).unwrap();
        let manifest_digest = sha256_hex(&manifest_bytes);
        let index = serde_json::json!({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [{
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": format!("sha256:{manifest_digest}"),
                "size": manifest_bytes.len(),
                "annotations": {
                    "io.containerd.image.name": "docker.io/argus/opengrep-runner:test",
                    "org.opencontainers.image.ref.name": "test"
                }
            }]
        });

        let archive_path = temp_dir.path().join("fake-docker-image.tar");
        let file = fs::File::create(&archive_path).unwrap();
        let mut builder = tar::Builder::new(file);
        append_test_tar_bytes(
            &mut builder,
            "oci-layout",
            br#"{"imageLayoutVersion":"1.0.0"}"#,
        );
        append_test_tar_bytes(
            &mut builder,
            "index.json",
            &serde_json::to_vec(&index).unwrap(),
        );
        append_test_tar_bytes(
            &mut builder,
            &format!("blobs/sha256/{manifest_digest}"),
            &manifest_bytes,
        );
        append_test_tar_bytes(
            &mut builder,
            &format!("blobs/sha256/{config_digest}"),
            &config_bytes,
        );
        append_test_tar_bytes(
            &mut builder,
            &format!("blobs/sha256/{layer_digest}"),
            &layer_bytes,
        );
        append_test_tar_bytes(&mut builder, "manifest.json", b"[]");
        append_test_tar_bytes(&mut builder, "repositories", b"{}");
        builder.finish().unwrap();
        archive_path
    }

    fn assert_archive_has_only_a3s_compatible_oci_layers(archive_path: &Path) {
        let unpack_dir = tempfile::Builder::new()
            .prefix("argus-a3s-loaded-")
            .tempdir()
            .unwrap();
        let file = fs::File::open(archive_path).unwrap();
        let mut archive = tar::Archive::new(file);
        archive.unpack(unpack_dir.path()).unwrap();
        assert!(
            !unpack_dir.path().join("manifest.json").exists(),
            "converted A3S OCI archive must drop Docker manifest.json"
        );
        assert!(
            !unpack_dir.path().join("repositories").exists(),
            "converted A3S OCI archive must drop Docker repositories metadata"
        );
        let index: serde_json::Value =
            serde_json::from_slice(&fs::read(unpack_dir.path().join("index.json")).unwrap())
                .unwrap();
        let manifest_digest = index["manifests"][0]["digest"]
            .as_str()
            .and_then(digest_sha256_hex)
            .unwrap();
        let manifest_path = unpack_dir
            .path()
            .join("blobs")
            .join("sha256")
            .join(manifest_digest);
        let manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(manifest_path).unwrap()).unwrap();
        let layers = manifest["layers"].as_array().unwrap();
        assert!(!layers.is_empty());
        assert!(layers.iter().all(|layer| {
            layer["mediaType"].as_str() == Some("application/vnd.oci.image.layer.v1.tar+gzip")
        }));
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
            ..Default::default()
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
            "-v {}:{}:rw",
            workspace_dir.display(),
            workspace_dir.display()
        )));
        assert!(logged.contains(&format!("-w {}", workspace_dir.display())));
        assert!(logged.contains("--memory 2048m"));
        assert!(logged.contains("--cpus 2"));
        assert!(!logged.contains("--network none"));
        assert!(logged.contains(&format!("-e RULE_ROOT={}/rules", workspace_dir.display())));
        assert!(
            logged.contains(&format!("{}/source", workspace_dir.display())),
            "localized wrapper should copy the workspace source: {logged}"
        );
        assert!(
            logged.contains("/tmp/argus-a3s-opengrep-"),
            "opengrep should scan guest-local paths: {logged}"
        );
        assert!(workspace_dir.join("meta/a3s-box-runner.json").exists());
    }

    #[test]
    fn execute_localizes_opengrep_workspace_before_scanning() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let fake_a3s_box = fake_a3s_box_script(&temp_dir);
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(workspace_dir.join("source")).unwrap();
        fs::create_dir_all(workspace_dir.join("opengrep-rules")).unwrap();
        fs::create_dir_all(workspace_dir.join("output")).unwrap();
        fs::write(workspace_dir.join("source/Main.java"), "class Main {}\n").unwrap();
        fs::write(
            workspace_dir.join("opengrep-rules/demo.yaml"),
            "rules: []\n",
        )
        .unwrap();
        let fake_opengrep_scan = temp_dir.path().join("opengrep-scan");
        fs::write(
            &fake_opengrep_scan,
            r#"#!/bin/sh
set -eu
target=""
config=""
output=""
summary=""
log=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) target="$2"; shift 2 ;;
    --config) config="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    --summary) summary="$2"; shift 2 ;;
    --log) log="$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "$target" in /tmp/argus-a3s-opengrep-*/source) ;; *) echo "bad target: $target" >&2; exit 70 ;; esac
case "$config" in /tmp/argus-a3s-opengrep-*/config-0) ;; *) echo "bad config: $config" >&2; exit 71 ;; esac
mkdir -p "$(dirname "$output")" "$(dirname "$summary")" "$(dirname "$log")"
printf '{"results":[]}\n' > "$output"
printf '{"status":"scan_completed"}\n' > "$summary"
printf 'localized scan ok\n' > "$log"
"#,
        )
        .unwrap();
        let mut permissions = fs::metadata(&fake_opengrep_scan).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&fake_opengrep_scan, permissions).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());
        let _exec = EnvVarGuard::set("FAKE_A3S_BOX_EXEC_RUN", "1");
        let original_path = env::var("PATH").unwrap_or_default();
        let _path = EnvVarGuard::set(
            "PATH",
            &format!("{}:{original_path}", temp_dir.path().display()),
        );

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec![
                "opengrep-scan".to_string(),
                "--target".to_string(),
                workspace_dir.join("source").display().to_string(),
                "--config".to_string(),
                workspace_dir.join("opengrep-rules").display().to_string(),
                "--output".to_string(),
                workspace_dir
                    .join("output/results.json")
                    .display()
                    .to_string(),
                "--summary".to_string(),
                workspace_dir
                    .join("output/summary.json")
                    .display()
                    .to_string(),
                "--log".to_string(),
                workspace_dir
                    .join("output/opengrep.log")
                    .display()
                    .to_string(),
            ],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0, 1],
            capture_stdout_path: Some("output/stdout.txt".to_string()),
            capture_stderr_path: Some("output/stderr.txt".to_string()),
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
            ..Default::default()
        });

        assert!(result.success, "{:?}", result.error);
        let logged = fs::read_to_string(fake_log).unwrap();
        assert!(
            logged.contains("bash -lc"),
            "opengrep command should run through localization wrapper: {logged}"
        );
        assert!(
            logged.contains("/tmp/argus-a3s-opengrep-"),
            "localized scan should use guest-local /tmp paths: {logged}"
        );
        assert!(fs::read_to_string(workspace_dir.join("output/stderr.txt"))
            .unwrap()
            .contains("ARGUS_A3S_LOCALIZE scan_start"));
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/results.json")).unwrap(),
            "{\"results\":[]}\n"
        );
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/summary.json")).unwrap(),
            "{\"status\":\"scan_completed\"}\n"
        );
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/opengrep.log")).unwrap(),
            "localized scan ok\n"
        );
    }

    #[test]
    fn stop_active_task_sync_removes_registered_box() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let fake_a3s_box = fake_a3s_box_script(&temp_dir);
        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());

        register_active_task_box(Some("task-1"), "argus-opengrep-testbox");
        assert!(stop_active_task_sync("task-1"));
        unregister_active_task_box(Some("task-1"), "argus-opengrep-testbox");

        let logged = fs::read_to_string(fake_log).unwrap();
        assert!(logged.contains("rm|--force argus-opengrep-testbox"));
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
            ..Default::default()
        });

        assert!(result.success);
        assert_eq!(result.exit_code, 1);
    }

    #[test]
    fn execute_loads_missing_a3s_image_from_local_container_cache() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_a3s_log = temp_dir.path().join("a3s-box.log");
        let fake_container_log = temp_dir.path().join("container-cli.log");
        let fake_container_archive = write_fake_docker_oci_archive(&temp_dir);
        let fake_loaded_archive = temp_dir.path().join("loaded-a3s-oci.tar");
        let cache_marker = temp_dir.path().join("image-cached");
        let fake_a3s_box = fake_a3s_box_cache_script(&temp_dir);
        let fake_container_cli = fake_container_cli_script(&temp_dir);
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_a3s_log.to_str().unwrap());
        let _marker = EnvVarGuard::set("FAKE_A3S_BOX_CACHE_MARKER", cache_marker.to_str().unwrap());
        let _container_cli =
            EnvVarGuard::set("CONTAINER_CLI", fake_container_cli.to_str().unwrap());
        let _container_log = EnvVarGuard::set(
            "FAKE_CONTAINER_CLI_LOG",
            fake_container_log.to_str().unwrap(),
        );
        let _container_archive = EnvVarGuard::set(
            "FAKE_CONTAINER_CLI_ARCHIVE",
            fake_container_archive.to_str().unwrap(),
        );
        let _loaded_archive = EnvVarGuard::set(
            "FAKE_A3S_BOX_LOADED_ARCHIVE",
            fake_loaded_archive.to_str().unwrap(),
        );

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string()],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            capture_stdout_path: Some("output/stdout.txt".to_string()),
            capture_stderr_path: None,
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
            ..Default::default()
        });

        assert!(result.success, "{:?}", result.error);
        assert!(
            cache_marker.exists(),
            "a3s-box load should populate image cache"
        );
        let a3s_logged = fs::read_to_string(fake_a3s_log).unwrap();
        assert!(a3s_logged.contains("image-inspect|argus/opengrep-runner:test"));
        assert!(a3s_logged.contains("load|-i "));
        assert!(a3s_logged.contains("--tag argus/opengrep-runner:test"));
        assert!(a3s_logged.contains("run|"));
        let container_logged = fs::read_to_string(fake_container_log).unwrap();
        assert!(container_logged.contains("image inspect argus/opengrep-runner:test"));
        assert!(container_logged.contains("save argus/opengrep-runner:test -o "));
        assert_archive_has_only_a3s_compatible_oci_layers(&fake_loaded_archive);
        assert_eq!(
            fs::read_to_string(workspace_dir.join("output/stdout.txt")).unwrap(),
            "scan ok\n"
        );
    }

    #[test]
    fn execute_maps_network_disabled_to_official_network_none_mode() {
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
            ..Default::default()
        });

        assert!(result.success, "{:?}", result.error);
        let logged = fs::read_to_string(fake_log).unwrap();
        assert!(logged.contains("run|"));
        assert!(
            logged.contains("--network none"),
            "a3s-box offline scans must use the official --network none mode: {logged}"
        );
    }

    #[test]
    fn execute_rejects_unavailable_a3s_virtualization_before_run() {
        let _lock = ENV_LOCK.lock().unwrap();
        let temp_dir = TempDir::new().unwrap();
        let fake_log = temp_dir.path().join("a3s-box.log");
        let script_path = temp_dir.path().join("fake-a3s-box-no-kvm.sh");
        fs::write(
            &script_path,
            r#"#!/bin/sh
set -eu
printf '%s|%s\n' "${1:-}" "$*" >> "${FAKE_A3S_BOX_LOG:?}"
case "${1:-}" in
  info)
    printf 'Virtualization: not available (Configuration error: KVM is not available: /dev/kvm not found.)\n'
    ;;
  *)
    exit 64
    ;;
esac
"#,
        )
        .unwrap();
        let mut permissions = fs::metadata(&script_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).unwrap();
        let workspace_dir = temp_dir.path().join("workspace");
        fs::create_dir_all(&workspace_dir).unwrap();

        let _bin = EnvVarGuard::set("A3S_BOX_BIN", script_path.to_str().unwrap());
        let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());

        let result = execute(A3sBoxRunnerSpec {
            scanner_type: "opengrep".to_string(),
            image: "argus/opengrep-runner:test".to_string(),
            workspace_dir: workspace_dir.display().to_string(),
            command: vec!["opengrep-scan".to_string()],
            timeout_seconds: 60,
            env: BTreeMap::new(),
            expected_exit_codes: vec![0],
            capture_stdout_path: None,
            capture_stderr_path: None,
            memory_limit_mb: None,
            cpu_limit: None,
            pids_limit: None,
            network_disabled: false,
            ..Default::default()
        });

        assert!(!result.success);
        assert!(result
            .error
            .as_deref()
            .unwrap_or_default()
            .contains("a3s-box virtualization unavailable before run"));
        let logged = fs::read_to_string(fake_log).unwrap();
        assert!(logged.contains("info|"));
        assert!(
            !logged.contains("run|"),
            "a3s-box run must not start without KVM"
        );
    }

    #[test]
    fn cpu_limit_is_rounded_up_for_a3s_cli_integer_cpus() {
        assert_eq!(format_cpu_limit(3.5), "4");
        assert_eq!(format_cpu_limit(2.0), "2");
        assert_eq!(format_cpu_limit(0.0), "1");
    }

    #[cfg(unix)]
    #[test]
    fn run_command_capture_truncates_stdout_at_limit() {
        // Emit > 256 bytes to stdout via shell, verify capture <= limit + sentinel length.
        let limit: usize = 256;
        let sentinel = format!("...[a3s-box output truncated to {limit} bytes]");
        let args: Vec<String> = vec![
            "-c".to_string(),
            "for i in $(seq 1 1000); do printf 'aaaaaaaaaa'; done".to_string(),
        ];
        let result =
            run_command_capture("sh", &args, None, limit, 1_048_576).expect("sh should run");
        // Output must not exceed limit + sentinel length.
        assert!(
            result.stdout.len() <= limit + sentinel.len(),
            "stdout len {} exceeds limit + sentinel {}",
            result.stdout.len(),
            limit + sentinel.len()
        );
        assert!(
            result.stdout.ends_with(&sentinel),
            "stdout should end with truncation sentinel, got: {:?}",
            &result.stdout[result.stdout.len().saturating_sub(80)..]
        );
    }

    #[cfg(unix)]
    #[test]
    fn run_command_capture_truncates_stderr_at_limit() {
        // Emit > 256 bytes to stderr via shell, verify capture <= limit + sentinel length.
        let limit: usize = 256;
        let sentinel = format!("...[a3s-box output truncated to {limit} bytes]");
        let args: Vec<String> = vec![
            "-c".to_string(),
            "for i in $(seq 1 1000); do printf 'bbbbbbbbbb' >&2; done".to_string(),
        ];
        let result =
            run_command_capture("sh", &args, None, 1_048_576, limit).expect("sh should run");
        assert!(
            result.stderr.len() <= limit + sentinel.len(),
            "stderr len {} exceeds limit + sentinel {}",
            result.stderr.len(),
            limit + sentinel.len()
        );
        assert!(
            result.stderr.ends_with(&sentinel),
            "stderr should end with truncation sentinel, got: {:?}",
            &result.stderr[result.stderr.len().saturating_sub(80)..]
        );
    }

    fn write_dummy_source(workspace: &std::path::Path, total_bytes: usize) {
        let source = workspace.join("source");
        fs::create_dir_all(&source).expect("create source dir");
        // Write a single file of `total_bytes` zero bytes — measured_dir_size_capped
        // sums regular-file sizes via metadata.len() so the actual content
        // doesn't matter, only the file size on disk.
        let buf = vec![0u8; total_bytes];
        fs::write(source.join("blob.bin"), &buf).expect("write blob");
    }

    fn opengrep_command(workspace: &std::path::Path) -> Vec<String> {
        vec![
            "opengrep-scan".to_string(),
            "--target".to_string(),
            workspace.join("source").display().to_string(),
            "--output".to_string(),
            workspace.join("output/results.json").display().to_string(),
            "--summary".to_string(),
            workspace.join("output/summary.json").display().to_string(),
            "--log".to_string(),
            workspace.join("output/opengrep.log").display().to_string(),
            "--jobs".to_string(),
            "2".to_string(),
            "--max-memory".to_string(),
            "2048".to_string(),
        ]
    }

    #[test]
    fn localize_skipped_when_source_exceeds_limit() {
        let temp = tempfile::tempdir().expect("temp");
        let workspace = temp.path().canonicalize().expect("canonicalize");
        write_dummy_source(&workspace, 4_096); // 4 KiB
        let cmd = opengrep_command(&workspace);

        let out = build_localized_opengrep_command_with_limit(
            &cmd,
            &workspace,
            "test-box",
            Some(1024), // 1 KiB cap → 4 KiB source exceeds it
            Some("task-large"),
        );

        assert_eq!(
            out, cmd,
            "command must be unchanged when source exceeds limit"
        );
    }

    #[test]
    fn localize_applied_when_source_fits_limit() {
        let temp = tempfile::tempdir().expect("temp");
        let workspace = temp.path().canonicalize().expect("canonicalize");
        write_dummy_source(&workspace, 1_024); // 1 KiB
        let cmd = opengrep_command(&workspace);

        let out = build_localized_opengrep_command_with_limit(
            &cmd,
            &workspace,
            "test-box",
            Some(64 * 1024), // 64 KiB cap → 1 KiB source fits
            Some("task-small"),
        );

        // Localization wraps the command in a bash -lc script with copy_path/copy_back_file.
        assert_eq!(
            out.len(),
            3,
            "localized command should be ['bash', '-lc', SCRIPT]"
        );
        assert_eq!(out[0], "bash");
        assert_eq!(out[1], "-lc");
        assert!(out[2].contains("copy_path"));
        assert!(out[2].contains("/tmp/argus-a3s-opengrep-test-box"));
    }

    #[test]
    fn localize_limit_zero_disables_localization() {
        let temp = tempfile::tempdir().expect("temp");
        let workspace = temp.path().canonicalize().expect("canonicalize");
        write_dummy_source(&workspace, 1_024);
        let cmd = opengrep_command(&workspace);

        let out = build_localized_opengrep_command_with_limit(
            &cmd,
            &workspace,
            "test-box",
            Some(0),
            Some("task-zero"),
        );

        assert_eq!(out, cmd, "limit=0 must disable localization");
    }

    #[test]
    fn localize_none_preserves_legacy_unconditional_behaviour() {
        let temp = tempfile::tempdir().expect("temp");
        let workspace = temp.path().canonicalize().expect("canonicalize");
        write_dummy_source(&workspace, 8 * 1024 * 1024); // 8 MiB — would exceed a low cap
        let cmd = opengrep_command(&workspace);

        // localize_max_source_bytes = None: no size measurement, always localize.
        let out =
            build_localized_opengrep_command_with_limit(&cmd, &workspace, "test-box", None, None);

        assert_eq!(out.len(), 3);
        assert_eq!(out[0], "bash");
    }

    #[test]
    fn extract_opengrep_target_finds_value() {
        let cmd = vec![
            "opengrep-scan".to_string(),
            "--jobs".to_string(),
            "4".to_string(),
            "--target".to_string(),
            "/some/path".to_string(),
            "--output".to_string(),
            "/o/r.json".to_string(),
        ];
        assert_eq!(extract_opengrep_target(&cmd), Some("/some/path"));
    }

    #[test]
    fn extract_opengrep_target_returns_none_when_missing() {
        let cmd = vec![
            "opengrep-scan".to_string(),
            "--jobs".to_string(),
            "4".to_string(),
        ];
        assert_eq!(extract_opengrep_target(&cmd), None);
    }

    #[test]
    fn measured_dir_size_capped_returns_early_on_cap_exceed() {
        let temp = tempfile::tempdir().expect("temp");
        let dir = temp.path();
        // Two 4 KiB files = 8 KiB total; cap at 1 KiB → must early-return >1 KiB.
        fs::write(dir.join("a.bin"), vec![0u8; 4096]).expect("a");
        fs::write(dir.join("b.bin"), vec![0u8; 4096]).expect("b");

        let measured = measured_dir_size_capped(dir, 1024);
        assert!(measured > 1024, "must return a value exceeding the cap");
    }
}
