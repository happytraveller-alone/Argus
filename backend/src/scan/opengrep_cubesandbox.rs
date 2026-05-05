use std::{
    collections::{HashMap, HashSet},
    io::Write,
    path::Path,
    sync::{Arc, LazyLock, Mutex},
};

use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use flate2::{write::GzEncoder, Compression};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tar::{Builder, Header};

use crate::{
    db::cubesandbox_templates::{TemplateKind, TemplateStatus},
    runtime::cubesandbox::{
        client::{CubeSandboxClient, CubeSandboxClientConfig, CubeSandboxSandbox},
        config::CubeSandboxConfig,
        helper::{run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand},
        opengrep_pool::PoolGuard,
        template_provisioner::{self, EnsureOutcome},
    },
    state::AppState,
};

#[derive(Clone, Debug)]
pub struct CubeSandboxOpengrepInput<'a> {
    pub task_id: &'a str,
    pub workspace_dir: &'a Path,
    pub source_dir: &'a Path,
    pub rules_dir: &'a Path,
    /// Selected image-packaged rule paths, relative to the baked image rule root.
    /// Example: `rules_opengrep/c/sql-injection.yaml`.
    pub image_rule_manifest_paths: &'a [String],
    pub jobs: usize,
    pub max_memory_mb: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CubeSandboxOpengrepOutput {
    pub results_text: String,
    pub summary_json: Value,
    pub log_text: String,
    pub stdout_text: String,
    pub stderr_text: String,
    pub scan_exit_code: i32,
    pub sandbox_id: String,
    pub cleanup_completed: bool,
}

#[derive(Serialize)]
struct CubeSandboxOpengrepRequest {
    // archive_b64 removed (A4-lite): archive is uploaded via write_file to /tmp/workspace.tar.gz
    image_rule_manifest_paths: Vec<String>,
    jobs: usize,
    max_memory_mb: u64,
}

#[derive(Deserialize)]
struct CubeSandboxOpengrepEnvelope {
    results_b64: String,
    summary: Value,
    log_b64: String,
    stdout_b64: String,
    stderr_b64: String,
    exit_code: i32,
}

#[derive(Clone)]
struct ActiveOpengrepSandbox {
    client: CubeSandboxClient,
    sandbox_id: String,
}

static ACTIVE_OPENGREP_SANDBOXES: LazyLock<Mutex<HashMap<String, ActiveOpengrepSandbox>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
static CANCELLED_OPENGREP_TASKS: LazyLock<Mutex<HashSet<String>>> =
    LazyLock::new(|| Mutex::new(HashSet::new()));

/// Holds either a pool-borrowed sandbox (warm path) or a directly-created one (cold path).
enum SessionSandboxSource {
    /// Warm pool path: the guard carries the sandbox back to the pool on release.
    Pool { guard: PoolGuard },
    /// Cold path: sandbox was created ad-hoc; cleanup deletes it.
    Direct {
        client: CubeSandboxClient,
        sandbox: CubeSandboxSandbox,
    },
}

impl SessionSandboxSource {
    fn client(&self) -> &CubeSandboxClient {
        match self {
            Self::Pool { guard } => &guard.client,
            Self::Direct { client, .. } => client,
        }
    }

    fn sandbox(&self) -> &CubeSandboxSandbox {
        match self {
            Self::Pool { guard } => guard.sandbox(),
            Self::Direct { sandbox, .. } => sandbox,
        }
    }
}

pub struct OpengrepSandboxSession {
    task_id: String,
    pub template_id: String,
    source: SessionSandboxSource,
    t0: std::time::Instant,
}

impl OpengrepSandboxSession {
    pub async fn start(state: &AppState, task_id: &str) -> Result<Self> {
        let t0 = std::time::Instant::now();
        let config = CubeSandboxConfig::load_runtime(state)
            .await?
            .for_template_kind(opengrep_template_kind(), state.config.as_ref());
        config.validate_for_execution()?;
        let template_id = ensure_template_id_or_wait(state, &config, task_id).await?;
        tracing::info!(task_id = %task_id, stage = "template_ready", elapsed_ms = t0.elapsed().as_millis() as u64);
        if take_cancel_request(task_id) {
            bail!("Opengrep CubeSandbox scan cancelled before sandbox creation for task {task_id}");
        }

        // Try warm pool first.
        if let Some(pool) = state.get_opengrep_pool().await {
            tracing::info!(task_id = %task_id, stage = "client_prepared", elapsed_ms = t0.elapsed().as_millis() as u64);
            let guard = pool.acquire(task_id).await?;
            let sandbox_id = guard.sandbox().sandbox_id.clone();
            register_active_sandbox(
                task_id,
                ActiveOpengrepSandbox {
                    client: guard.client.clone(),
                    sandbox_id: sandbox_id.clone(),
                },
            );
            return Ok(Self {
                task_id: task_id.to_string(),
                template_id,
                source: SessionSandboxSource::Pool { guard },
                t0,
            });
        }

        // Cold path (no pool or pool disabled).
        let client = prepare_client(&config, &template_id).await?;
        tracing::info!(task_id = %task_id, stage = "client_prepared", elapsed_ms = t0.elapsed().as_millis() as u64);
        let sandbox = client.create_sandbox().await?;
        tracing::info!(task_id = %task_id, stage = "sandbox_created", elapsed_ms = t0.elapsed().as_millis() as u64);
        register_active_sandbox(
            task_id,
            ActiveOpengrepSandbox {
                client: client.clone(),
                sandbox_id: sandbox.sandbox_id.clone(),
            },
        );
        if take_cancel_request(task_id) {
            let _ = client.delete_sandbox(&sandbox.sandbox_id).await;
            unregister_active_sandbox(task_id, &sandbox.sandbox_id);
            bail!("Opengrep CubeSandbox scan cancelled before sandbox connect for task {task_id}");
        }
        client.connect_sandbox(&sandbox.sandbox_id).await?;
        tracing::info!(task_id = %task_id, stage = "sandbox_connected", elapsed_ms = t0.elapsed().as_millis() as u64);
        Ok(Self {
            task_id: task_id.to_string(),
            template_id,
            source: SessionSandboxSource::Direct { client, sandbox },
            t0,
        })
    }

    pub async fn run_scan(
        &self,
        input: CubeSandboxOpengrepInput<'_>,
    ) -> Result<CubeSandboxOpengrepOutput> {
        if take_cancel_request(input.task_id) {
            bail!(
                "Opengrep CubeSandbox scan cancelled before scanner execution for task {}",
                input.task_id
            );
        }
        let client = self.source.client();
        let sandbox = self.source.sandbox();
        tracing::info!(task_id = %self.task_id, stage = "archive_start", elapsed_ms = self.t0.elapsed().as_millis() as u64);

        // A4-lite: build raw tar+gz bytes and upload via write_file (skip base64 encode/decode).
        let archive_bytes =
            create_workspace_archive_bytes(input.workspace_dir, input.source_dir, input.rules_dir)?;
        tracing::info!(
            task_id = %self.task_id,
            stage = "archive_built",
            elapsed_ms = self.t0.elapsed().as_millis() as u64,
            archive_bytes = archive_bytes.len() as u64,
            jobs = input.jobs as u64,
        );

        // Upload archive directly — no base64 encoding.
        client
            .write_file(sandbox, "/tmp/workspace.tar.gz", archive_bytes)
            .await?;

        let payload = CubeSandboxOpengrepRequest {
            image_rule_manifest_paths: input.image_rule_manifest_paths.to_vec(),
            jobs: input.jobs,
            max_memory_mb: input.max_memory_mb,
        };
        let script = build_opengrep_runner_script(&payload)?;
        let output = client.run_command(sandbox, &script).await?;
        tracing::info!(task_id = %self.task_id, stage = "command_done", elapsed_ms = self.t0.elapsed().as_millis() as u64);

        let envelope_path = output
            .stdout
            .lines()
            .rev()
            .find_map(|line| line.strip_prefix("ARGUS_OPENGREP_RESULT_PATH="))
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);
        let envelope_bytes = match envelope_path {
            Some(path) => {
                let bytes = client
                    .read_file(sandbox, &path)
                    .await
                    .with_context(|| format!("reading opengrep envelope from {path}"))?;
                tracing::info!(
                    task_id = %self.task_id,
                    stage = "envelope_fetched",
                    elapsed_ms = self.t0.elapsed().as_millis() as u64,
                    envelope_bytes = bytes.len() as u64,
                );
                bytes
            }
            None => {
                bail!(
                    "CubeSandbox Opengrep output missing result path marker (exit={:?}) stdout={} stderr={}",
                    output.exit_code,
                    truncate_for_error(&output.stdout),
                    truncate_for_error(&output.stderr)
                );
            }
        };
        let mut result = parse_opengrep_envelope_bytes(&envelope_bytes)?;
        result.sandbox_id = sandbox.sandbox_id.clone();
        Ok(result)
    }

    pub async fn cleanup(self) -> Result<()> {
        let sandbox_id = self.source.sandbox().sandbox_id.clone();
        unregister_active_sandbox(&self.task_id, &sandbox_id);
        match self.source {
            SessionSandboxSource::Pool { guard } => {
                let pool = Arc::clone(&guard.pool);
                pool.release(guard).await?;
            }
            SessionSandboxSource::Direct { client, sandbox } => {
                client.delete_sandbox(&sandbox.sandbox_id).await?;
            }
        }
        tracing::info!(task_id = %self.task_id, stage = "cleaned_up", elapsed_ms = self.t0.elapsed().as_millis() as u64);
        Ok(())
    }
}

pub async fn run_opengrep_scan(
    state: &AppState,
    input: CubeSandboxOpengrepInput<'_>,
) -> Result<CubeSandboxOpengrepOutput> {
    let session = OpengrepSandboxSession::start(state, input.task_id).await?;
    let mut result = session.run_scan(input).await?;
    let sandbox_id = result.sandbox_id.clone();
    // Wire scan-failure counter feedback before cleanup consumes session.
    let template_id = session.template_id.clone();
    match result.summary_json.get("status").and_then(|v| v.as_str()) {
        Some("scan_failed") => {
            match crate::db::cubesandbox_templates::bump_scan_failure_counter(state, &template_id)
                .await
            {
                Ok(n) if n >= 3 => {
                    let _ = crate::db::cubesandbox_templates::mark_invalidated_by_template_id(
                        state,
                        &template_id,
                    )
                    .await;
                    let _ = crate::db::cubesandbox_templates::reset_scan_failure_counter(
                        state,
                        &template_id,
                    )
                    .await;
                }
                Ok(_) => {}
                Err(e) => {
                    tracing::warn!(error = %e, %template_id, "scan_failed counter bump failed; swallowing")
                }
            }
        }
        Some("scan_completed") => {
            if let Err(e) =
                crate::db::cubesandbox_templates::reset_scan_failure_counter(state, &template_id)
                    .await
            {
                tracing::warn!(error = %e, %template_id, "scan_completed counter reset failed; swallowing");
            }
        }
        _ => {}
    }
    if let Err(error) = session.cleanup().await {
        bail!("CubeSandbox cleanup failed after Opengrep scan: {error}");
    }
    result.sandbox_id = sandbox_id;
    result.cleanup_completed = true;
    Ok(result)
}

pub async fn cancel_opengrep_scan(task_id: &str) -> Result<bool> {
    CANCELLED_OPENGREP_TASKS
        .lock()
        .expect("cancel set lock")
        .insert(task_id.to_string());
    let active = ACTIVE_OPENGREP_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .remove(task_id);
    let Some(active) = active else {
        return Ok(false);
    };
    active.client.delete_sandbox(&active.sandbox_id).await?;
    Ok(true)
}

fn register_active_sandbox(task_id: &str, active: ActiveOpengrepSandbox) {
    ACTIVE_OPENGREP_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .insert(task_id.to_string(), active);
}

fn unregister_active_sandbox(task_id: &str, sandbox_id: &str) {
    let mut active = ACTIVE_OPENGREP_SANDBOXES
        .lock()
        .expect("active sandbox lock");
    if active
        .get(task_id)
        .is_some_and(|current| current.sandbox_id == sandbox_id)
    {
        active.remove(task_id);
    }
}

fn take_cancel_request(task_id: &str) -> bool {
    CANCELLED_OPENGREP_TASKS
        .lock()
        .expect("cancel set lock")
        .remove(task_id)
}

async fn prepare_client(
    config: &CubeSandboxConfig,
    template_id: &str,
) -> Result<CubeSandboxClient> {
    if should_run_local_lifecycle(config)? && config.auto_install {
        let output = run_helper_command(config, CubeSandboxHelperCommand::Install).await?;
        ensure_helper_success(CubeSandboxHelperCommand::Install, &output)?;
    }
    if should_run_local_lifecycle(config)? {
        let status_output = run_helper_command(config, CubeSandboxHelperCommand::Status).await?;
        if !status_output.success && config.auto_start {
            let start_output =
                run_helper_command(config, CubeSandboxHelperCommand::RunVmBackground).await?;
            ensure_helper_success(CubeSandboxHelperCommand::RunVmBackground, &start_output)?;
        } else {
            ensure_helper_success(CubeSandboxHelperCommand::Status, &status_output)?;
        }
    }
    let client = CubeSandboxClient::new(CubeSandboxClientConfig {
        api_base_url: config.api_base_url.clone(),
        data_plane_base_url: config.data_plane_base_url.clone(),
        template_id: template_id.to_string(),
        execution_timeout_seconds: config.execution_timeout_seconds,
        cleanup_timeout_seconds: config.sandbox_cleanup_timeout_seconds,
        stdout_limit_bytes: config.stdout_limit_bytes,
        stderr_limit_bytes: config.stderr_limit_bytes,
    })?;
    client.health().await?;
    Ok(client)
}

const TEMPLATE_WAIT_TIMEOUT_SECS: u64 = 1800;

async fn ensure_template_id_or_wait(
    state: &AppState,
    config: &CubeSandboxConfig,
    task_id: &str,
) -> Result<String> {
    match template_provisioner::ensure_opengrep_template_ready(state, config).await? {
        EnsureOutcome::Ready { template_id } => Ok(template_id),
        EnsureOutcome::NotEligible { reason } => {
            bail!("CubeSandbox Opengrep 模板自动构建不可用: {reason}")
        }
        EnsureOutcome::InProgress { record_id: _ } => {
            wait_for_template(state, config, task_id).await
        }
    }
}

async fn wait_for_template(
    state: &AppState,
    config: &CubeSandboxConfig,
    task_id: &str,
) -> Result<String> {
    use std::time::Duration;
    let deadline = std::time::Instant::now() + Duration::from_secs(TEMPLATE_WAIT_TIMEOUT_SECS);
    loop {
        if take_cancel_request(task_id) {
            bail!("Opengrep CubeSandbox scan cancelled while waiting for template build (task {task_id})");
        }
        if let Some(template_id) = template_provisioner::resolve_existing_template_id(
            state,
            config,
            opengrep_template_kind(),
        )
        .await?
        {
            return Ok(template_id);
        }
        if let Some(record) =
            template_provisioner::get_status(state, opengrep_template_kind()).await?
        {
            match record.status {
                TemplateStatus::Ready => {
                    if let Some(template_id) = record.template_id {
                        return Ok(template_id);
                    }
                    bail!("CubeSandbox Opengrep template marked ready but missing template_id");
                }
                TemplateStatus::Failed => {
                    bail!(
                        "CubeSandbox Opengrep 模板构建失败: {}",
                        record.error_message.unwrap_or_default()
                    );
                }
                TemplateStatus::Invalidated => {
                    bail!("CubeSandbox Opengrep 模板已被标记为失效, 请重建模板");
                }
                TemplateStatus::Pending | TemplateStatus::Building => {}
            }
        }
        if std::time::Instant::now() >= deadline {
            bail!(
                "CubeSandbox Opengrep 模板构建超时 (>{}s)",
                TEMPLATE_WAIT_TIMEOUT_SECS
            );
        }
        tokio::time::sleep(Duration::from_secs(5)).await;
    }
}

pub fn opengrep_template_kind() -> TemplateKind {
    TemplateKind::current_opengrep()
}

fn ensure_helper_success(
    command: CubeSandboxHelperCommand,
    output: &crate::runtime::cubesandbox::helper::CubeSandboxHelperOutput,
) -> Result<()> {
    if output.success {
        return Ok(());
    }
    bail!(
        "CubeSandbox helper command failed: {:?} exit={:?}",
        command,
        output.exit_code
    )
}

/// Returns true when the sandbox image has pre-baked rules and we should skip bundling them.
/// Controlled by `OPENGREP_USE_BAKED_RULES` env var (default: "1" = enabled).
fn use_baked_rules() -> bool {
    std::env::var("OPENGREP_USE_BAKED_RULES")
        .unwrap_or_else(|_| "1".to_string())
        .trim()
        != "0"
}

/// A4-lite: returns raw tar+gz bytes (no base64 encoding).
/// The caller uploads these via `client.write_file(sandbox, "/tmp/workspace.tar.gz", bytes)`.
/// When `use_baked_rules()` is true, only the source dir is archived (rules already in image).
fn create_workspace_archive_bytes(
    _workspace_dir: &Path,
    source_dir: &Path,
    rules_dir: &Path,
) -> Result<Vec<u8>> {
    create_workspace_archive_bytes_with_baked_mode(source_dir, rules_dir, use_baked_rules())
}

fn create_workspace_archive_bytes_with_baked_mode(
    source_dir: &Path,
    rules_dir: &Path,
    baked_rules: bool,
) -> Result<Vec<u8>> {
    let mut archive = Vec::new();
    {
        let encoder = GzEncoder::new(&mut archive, Compression::default());
        let mut builder = Builder::new(encoder);
        append_dir(&mut builder, source_dir, "source")?;
        if baked_rules {
            // Image-packaged rules are selected through a manifest at runtime.
            // Keep only non-image rules (currently user rules) in the archive.
            append_dir_filtered(&mut builder, rules_dir, "rules", |relative| {
                !relative.starts_with("internal")
            })?;
        } else {
            // Baked-rules disabled: include rules dir so the Python script can find them.
            append_dir(&mut builder, rules_dir, "rules")?;
        }
        builder.finish()?;
        let encoder = builder.into_inner()?;
        encoder.finish()?;
    }
    Ok(archive)
}

fn append_dir<W: Write>(builder: &mut Builder<W>, dir: &Path, archive_prefix: &str) -> Result<()> {
    append_dir_filtered(builder, dir, archive_prefix, |_| true)
}

fn append_dir_filtered<W, F>(
    builder: &mut Builder<W>,
    dir: &Path,
    archive_prefix: &str,
    should_include: F,
) -> Result<()>
where
    W: Write,
    F: Fn(&Path) -> bool,
{
    if !dir.exists() {
        return Ok(());
    }
    let mut files = Vec::new();
    collect_files(dir, &mut files)?;
    files.sort();
    for path in files {
        let relative = path.strip_prefix(dir)?;
        if !should_include(relative) {
            continue;
        }
        let archive_path = Path::new(archive_prefix).join(relative);
        append_file_with_normalized_mode(builder, &path, &archive_path)
            .with_context(|| format!("failed to stage {}", path.display()))?;
    }
    Ok(())
}

fn append_file_with_normalized_mode<W: Write>(
    builder: &mut Builder<W>,
    path: &Path,
    archive_path: &Path,
) -> Result<()> {
    let bytes = std::fs::read(path)?;
    let metadata = std::fs::metadata(path)?;
    let mut header = Header::new_gnu();
    header.set_size(bytes.len() as u64);
    header.set_mode(normalized_archive_mode(&metadata));
    header.set_cksum();
    builder.append_data(&mut header, archive_path, bytes.as_slice())?;
    Ok(())
}

fn normalized_archive_mode(metadata: &std::fs::Metadata) -> u32 {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = metadata.permissions().mode() & 0o777;
        if mode & 0o111 != 0 {
            return 0o755;
        }
        0o644
    }
    #[cfg(not(unix))]
    {
        0o644
    }
}

fn collect_files(dir: &Path, output: &mut Vec<std::path::PathBuf>) -> Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            collect_files(&path, output)?;
        } else if file_type.is_file() {
            output.push(path);
        }
    }
    Ok(())
}

fn build_payload_python_script(python_body: &str, payload_b64: &str) -> String {
    let unique = uuid::Uuid::new_v4();
    let mut script = String::new();
    script.push_str("set -e\n");
    script.push_str(&format!(
        "_ARGUS_PAYLOAD=\"/tmp/argus-opengrep-payload-{unique}.b64\"\n"
    ));
    script.push_str("cat > \"$_ARGUS_PAYLOAD\" <<'__ARGUS_B64__'\n");
    script.push_str(payload_b64);
    script.push_str("\n__ARGUS_B64__\n");
    script.push_str("_ARGUS_RC=0\n");
    script.push_str("python3 - \"$_ARGUS_PAYLOAD\" <<'PY' || _ARGUS_RC=$?\n");
    script.push_str(python_body);
    script.push_str("\nPY\n");
    script.push_str("rm -f \"$_ARGUS_PAYLOAD\"\n");
    script.push_str("exit $_ARGUS_RC\n");
    script
}

fn build_opengrep_runner_script(payload: &CubeSandboxOpengrepRequest) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(payload)?);
    Ok(build_payload_python_script(
        CUBESANDBOX_OPENGREP_PY,
        &payload_b64,
    ))
}

fn parse_opengrep_envelope_bytes(bytes: &[u8]) -> Result<CubeSandboxOpengrepOutput> {
    let parsed: CubeSandboxOpengrepEnvelope =
        serde_json::from_slice(bytes).context("decoding opengrep envelope JSON")?;
    Ok(CubeSandboxOpengrepOutput {
        results_text: decode_text(&parsed.results_b64, "opengrep results")?,
        summary_json: parsed.summary,
        log_text: decode_text(&parsed.log_b64, "opengrep log")?,
        stdout_text: decode_text(&parsed.stdout_b64, "opengrep stdout")?,
        stderr_text: decode_text(&parsed.stderr_b64, "opengrep stderr")?,
        scan_exit_code: parsed.exit_code,
        sandbox_id: String::new(),
        cleanup_completed: false,
    })
}

fn decode_text(value: &str, label: &str) -> Result<String> {
    let bytes = STANDARD
        .decode(value)
        .with_context(|| format!("invalid {label} base64"))?;
    String::from_utf8(bytes).with_context(|| format!("invalid {label} utf8"))
}

fn truncate_for_error(value: &str) -> String {
    const LIMIT: usize = 1024;
    if value.len() <= LIMIT {
        return value.to_string();
    }
    let mut start = value.len().saturating_sub(LIMIT);
    while !value.is_char_boundary(start) {
        start += 1;
    }
    value[start..].to_string()
}

const CUBESANDBOX_OPENGREP_PY: &str = r#"
import base64
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import time

_t = {}
_t["start"] = time.perf_counter()

with open(sys.argv[1], "rb") as _argus_payload_fh:
    _argus_payload_b64 = _argus_payload_fh.read().strip()
payload = json.loads(base64.b64decode(_argus_payload_b64).decode("utf-8"))
# fallback when payload['jobs'] is missing or zero (Python truthiness on int 0)
DEFAULT_JOBS = 4
work = pathlib.Path("/tmp/argus-opengrep-work")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir(parents=True)
# A4-lite: archive was uploaded via write_file to /tmp/workspace.tar.gz (no base64)
archive_path = pathlib.Path("/tmp/workspace.tar.gz")
_t["extract_start"] = time.perf_counter()
with tarfile.open(archive_path, "r:gz") as bundle:
    root = work.resolve()
    for member in bundle.getmembers():
        target = (work / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"archive member escapes workspace: {member.name}")
    bundle.extractall(work)
_t["extract_done"] = time.perf_counter()
print(f"STAGE_TIMING extract_done={_t['extract_done']-_t['extract_start']:.3f}s", file=sys.stderr)

source = work / "source"
# Baked-rules path: if the image pre-extracted rules into /opt/opengrep/rules/
# and OPENGREP_USE_BAKED_RULES != "0", use the image-side rules directly. The
# marker file is written by newer images, but older valid templates only have
# rules_opengrep/, so accept either shape.
_BAKED_RULES_DIR = pathlib.Path("/opt/opengrep/rules")
_use_baked = (
    os.environ.get("OPENGREP_USE_BAKED_RULES", "1").strip() != "0"
    and ((_BAKED_RULES_DIR / ".baked").exists() or (_BAKED_RULES_DIR / "rules_opengrep").is_dir())
)
manifest_entries = payload.get("image_rule_manifest_paths") or []
manifest_path = work / "image-rules.manifest"
if manifest_entries:
    manifest_path.write_text(
        "\n".join(str(entry).lstrip("./") for entry in manifest_entries if str(entry).strip()) + "\n",
        encoding="utf-8",
    )

if _use_baked:
    rules = _BAKED_RULES_DIR
    print(f"STAGE_TIMING baked_rules=1 rules={rules}", file=sys.stderr)
else:
    rules = work / "rules"
    print(f"STAGE_TIMING baked_rules=0 rules={rules}", file=sys.stderr)
workspace_rules = work / "rules"
output_dir = work / "output"
output_dir.mkdir(parents=True, exist_ok=True)
results = output_dir / "results.json"
summary = output_dir / "summary.json"
log = output_dir / "opengrep.log"
stdout = output_dir / "opengrep.stdout"
stderr = output_dir / "opengrep.stderr"

cmd = [
    "opengrep-scan",
    "--target", str(source),
    "--output", str(results),
    "--summary", str(summary),
    "--log", str(log),
    "--jobs", str(int(payload.get("jobs") or DEFAULT_JOBS)),
    "--max-memory", str(payload.get("max_memory_mb") or 2048),
]
if _use_baked and manifest_entries:
    cmd.extend(["--manifest", str(manifest_path)])
elif not _use_baked:
    cmd.extend(["--config", str(rules)])
elif rules.exists():
    cmd.extend(["--config", str(rules)])
if workspace_rules.exists() and (any(workspace_rules.rglob("*.yml")) or any(workspace_rules.rglob("*.yaml"))):
    cmd.extend(["--config", str(workspace_rules)])
run_env = os.environ.copy()
run_env.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONUTF8": "1"})
proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, env=run_env)
_t["opengrep_done"] = time.perf_counter()
print(f"STAGE_TIMING opengrep_done={_t['opengrep_done']-_t['extract_done']:.3f}s", file=sys.stderr)
stdout.write_text(proc.stdout or "", encoding="utf-8")
stderr.write_text(proc.stderr or "", encoding="utf-8")
if not summary.exists():
    summary.write_text(
        json.dumps(
            {
                "status": "scan_completed" if proc.returncode in (0, 1) else "scan_failed",
                "reason": "" if proc.returncode in (0, 1) else f"opengrep-scan exited {proc.returncode}",
                "results_path": str(results),
                "log_path": str(log),
            },
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
if not results.exists() and proc.returncode in (0, 1):
    results.write_text('{"results":[]}\n', encoding="utf-8")
summary_payload = json.loads(summary.read_text(encoding="utf-8"))
summary_payload["exit_code"] = proc.returncode
if proc.returncode not in (0, 1) and not summary_payload.get("reason"):
    summary_payload["reason"] = f"opengrep-scan exited {proc.returncode}"
summary_payload["argus_oci_debug"] = {
    "manifest_count": len(manifest_entries),
    "baked_rules": bool(_use_baked),
    "workspace_rules": str(workspace_rules),
    "workspace_rules_exists": workspace_rules.exists(),
    "command": cmd,
}

def b64_text(path):
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")

envelope = {
    "results_b64": b64_text(results),
    "summary": summary_payload,
    "log_b64": b64_text(log),
    "stdout_b64": b64_text(stdout),
    "stderr_b64": b64_text(stderr),
    "exit_code": proc.returncode,
}
# A4-lite continued: write envelope to a sandbox-side file and emit only the
# path marker on stdout. The Rust client downloads the file via envd /files
# GET, sidestepping the stdout/stderr length cap that truncates large scans.
result_path = "/tmp/argus-opengrep-result.json"
pathlib.Path(result_path).write_text(
    json.dumps(envelope, separators=(",", ":")),
    encoding="utf-8",
)
print("ARGUS_OPENGREP_RESULT_PATH=" + result_path)
"#;

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn opengrep_cubesandbox_uses_dedicated_template_kind() {
        assert_eq!(opengrep_template_kind(), TemplateKind::OpengrepDedicated);
    }

    #[test]
    fn opengrep_runner_script_passes_payload_as_python_argument() {
        let script = build_opengrep_runner_script(&CubeSandboxOpengrepRequest {
            image_rule_manifest_paths: vec!["rules_opengrep/python/demo-rule.yaml".to_string()],
            jobs: 2,
            max_memory_mb: 1024,
        })
        .expect("script should build");

        assert!(script.starts_with("set -e\n"));
        assert!(script.contains("python3 - \"$_ARGUS_PAYLOAD\" <<'PY'"));
        assert!(script.contains("--manifest"));
        assert!(script.contains("\"PYTHONUTF8\": \"1\""));
        assert!(script.contains("summary_payload[\"reason\"]"));
        assert!(script.contains("ARGUS_OPENGREP_RESULT_PATH="));
        assert!(script.ends_with("exit $_ARGUS_RC\n"));
    }

    #[test]
    fn opengrep_archive_skips_internal_rules_when_baked_rules_are_enabled() {
        let root =
            std::env::temp_dir().join(format!("opengrep-baked-archive-{}", uuid::Uuid::new_v4()));
        let source = root.join("source");
        let rules = root.join("rules");
        std::fs::create_dir_all(source.join("src")).expect("source dir");
        std::fs::create_dir_all(rules.join("internal/python")).expect("internal rules dir");
        std::fs::create_dir_all(rules.join("user")).expect("user rules dir");
        std::fs::write(source.join("src/main.py"), "print(1)\n").expect("source file");
        std::fs::write(rules.join("internal/python/demo.yaml"), "rules: []\n")
            .expect("internal rule");
        std::fs::write(rules.join("user/custom.yaml"), "rules: []\n").expect("user rule");

        let archive =
            create_workspace_archive_bytes_with_baked_mode(&source, &rules, true).expect("archive");
        let decoder = flate2::read::GzDecoder::new(archive.as_slice());
        let mut archive = tar::Archive::new(decoder);
        let paths: Vec<String> = archive
            .entries()
            .expect("entries")
            .map(|entry| {
                entry
                    .expect("entry")
                    .path()
                    .expect("path")
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect();

        assert!(paths.contains(&"source/src/main.py".to_string()));
        assert!(paths.contains(&"rules/user/custom.yaml".to_string()));
        assert!(!paths.contains(&"rules/internal/python/demo.yaml".to_string()));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn parse_opengrep_envelope_bytes_reads_result() {
        let envelope = json!({
            "results_b64": STANDARD.encode("{\"results\":[]}\n"),
            "summary": {"status": "scan_completed", "exit_code": 0},
            "log_b64": STANDARD.encode("log\n"),
            "stdout_b64": STANDARD.encode("stdout\n"),
            "stderr_b64": STANDARD.encode("stderr\n"),
            "exit_code": 0,
        });
        let bytes = serde_json::to_vec(&envelope).expect("envelope serializes");

        let parsed = parse_opengrep_envelope_bytes(&bytes).expect("envelope bytes should parse");
        assert_eq!(parsed.results_text, "{\"results\":[]}\n");
        assert_eq!(parsed.log_text, "log\n");
        assert_eq!(parsed.scan_exit_code, 0);
    }

    #[test]
    fn truncate_for_error_respects_utf8_boundaries() {
        let value = format!("{}tail", "🙂".repeat(300));

        let truncated = truncate_for_error(&value);

        assert!(truncated.ends_with("tail"));
        assert!(truncated.len() <= 1024);
    }
}
