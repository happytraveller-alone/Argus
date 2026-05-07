use std::{
    collections::{HashMap, HashSet},
    io::Write,
    path::Path,
    sync::{LazyLock, Mutex},
};

use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use flate2::{write::GzEncoder, Compression};
use serde::Serialize;
use serde_json::Value;
use tar::{Builder, Header};

use crate::{
    db::cubesandbox_templates::{TemplateKind, TemplateStatus},
    runtime::cubesandbox::{
        client::{CubeSandboxClient, CubeSandboxClientConfig, CubeSandboxSandbox},
        config::CubeSandboxConfig,
        helper::{run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand},
        template_provisioner::{self, EnsureOutcome},
        types::ActiveCubeSandboxSnapshot,
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

#[derive(Clone)]
struct ActiveOpengrepSandbox {
    client: CubeSandboxClient,
    sandbox_id: String,
}

static ACTIVE_OPENGREP_SANDBOXES: LazyLock<Mutex<HashMap<String, ActiveOpengrepSandbox>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
static CANCELLED_OPENGREP_TASKS: LazyLock<Mutex<HashSet<String>>> =
    LazyLock::new(|| Mutex::new(HashSet::new()));

pub struct OpengrepSandboxSession {
    task_id: String,
    pub template_id: String,
    client: CubeSandboxClient,
    sandbox: CubeSandboxSandbox,
    t0: std::time::Instant,
}

impl OpengrepSandboxSession {
    pub async fn start(state: &AppState, task_id: &str) -> Result<Self> {
        let t0 = std::time::Instant::now();

        // ── Pool-first acquisition (Phase A.2.2) ─────────────────────────────
        //
        // Try to take a pre-warmed sandbox from the standby pool.  On pool miss
        // (starvation, kill switch, or pool not configured) fall back to the
        // original synchronous cold-start path — no 503, no error surface.
        if let Some(pool) = state.cubesandbox_pool.as_ref() {
            let kind = opengrep_template_kind();
            if let Some(handle) = pool.take(&kind).await {
                // Pool hit: spawn a background refill so the slot is replenished
                // while our source upload runs in parallel.
                pool.refill_in_background(kind).await;

                tracing::info!(
                    task_id = %task_id,
                    stage = "standby_acquired",
                    sandbox_id = %handle.sandbox_id,
                    elapsed_ms = t0.elapsed().as_millis() as u64,
                    "using pre-warmed standby sandbox"
                );

                if take_cancel_request(task_id) {
                    crate::runtime::cubesandbox::best_effort_delete_sandbox(
                        &handle.client,
                        &handle.sandbox_id,
                        task_id,
                        "cancel_after_pool_take",
                    )
                    .await;
                    bail!(
                        "Opengrep CubeSandbox scan cancelled after pool take for task {task_id}"
                    );
                }

                // Re-wrap handle into the session shape. `domain` MUST come
                // from the original create_sandbox response — without it
                // envd_host bails "missing sandbox domain" on the first
                // write_file. The cubelet GET listing has no domain, so we
                // rely on the value captured at pool factory time.
                let sandbox = CubeSandboxSandbox {
                    sandbox_id: handle.sandbox_id.clone(),
                    template_id: handle.template_id.clone(),
                    client_id: String::new(),
                    envd_version: String::new(),
                    domain: handle.domain.clone(),
                };
                let client = (*handle.client).clone();
                register_active_sandbox(
                    task_id,
                    ActiveOpengrepSandbox {
                        client: client.clone(),
                        sandbox_id: handle.sandbox_id.clone(),
                    },
                );
                return Ok(Self {
                    task_id: task_id.to_string(),
                    template_id: handle.template_id.clone(),
                    client,
                    sandbox,
                    t0,
                });
            } else {
                // Pool miss: log starvation metric and fall through to cold-start.
                tracing::info!(
                    task_id = %task_id,
                    stage = "standby_pool_starvation",
                    template = "OpengrepDedicated",
                    "pool returned None; falling back to cold-start"
                );
            }
        }

        // ── Cold-start fallback (original path, unchanged) ────────────────────
        let config = CubeSandboxConfig::load_runtime(state)
            .await?
            .for_template_kind(opengrep_template_kind(), state.config.as_ref());
        config.validate_for_execution()?;
        let template_id = ensure_template_id_or_wait(state, &config, task_id).await?;
        tracing::info!(task_id = %task_id, stage = "template_ready", elapsed_ms = t0.elapsed().as_millis() as u64);
        if take_cancel_request(task_id) {
            bail!("Opengrep CubeSandbox scan cancelled before sandbox creation for task {task_id}");
        }

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
            crate::runtime::cubesandbox::best_effort_delete_sandbox(
                &client,
                &sandbox.sandbox_id,
                task_id,
                "cancel_after_create",
            )
            .await;
            unregister_active_sandbox(task_id, &sandbox.sandbox_id);
            bail!("Opengrep CubeSandbox scan cancelled before sandbox connect for task {task_id}");
        }
        client.connect_sandbox(&sandbox.sandbox_id).await?;
        tracing::info!(task_id = %task_id, stage = "sandbox_connected", elapsed_ms = t0.elapsed().as_millis() as u64);
        Ok(Self {
            task_id: task_id.to_string(),
            template_id,
            client,
            sandbox,
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
        let client = &self.client;
        let sandbox = &self.sandbox;
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

        let markers = extract_opengrep_markers(&output.stdout);
        if !markers.scan_done {
            bail!(
                "CubeSandbox Opengrep output missing SCAN_DONE marker (exit={:?}) stdout={} stderr={}",
                output.exit_code,
                truncate_for_error(&output.stdout),
                truncate_for_error(&output.stderr)
            );
        }

        // Required: results, summary. Optional (best-effort): log, stdout, stderr.
        let results_path = markers
            .get("RESULTS")
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "CubeSandbox Opengrep output missing RESULTS_PATH marker (exit={:?}) stdout={} stderr={}",
                    output.exit_code,
                    truncate_for_error(&output.stdout),
                    truncate_for_error(&output.stderr)
                )
            })?;
        let summary_path = markers
            .get("SUMMARY")
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "CubeSandbox Opengrep output missing SUMMARY_PATH marker (exit={:?}) stdout={} stderr={}",
                    output.exit_code,
                    truncate_for_error(&output.stdout),
                    truncate_for_error(&output.stderr)
                )
            })?;

        let results_bytes = client
            .read_file(sandbox, results_path)
            .await
            .with_context(|| format!("reading opengrep results from {results_path}"))?;
        let summary_bytes = client
            .read_file(sandbox, summary_path)
            .await
            .with_context(|| format!("reading opengrep summary from {summary_path}"))?;
        let log_bytes = match markers.get("LOG") {
            Some(p) => client
                .read_file(sandbox, p)
                .await
                .unwrap_or_else(|err| {
                    tracing::warn!(error = %err, path = %p, "opengrep log read failed; continuing");
                    Vec::new()
                }),
            None => Vec::new(),
        };
        let stdout_bytes = match markers.get("STDOUT") {
            Some(p) => client
                .read_file(sandbox, p)
                .await
                .unwrap_or_else(|err| {
                    tracing::warn!(error = %err, path = %p, "opengrep stdout read failed; continuing");
                    Vec::new()
                }),
            None => Vec::new(),
        };
        let stderr_bytes = match markers.get("STDERR") {
            Some(p) => client
                .read_file(sandbox, p)
                .await
                .unwrap_or_else(|err| {
                    tracing::warn!(error = %err, path = %p, "opengrep stderr read failed; continuing");
                    Vec::new()
                }),
            None => Vec::new(),
        };

        tracing::info!(
            task_id = %self.task_id,
            stage = "outputs_fetched",
            elapsed_ms = self.t0.elapsed().as_millis() as u64,
            results_bytes = results_bytes.len() as u64,
            summary_bytes = summary_bytes.len() as u64,
            log_bytes = log_bytes.len() as u64,
            stdout_bytes = stdout_bytes.len() as u64,
            stderr_bytes = stderr_bytes.len() as u64,
        );

        // results.json + summary.json must be valid UTF-8 (they are JSON we author).
        let results_text = String::from_utf8(results_bytes)
            .context("opengrep results.json was not valid UTF-8")?;
        let summary_json: Value = serde_json::from_slice(&summary_bytes)
            .context("decoding opengrep summary.json")?;
        // Log/stdout/stderr can contain user-content; tolerate non-UTF-8 bytes.
        let log_text = String::from_utf8_lossy(&log_bytes).into_owned();
        let stdout_text = String::from_utf8_lossy(&stdout_bytes).into_owned();
        let stderr_text = String::from_utf8_lossy(&stderr_bytes).into_owned();

        let scan_exit_code = markers
            .exit_code
            .or_else(|| summary_json.get("exit_code").and_then(|v| v.as_i64()).and_then(|n| i32::try_from(n).ok()))
            .unwrap_or(output.exit_code.unwrap_or(0));

        Ok(CubeSandboxOpengrepOutput {
            results_text,
            summary_json,
            log_text,
            stdout_text,
            stderr_text,
            scan_exit_code,
            sandbox_id: sandbox.sandbox_id.clone(),
            cleanup_completed: false,
        })
    }

    pub fn sandbox_id(&self) -> &str {
        &self.sandbox.sandbox_id
    }

    pub async fn unregister_active(&self) {
        unregister_active_sandbox(&self.task_id, &self.sandbox.sandbox_id);
    }
}

pub async fn run_opengrep_scan(
    state: &AppState,
    input: CubeSandboxOpengrepInput<'_>,
) -> Result<CubeSandboxOpengrepOutput> {
    let session = OpengrepSandboxSession::start(state, input.task_id).await?;

    // Capture values needed after session is consumed by cleanup.
    let template_id = session.template_id.clone();
    let task_id_owned = session.task_id.clone();
    let sandbox_id_for_log = session.sandbox_id().to_string();
    let client_for_cleanup = session.client.clone();

    // Do NOT use `?` here — we must run cleanup regardless of scan outcome.
    let scan_result = session.run_scan(input).await;

    // Determine counter status from scan result before cleanup.
    let status_for_counter = scan_result
        .as_ref()
        .ok()
        .and_then(|r| r.summary_json.get("status").and_then(|v| v.as_str()))
        .map(str::to_string);

    // Always-cleanup: unregister then best-effort delete. Never bail on cleanup failure.
    session.unregister_active().await;
    crate::runtime::cubesandbox::best_effort_delete_sandbox(
        &client_for_cleanup,
        &sandbox_id_for_log,
        &task_id_owned,
        "cleanup_post_run",
    )
    .await;

    // Counter feedback runs after cleanup, on captured values.
    match status_for_counter.as_deref() {
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

    // Surface scan result; mark cleanup_completed = true on success path.
    let mut result = scan_result?;
    result.sandbox_id = sandbox_id_for_log;
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

pub fn snapshot_active_sandbox_ids() -> HashSet<String> {
    ACTIVE_OPENGREP_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .values()
        .map(|active| active.sandbox_id.clone())
        .collect()
}

pub fn snapshot_active_sandboxes() -> Vec<ActiveCubeSandboxSnapshot> {
    ACTIVE_OPENGREP_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .iter()
        .map(|(task_id, active)| ActiveCubeSandboxSnapshot {
            task_id: task_id.clone(),
            sandbox_id: active.sandbox_id.clone(),
            engine: "opengrep".to_string(),
        })
        .collect()
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
    // Status-first lifecycle gate (see runtime::cubesandbox::task.rs for the
    // long-form rationale). Probe Status first — only fall through to
    // Install / RunVmBackground when cubelet is genuinely down, instead of
    // re-installing on every single scan.
    if should_run_local_lifecycle(config)? {
        let status_output = run_helper_command(config, CubeSandboxHelperCommand::Status).await?;
        if !status_output.success {
            if config.auto_install {
                let install_output =
                    run_helper_command(config, CubeSandboxHelperCommand::Install).await?;
                ensure_helper_success(CubeSandboxHelperCommand::Install, &install_output)?;
            }
            if config.auto_start {
                let start_output =
                    run_helper_command(config, CubeSandboxHelperCommand::RunVmBackground).await?;
                ensure_helper_success(CubeSandboxHelperCommand::RunVmBackground, &start_output)?;
            } else {
                ensure_helper_success(CubeSandboxHelperCommand::Status, &status_output)?;
            }
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
            bail!("CubeSandbox Opengrep 模板构建超时 (>{TEMPLATE_WAIT_TIMEOUT_SECS}s)");
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

/// Markers emitted by the in-sandbox Python wrapper. Each `*_PATH` line gives
/// a sandbox-side absolute path that the Rust client can fetch via
/// `client.read_file`. `EXIT_CODE` carries opengrep-scan's exit code (Python
/// emits this even on internal timeouts so the result envelope is always
/// well-defined). `SCAN_DONE=1` is the completion sentinel — its absence means
/// the wrapper script crashed mid-flight (e.g. OOM-kill) and outputs are not
/// trustworthy.
#[derive(Debug, Default, PartialEq, Eq)]
struct OpengrepMarkers {
    paths: HashMap<String, String>,
    exit_code: Option<i32>,
    scan_done: bool,
}

impl OpengrepMarkers {
    fn get(&self, key: &str) -> Option<&str> {
        self.paths.get(key).map(String::as_str)
    }
}

fn extract_opengrep_markers(stdout: &str) -> OpengrepMarkers {
    let mut markers = OpengrepMarkers::default();
    for line in stdout.lines() {
        let line = line.trim();
        let Some(rest) = line.strip_prefix("ARGUS_OPENGREP_") else {
            continue;
        };
        if let Some(value) = rest.strip_prefix("SCAN_DONE=") {
            if value.trim() == "1" {
                markers.scan_done = true;
            }
        } else if let Some(value) = rest.strip_prefix("EXIT_CODE=") {
            if let Ok(code) = value.trim().parse::<i32>() {
                markers.exit_code = Some(code);
            }
        } else if let Some((key, value)) = rest.split_once("_PATH=") {
            let value = value.trim();
            if !value.is_empty() {
                markers.paths.insert(key.to_string(), value.to_string());
            }
        }
    }
    markers
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
stdout_path = output_dir / "opengrep.stdout"
stderr_path = output_dir / "opengrep.stderr"

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
# First-principles memory fix: opengrep-scan output is redirected directly to
# files on the sandbox writable layer. Python never holds stdout/stderr in
# RAM (no subprocess.PIPE buffering), and we never read result/log files back
# into memory or base64-encode them. The Rust side downloads each file
# individually via the envd /files API. This bounds peak Python memory to a
# few MB regardless of scan output size, eliminating the OOM that killed
# FFMPEG-scale scans before they could emit completion markers.
returncode = -1
timed_out = False
try:
    with stdout_path.open("wb") as _so, stderr_path.open("wb") as _se:
        proc = subprocess.run(cmd, stdout=_so, stderr=_se, timeout=900, env=run_env)
    returncode = proc.returncode
except subprocess.TimeoutExpired as exc:
    timed_out = True
    returncode = -1
    # Best-effort note in stderr file so the Rust side can surface a useful error.
    try:
        with stderr_path.open("ab") as _se:
            _se.write(f"\nopengrep-scan exceeded internal timeout of {exc.timeout}s; killed by wrapper\n".encode("utf-8"))
    except Exception:
        pass
_t["opengrep_done"] = time.perf_counter()
print(f"STAGE_TIMING opengrep_done={_t['opengrep_done']-_t['extract_done']:.3f}s", file=sys.stderr)
if not summary.exists():
    summary.write_text(
        json.dumps(
            {
                "status": "scan_completed" if (not timed_out and returncode in (0, 1)) else "scan_failed",
                "reason": ""
                    if (not timed_out and returncode in (0, 1))
                    else (f"opengrep-scan timed out after wrapper internal timeout"
                          if timed_out
                          else f"opengrep-scan exited {returncode}"),
                "results_path": str(results),
                "log_path": str(log),
            },
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
if not results.exists() and not timed_out and returncode in (0, 1):
    results.write_text('{"results":[]}\n', encoding="utf-8")
summary_payload = json.loads(summary.read_text(encoding="utf-8"))
summary_payload["exit_code"] = returncode
if timed_out and not summary_payload.get("reason"):
    summary_payload["reason"] = "opengrep-scan timed out after wrapper internal timeout"
elif (not timed_out) and returncode not in (0, 1) and not summary_payload.get("reason"):
    summary_payload["reason"] = f"opengrep-scan exited {returncode}"
summary_payload["argus_oci_debug"] = {
    "manifest_count": len(manifest_entries),
    "baked_rules": bool(_use_baked),
    "workspace_rules": str(workspace_rules),
    "workspace_rules_exists": workspace_rules.exists(),
    "command": cmd,
    "timed_out": bool(timed_out),
}
# Persist the augmented summary back to disk so the Rust side reads the
# canonical version (with exit_code and argus_oci_debug merged in).
summary.write_text(
    json.dumps(summary_payload, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
# Emit per-file path markers and a completion sentinel. The Rust client
# downloads each file via the envd /files API. SCAN_DONE=1 must come last so
# its presence implies all earlier markers and on-disk files are intact.
print(f"ARGUS_OPENGREP_RESULTS_PATH={results}")
print(f"ARGUS_OPENGREP_SUMMARY_PATH={summary}")
print(f"ARGUS_OPENGREP_LOG_PATH={log}")
print(f"ARGUS_OPENGREP_STDOUT_PATH={stdout_path}")
print(f"ARGUS_OPENGREP_STDERR_PATH={stderr_path}")
print(f"ARGUS_OPENGREP_EXIT_CODE={returncode}")
print("ARGUS_OPENGREP_SCAN_DONE=1")
"#;

#[cfg(test)]
mod tests {
    use super::*;

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
        // New per-file markers + completion sentinel must all be present.
        assert!(script.contains("ARGUS_OPENGREP_RESULTS_PATH="));
        assert!(script.contains("ARGUS_OPENGREP_SUMMARY_PATH="));
        assert!(script.contains("ARGUS_OPENGREP_LOG_PATH="));
        assert!(script.contains("ARGUS_OPENGREP_STDOUT_PATH="));
        assert!(script.contains("ARGUS_OPENGREP_STDERR_PATH="));
        assert!(script.contains("ARGUS_OPENGREP_EXIT_CODE="));
        assert!(script.contains("ARGUS_OPENGREP_SCAN_DONE=1"));
        // No b64 envelope anywhere — guard against regressions.
        assert!(!script.contains("results_b64"));
        assert!(!script.contains("envelope"));
        // TimeoutExpired path must keep the wrapper alive so markers still emit.
        assert!(script.contains("TimeoutExpired"));
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
    fn extract_opengrep_markers_parses_complete_manifest() {
        let stdout = "noise before\n\
             ARGUS_OPENGREP_RESULTS_PATH=/tmp/argus-opengrep-work/output/results.json\n\
             ARGUS_OPENGREP_SUMMARY_PATH=/tmp/argus-opengrep-work/output/summary.json\n\
             ARGUS_OPENGREP_LOG_PATH=/tmp/argus-opengrep-work/output/opengrep.log\n\
             ARGUS_OPENGREP_STDOUT_PATH=/tmp/argus-opengrep-work/output/opengrep.stdout\n\
             ARGUS_OPENGREP_STDERR_PATH=/tmp/argus-opengrep-work/output/opengrep.stderr\n\
             ARGUS_OPENGREP_EXIT_CODE=0\n\
             ARGUS_OPENGREP_SCAN_DONE=1\n";

        let m = extract_opengrep_markers(stdout);

        assert!(m.scan_done);
        assert_eq!(m.exit_code, Some(0));
        assert_eq!(
            m.get("RESULTS"),
            Some("/tmp/argus-opengrep-work/output/results.json")
        );
        assert_eq!(
            m.get("SUMMARY"),
            Some("/tmp/argus-opengrep-work/output/summary.json")
        );
        assert_eq!(
            m.get("LOG"),
            Some("/tmp/argus-opengrep-work/output/opengrep.log")
        );
        assert_eq!(
            m.get("STDOUT"),
            Some("/tmp/argus-opengrep-work/output/opengrep.stdout")
        );
        assert_eq!(
            m.get("STDERR"),
            Some("/tmp/argus-opengrep-work/output/opengrep.stderr")
        );
    }

    #[test]
    fn extract_opengrep_markers_missing_scan_done_means_incomplete() {
        let stdout = "ARGUS_OPENGREP_RESULTS_PATH=/tmp/r.json\n\
             ARGUS_OPENGREP_SUMMARY_PATH=/tmp/s.json\n";

        let m = extract_opengrep_markers(stdout);

        assert!(!m.scan_done);
        assert!(m.exit_code.is_none());
        assert_eq!(m.get("RESULTS"), Some("/tmp/r.json"));
    }

    #[test]
    fn extract_opengrep_markers_ignores_unrelated_output() {
        let stdout = "STAGE_TIMING extract_done=0.05s\n\
             some other line\n\
             ARGUS_OPENGREP_SCAN_DONE=1\n";

        let m = extract_opengrep_markers(stdout);

        assert!(m.scan_done);
        assert!(m.paths.is_empty());
    }

    #[test]
    fn extract_opengrep_markers_skips_empty_path_values() {
        let stdout = "ARGUS_OPENGREP_RESULTS_PATH=\n\
             ARGUS_OPENGREP_SUMMARY_PATH=/tmp/s.json\n\
             ARGUS_OPENGREP_SCAN_DONE=1\n";

        let m = extract_opengrep_markers(stdout);

        assert!(m.scan_done);
        assert_eq!(m.get("RESULTS"), None);
        assert_eq!(m.get("SUMMARY"), Some("/tmp/s.json"));
    }

    #[test]
    fn truncate_for_error_respects_utf8_boundaries() {
        let value = format!("{}tail", "🙂".repeat(300));

        let truncated = truncate_for_error(&value);

        assert!(truncated.ends_with("tail"));
        assert!(truncated.len() <= 1024);
    }
}
