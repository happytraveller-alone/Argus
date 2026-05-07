use std::{
    collections::{BTreeSet, HashMap, HashSet},
    io::Write,
    path::Path,
    sync::{LazyLock, Mutex},
};

use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use flate2::{write::GzEncoder, Compression};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tar::{Builder, Header};

use crate::{
    db::cubesandbox_templates::TemplateKind,
    runtime::cubesandbox::{
        client::{
            CubeSandboxClient, CubeSandboxClientConfig, CubeSandboxSandbox, EnvdProcessOutput,
        },
        config::CubeSandboxConfig,
        helper::{run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand},
        template_provisioner::{self, EnsureOutcome},
        types::ActiveCubeSandboxSnapshot,
    },
    scan::codeql,
    state::AppState,
};

#[derive(Clone, Debug)]
pub struct CubeSandboxCodeqlInput<'a> {
    pub task_id: &'a str,
    pub workspace_dir: &'a Path,
    pub source_dir: &'a Path,
    pub query_dir: &'a Path,
    pub language: &'a str,
    pub build_mode: Option<&'a str>,
    pub build_plan: Option<Value>,
    pub exploration_rounds: Vec<Value>,
    pub threads: usize,
    pub ram_mb: u64,
    pub allow_network: bool,
}

#[derive(Clone)]
struct ActiveCodeqlSandbox {
    client: CubeSandboxClient,
    sandbox_id: String,
}

static ACTIVE_CODEQL_SANDBOXES: LazyLock<Mutex<HashMap<String, ActiveCodeqlSandbox>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
static CANCELLED_CODEQL_TASKS: LazyLock<Mutex<HashSet<String>>> =
    LazyLock::new(|| Mutex::new(HashSet::new()));

/// Return the set of sandbox_ids currently tracked as active CodeQL sandboxes.
/// Safe to call from async context: acquires the std::sync::Mutex only briefly.
/// At startup (before HTTP server bind), this always returns the empty set.
pub fn snapshot_active_sandbox_ids() -> HashSet<String> {
    ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock poisoned")
        .values()
        .map(|sb| sb.sandbox_id.clone())
        .collect()
}

pub fn snapshot_active_sandboxes() -> Vec<ActiveCubeSandboxSnapshot> {
    ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock poisoned")
        .iter()
        .map(|(task_id, active)| ActiveCubeSandboxSnapshot {
            task_id: task_id.clone(),
            sandbox_id: active.sandbox_id.clone(),
            engine: "codeql".to_string(),
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CubeSandboxCodeqlOutput {
    pub sarif_text: String,
    pub events_text: String,
    pub summary_json: Value,
    pub build_plan_json: Option<Value>,
    pub sandbox_id: String,
    pub cleanup_completed: bool,
}

#[derive(Serialize)]
struct CubeSandboxCodeqlRequest {
    archive_b64: String,
    language: String,
    build_mode: Option<String>,
    build_plan: Option<Value>,
    exploration_rounds: Vec<Value>,
    threads: usize,
    ram_mb: u64,
    allow_network: bool,
}

#[derive(Deserialize)]
struct CubeSandboxCodeqlEnvelope {
    sarif_b64: String,
    events_b64: String,
    summary: Value,
    #[serde(default)]
    build_plan: Option<Value>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeqlExplorationCommandOutput {
    pub command: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub failure_category: String,
    pub dependency_installation: Value,
}

#[derive(Deserialize)]
struct CodeqlExplorationCommandEnvelope {
    command: String,
    #[serde(default)]
    stdout: String,
    #[serde(default)]
    stderr: String,
    exit_code: i32,
    #[serde(default)]
    failure_category: String,
    #[serde(default)]
    dependency_installation: Value,
}

pub struct CodeqlSandboxSession {
    task_id: String,
    pub template_id: String,
    client: CubeSandboxClient,
    sandbox: CubeSandboxSandbox,
}

impl CodeqlSandboxSession {
    pub async fn start(state: &AppState, task_id: &str) -> Result<Self> {
        let t0 = std::time::Instant::now();

        // ── Pool-first acquisition (Phase B.1) ───────────────────────────────
        //
        // Try to take a pre-warmed sandbox from the standby pool.  On pool miss
        // (starvation, kill switch, or pool not configured) fall back to the
        // original synchronous cold-start path — no 503, no error surface.
        if let Some(pool) = state.cubesandbox_pool.as_ref() {
            let kind = TemplateKind::CodeqlCpp;
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
                        "CodeQL CubeSandbox scan cancelled after pool take for task {task_id}"
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
                    ActiveCodeqlSandbox {
                        client: client.clone(),
                        sandbox_id: handle.sandbox_id.clone(),
                    },
                );
                return Ok(Self {
                    task_id: task_id.to_string(),
                    template_id: handle.template_id.clone(),
                    client,
                    sandbox,
                });
            } else {
                // Pool miss: log starvation metric and fall through to cold-start.
                tracing::info!(
                    task_id = %task_id,
                    stage = "standby_pool_starvation",
                    template = "CodeqlCpp",
                    "pool returned None; falling back to cold-start"
                );
            }
        }

        // ── Cold-start fallback (original path, unchanged) ────────────────────
        let config = CubeSandboxConfig::load_runtime(state).await?;
        config.validate_for_execution()?;
        let template_id = ensure_template_id_or_wait(state, &config, task_id).await?;
        if take_cancel_request(task_id) {
            bail!("CodeQL CubeSandbox scan cancelled before sandbox creation for task {task_id}");
        }
        let client = prepare_client(&config, &template_id).await?;
        let sandbox = client.create_sandbox().await?;
        register_active_sandbox(
            task_id,
            ActiveCodeqlSandbox {
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
            bail!("CodeQL CubeSandbox scan cancelled before sandbox connect for task {task_id}");
        }
        client.connect_sandbox(&sandbox.sandbox_id).await?;
        Ok(Self {
            task_id: task_id.to_string(),
            template_id: template_id.clone(),
            client,
            sandbox,
        })
    }

    pub fn sandbox_id(&self) -> &str {
        &self.sandbox.sandbox_id
    }

    pub async fn stage_workspace(
        &self,
        workspace_dir: &Path,
        source_dir: &Path,
        query_dir: &Path,
    ) -> Result<()> {
        let archive_b64 = create_workspace_archive_b64(workspace_dir, source_dir, query_dir)?;
        let script = build_workspace_setup_script(&archive_b64)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        ensure_successful_process("CubeSandbox CodeQL workspace setup", output)?;
        Ok(())
    }

    pub async fn run_exploration_command(
        &self,
        command: &str,
    ) -> Result<CodeqlExplorationCommandOutput> {
        let script = build_exploration_command_script(command)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        if output.exit_code.unwrap_or(0) != 0 {
            bail!(
                "CubeSandbox CodeQL exploration wrapper failed exit={:?} stdout={} stderr={}",
                output.exit_code,
                codeql::redact_sensitive_text(&output.stdout),
                codeql::redact_sensitive_text(&output.stderr)
            );
        }
        let envelope_path = extract_codeql_envelope_path(
            &output,
            "ARGUS_CODEQL_EXPLORATION_RESULT_PATH=",
            "CodeQL exploration",
        )?;
        let bytes = self
            .client
            .read_file(&self.sandbox, &envelope_path)
            .await
            .with_context(|| format!("reading CodeQL exploration envelope from {envelope_path}"))?;
        parse_codeql_exploration_envelope_bytes(&bytes)
    }

    pub async fn run_dependency_install_command(
        &self,
        command: &str,
    ) -> Result<CodeqlExplorationCommandOutput> {
        let script = build_exploration_command_script(command)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        if output.exit_code.unwrap_or(0) != 0 {
            bail!(
                "CubeSandbox CodeQL dependency install wrapper failed exit={:?} stdout={} stderr={}",
                output.exit_code,
                codeql::redact_sensitive_text(&output.stdout),
                codeql::redact_sensitive_text(&output.stderr)
            );
        }
        let envelope_path = extract_codeql_envelope_path(
            &output,
            "ARGUS_CODEQL_EXPLORATION_RESULT_PATH=",
            "CodeQL dependency install",
        )?;
        let bytes = self
            .client
            .read_file(&self.sandbox, &envelope_path)
            .await
            .with_context(|| {
                format!("reading CodeQL dependency-install envelope from {envelope_path}")
            })?;
        parse_codeql_exploration_envelope_bytes(&bytes)
    }

    pub async fn run_scan(
        &self,
        input: CubeSandboxCodeqlInput<'_>,
    ) -> Result<CubeSandboxCodeqlOutput> {
        if take_cancel_request(input.task_id) {
            bail!(
                "CodeQL CubeSandbox scan cancelled before CodeQL capture for task {}",
                input.task_id
            );
        }
        let payload = CubeSandboxCodeqlRequest {
            archive_b64: create_workspace_archive_b64(
                input.workspace_dir,
                input.source_dir,
                input.query_dir,
            )?,
            language: codeql::normalize_language(input.language),
            build_mode: input.build_mode.map(str::to_string),
            build_plan: input.build_plan,
            exploration_rounds: input.exploration_rounds,
            threads: input.threads,
            ram_mb: input.ram_mb,
            allow_network: input.allow_network,
        };
        let script = build_codeql_runner_script(&payload)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        let envelope_path =
            extract_codeql_envelope_path(&output, "ARGUS_CODEQL_RESULT_PATH=", "CodeQL")?;
        let bytes = self
            .client
            .read_file(&self.sandbox, &envelope_path)
            .await
            .with_context(|| format!("reading CodeQL envelope from {envelope_path}"))?;
        let mut result = parse_codeql_envelope_bytes(&bytes)?;
        result.sandbox_id = self.sandbox.sandbox_id.clone();
        Ok(result)
    }

    pub async fn cleanup(self) -> Result<()> {
        unregister_active_sandbox(&self.task_id, &self.sandbox.sandbox_id);
        self.client.delete_sandbox(&self.sandbox.sandbox_id).await
    }
}

pub async fn run_codeql_scan(
    state: &AppState,
    input: CubeSandboxCodeqlInput<'_>,
) -> Result<CubeSandboxCodeqlOutput> {
    let session = CodeqlSandboxSession::start(state, input.task_id).await?;
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
        bail!("CubeSandbox cleanup failed after CodeQL scan: {error}");
    }
    result.sandbox_id = sandbox_id;
    result.cleanup_completed = true;
    Ok(result)
}

pub async fn cancel_codeql_scan(task_id: &str) -> Result<bool> {
    CANCELLED_CODEQL_TASKS
        .lock()
        .expect("cancel set lock")
        .insert(task_id.to_string());
    let active = ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .remove(task_id);
    let Some(active) = active else {
        return Ok(false);
    };
    active.client.delete_sandbox(&active.sandbox_id).await?;
    Ok(true)
}

fn register_active_sandbox(task_id: &str, active: ActiveCodeqlSandbox) {
    ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .insert(task_id.to_string(), active);
}

fn unregister_active_sandbox(task_id: &str, sandbox_id: &str) {
    let mut active = ACTIVE_CODEQL_SANDBOXES.lock().expect("active sandbox lock");
    if active
        .get(task_id)
        .is_some_and(|current| current.sandbox_id == sandbox_id)
    {
        active.remove(task_id);
    }
}

fn take_cancel_request(task_id: &str) -> bool {
    CANCELLED_CODEQL_TASKS
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

const TEMPLATE_WAIT_TIMEOUT_SECS: u64 = 1800; // up to 30 min for first-time build

async fn ensure_template_id_or_wait(
    state: &AppState,
    config: &CubeSandboxConfig,
    task_id: &str,
) -> Result<String> {
    match template_provisioner::ensure_codeql_cpp_template_ready(state, config).await? {
        EnsureOutcome::Ready { template_id } => Ok(template_id),
        EnsureOutcome::NotEligible { reason } => {
            bail!("CubeSandbox 模板自动构建不可用: {reason}")
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
            bail!(
                "CodeQL CubeSandbox scan cancelled while waiting for template build (task {task_id})"
            );
        }
        if let Some(template_id) = template_provisioner::resolve_existing_template_id(
            state,
            config,
            TemplateKind::CodeqlCpp,
        )
        .await?
        {
            return Ok(template_id);
        }
        if let Some(record) =
            template_provisioner::get_status(state, TemplateKind::CodeqlCpp).await?
        {
            use crate::db::cubesandbox_templates::TemplateStatus;
            match record.status {
                TemplateStatus::Ready => {
                    if let Some(template_id) = record.template_id {
                        return Ok(template_id);
                    }
                    bail!("CubeSandbox template marked ready but missing template_id");
                }
                TemplateStatus::Failed => {
                    bail!(
                        "CubeSandbox 模板构建失败: {}; 可在「CodeQL 编译探索」面板点击「重建模板」重试",
                        record.error_message.unwrap_or_default()
                    );
                }
                TemplateStatus::Invalidated => {
                    bail!(
                        "CubeSandbox 模板已被标记为失效, 请在「CodeQL 编译探索」面板点击「立即构建」"
                    );
                }
                TemplateStatus::Pending | TemplateStatus::Building => {}
            }
        }
        if std::time::Instant::now() >= deadline {
            bail!(
                "CubeSandbox 模板构建超时 (>{}s); 请在「CodeQL 编译探索」面板查看日志",
                TEMPLATE_WAIT_TIMEOUT_SECS
            );
        }
        tokio::time::sleep(Duration::from_secs(5)).await;
    }
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

fn create_workspace_archive_b64(
    workspace_dir: &Path,
    source_dir: &Path,
    query_dir: &Path,
) -> Result<String> {
    let mut archive = Vec::new();
    {
        let encoder = GzEncoder::new(&mut archive, Compression::default());
        let mut builder = Builder::new(encoder);
        append_dir(&mut builder, source_dir, "source")?;
        append_dir(&mut builder, query_dir, "queries")?;
        append_optional_file(
            &mut builder,
            workspace_dir.join("build-plan/build-plan.json"),
            "build-plan/build-plan.json",
        )?;
        builder.finish()?;
        let encoder = builder.into_inner()?;
        encoder.finish()?;
    }
    Ok(STANDARD.encode(archive))
}

fn append_dir<W: Write>(builder: &mut Builder<W>, dir: &Path, archive_prefix: &str) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    let mut files = Vec::new();
    collect_files(dir, &mut files)?;
    files.sort();
    for path in files {
        let relative = path.strip_prefix(dir)?;
        let archive_path = Path::new(archive_prefix).join(relative);
        append_file_with_normalized_mode(builder, &path, &archive_path)
            .with_context(|| format!("failed to stage {}", path.display()))?;
    }
    Ok(())
}

fn append_optional_file<W: Write>(
    builder: &mut Builder<W>,
    path: impl AsRef<Path>,
    archive_path: &str,
) -> Result<()> {
    let path = path.as_ref();
    if !path.exists() {
        return Ok(());
    }
    append_file_with_normalized_mode(builder, path, Path::new(archive_path))?;
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
    header.set_mode(normalized_archive_mode(path, archive_path, &metadata));
    header.set_cksum();
    builder.append_data(&mut header, archive_path, bytes.as_slice())?;
    Ok(())
}

fn normalized_archive_mode(
    source_path: &Path,
    archive_path: &Path,
    metadata: &std::fs::Metadata,
) -> u32 {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = metadata.permissions().mode() & 0o777;
        if mode & 0o111 != 0 || should_force_executable(source_path, archive_path) {
            return 0o755;
        }
        0o644
    }
    #[cfg(not(unix))]
    {
        if should_force_executable(source_path, archive_path) {
            0o755
        } else {
            0o644
        }
    }
}

fn should_force_executable(source_path: &Path, archive_path: &Path) -> bool {
    let Some(name) = source_path
        .file_name()
        .or_else(|| archive_path.file_name())
        .and_then(|value| value.to_str())
    else {
        return false;
    };
    matches!(
        name,
        "autogen.sh"
            | "configure"
            | "bootstrap"
            | "bootstrap.sh"
            | "git-version-gen"
            | "compile"
            | "config.guess"
            | "config.sub"
            | "install-sh"
            | "missing"
            | "depcomp"
            | "test-driver"
    ) || name.ends_with(".sh")
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

/// Wrap a Python program + base64 payload into a shell script.
///
/// The payload is embedded inline via a `cat <<'__ARGUS_B64__' ... __ARGUS_B64__`
/// heredoc, written to a temp file, then passed by path to `python3 -`.
/// This avoids `argv` size limits when the payload is multi-megabyte.
fn build_payload_python_script(python_body: &str, payload_b64: &str) -> String {
    let unique = uuid::Uuid::new_v4();
    let mut script = String::new();
    script.push_str("set -e\n");
    script.push_str(&format!(
        "_ARGUS_PAYLOAD=\"/tmp/argus-payload-{unique}.b64\"\n"
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

fn build_codeql_runner_script(payload: &CubeSandboxCodeqlRequest) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(payload)?);
    Ok(build_payload_python_script(
        CUBESANDBOX_CODEQL_PY,
        &payload_b64,
    ))
}

fn build_workspace_setup_script(archive_b64: &str) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(&json!({
        "archive_b64": archive_b64,
    }))?);
    Ok(build_payload_python_script(
        CUBESANDBOX_CODEQL_SETUP_PY,
        &payload_b64,
    ))
}

fn build_exploration_command_script(command: &str) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(&json!({
        "command": command,
    }))?);
    Ok(build_payload_python_script(
        CUBESANDBOX_CODEQL_EXPLORE_PY,
        &payload_b64,
    ))
}

fn ensure_successful_process(label: &str, output: EnvdProcessOutput) -> Result<()> {
    if output.exit_code.unwrap_or(0) == 0 {
        return Ok(());
    }
    bail!(
        "{label} failed exit={:?} stdout={} stderr={}",
        output.exit_code,
        codeql::redact_sensitive_text(&output.stdout),
        codeql::redact_sensitive_text(&output.stderr)
    )
}

fn extract_codeql_envelope_path(
    output: &EnvdProcessOutput,
    marker: &str,
    label: &str,
) -> Result<String> {
    let path = output
        .stdout
        .lines()
        .rev()
        .find_map(|line| line.strip_prefix(marker))
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string);
    match path {
        Some(p) => Ok(p),
        None => bail!(
            "CubeSandbox {label} output missing result path marker (exit={:?}) stdout={} stderr={}",
            output.exit_code,
            codeql::redact_sensitive_text(&output.stdout),
            codeql::redact_sensitive_text(&output.stderr)
        ),
    }
}

fn parse_codeql_envelope_bytes(bytes: &[u8]) -> Result<CubeSandboxCodeqlOutput> {
    let parsed: CubeSandboxCodeqlEnvelope =
        serde_json::from_slice(bytes).context("decoding CodeQL envelope JSON")?;
    Ok(CubeSandboxCodeqlOutput {
        sarif_text: decode_text(&parsed.sarif_b64, "sarif")?,
        events_text: decode_text(&parsed.events_b64, "events")?,
        summary_json: parsed.summary,
        build_plan_json: parsed.build_plan,
        sandbox_id: String::new(),
        cleanup_completed: false,
    })
}

fn parse_codeql_exploration_envelope_bytes(bytes: &[u8]) -> Result<CodeqlExplorationCommandOutput> {
    let parsed: CodeqlExplorationCommandEnvelope =
        serde_json::from_slice(bytes).context("decoding CodeQL exploration envelope JSON")?;
    Ok(CodeqlExplorationCommandOutput {
        command: parsed.command,
        stdout: codeql::redact_sensitive_text(&parsed.stdout),
        stderr: codeql::redact_sensitive_text(&parsed.stderr),
        exit_code: parsed.exit_code,
        failure_category: if parsed.failure_category.trim().is_empty() {
            if parsed.exit_code == 0 {
                "none".to_string()
            } else {
                "command_failed".to_string()
            }
        } else {
            parsed.failure_category
        },
        dependency_installation: parsed.dependency_installation,
    })
}

fn decode_text(value: &str, label: &str) -> Result<String> {
    let bytes = STANDARD
        .decode(value)
        .with_context(|| format!("invalid {label} base64"))?;
    String::from_utf8(bytes).with_context(|| format!("invalid {label} utf8"))
}

pub fn capture_events_to_jsonl(events: &str) -> String {
    events
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .map(|event| serde_json::to_string(&event).unwrap_or_else(|_| "{}".to_string()))
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn summarize_captured_files(events_text: &str, known_paths: &BTreeSet<String>) -> Value {
    let captured = known_paths
        .iter()
        .filter(|path| {
            let lower = path.to_ascii_lowercase();
            lower.ends_with(".c")
                || lower.ends_with(".cc")
                || lower.ends_with(".cpp")
                || lower.ends_with(".cxx")
                || lower.ends_with(".h")
                || lower.ends_with(".hpp")
        })
        .take(50)
        .cloned()
        .collect::<Vec<_>>();
    json!({
        "database_create": "completed",
        "extractor": "cpp",
        "events_jsonl_sha256": sha256_text(events_text),
        "captured_files": captured,
    })
}

fn sha256_text(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value.as_bytes());
    format!("sha256:{:x}", hasher.finalize())
}

const CUBESANDBOX_CODEQL_PY: &str = r##"
import base64
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import time

with open(sys.argv[1], "rb") as _argus_payload_fh:
    _argus_payload_b64 = _argus_payload_fh.read().strip()
payload = json.loads(base64.b64decode(_argus_payload_b64).decode("utf-8"))
work = pathlib.Path("/tmp/argus-codeql-work")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir(parents=True)
archive_path = work / "workspace.tar.gz"
archive_path.write_bytes(base64.b64decode(payload["archive_b64"]))
with tarfile.open(archive_path, "r:gz") as bundle:
    root = work.resolve()
    for member in bundle.getmembers():
        target = (work / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"archive member escapes workspace: {member.name}")
    bundle.extractall(work)

source = work / "source"
queries = work / "queries"
database = work / "codeql-db"
sarif = work / "results.sarif"
summary = {"status": "running", "engine": "codeql", "executor": "cubesandbox"}
events = []

def event(stage, name, message, **extra):
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": "codeql",
        "executor": "cubesandbox",
        "stage": stage,
        "event": name,
        "message": message,
    }
    payload.update(extra)
    events.append(payload)

def emit_result_and_exit(status, exit_code=1, message=None):
    final_summary = {"status": status, "engine": "codeql", "executor": "cubesandbox"}
    if message:
        final_summary["message"] = message
    events_text = "\n".join(json.dumps(item, separators=(",", ":")) for item in events) + "\n"
    result = {
        "sarif_b64": "",
        "events_b64": base64.b64encode(events_text.encode("utf-8")).decode("ascii"),
        "summary": final_summary,
        "build_plan": build_plan,
    }
    # File-based envelope transport: write to sandbox file and emit only the
    # path marker so large SARIF payloads bypass the run_command stdout cap.
    result_path = "/tmp/argus-codeql-result.json"
    pathlib.Path(result_path).write_text(
        json.dumps(result, separators=(",", ":")),
        encoding="utf-8",
    )
    print("ARGUS_CODEQL_RESULT_PATH=" + result_path)
    raise SystemExit(exit_code)

def run(cmd, cwd=None):
    event("sandbox_command", "started", " ".join(shlex.quote(str(part)) for part in cmd), command=cmd, cwd=str(cwd or work))
    result = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    event(
        "sandbox_command",
        "completed" if result.returncode == 0 else "failed",
        "command exited",
        command=cmd,
        exit_code=result.returncode,
        stdout=result.stdout[-8192:],
        stderr=result.stderr[-8192:],
    )
    if result.returncode != 0:
        message = f"command failed with exit code {result.returncode}: " + " ".join(shlex.quote(str(part)) for part in cmd)
        emit_result_and_exit("scan_failed", result.returncode, message)
    return result

def run_shell(command, cwd=None, stage="sandbox_command", name="started"):
    event(stage, name, command, command=command, cwd=str(cwd or work))
    if stage == "dependency_install":
        configure_apt_mirror_if_needed(command)
        if is_apt_update_command(command):
            result = run_apt_update_with_mirrors(command, cwd=cwd)
        else:
            result = subprocess.run(with_dependency_install_timeout(command), cwd=cwd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    else:
        command_to_run = command
        result = subprocess.run(command_to_run, cwd=cwd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    event(
        stage,
        "completed" if result.returncode == 0 else "failed",
        "command exited",
        command=command,
        exit_code=result.returncode,
        stdout=result.stdout[-8192:],
        stderr=result.stderr[-8192:],
    )
    if result.returncode != 0:
        message = f"shell command failed with exit code {result.returncode}: {command}"
        emit_result_and_exit("scan_failed", result.returncode, message)
    return result

def build_plan_evidence(plan):
    evidence = {}
    for key in ["evidence_index", "evidence_json", "evidence"]:
        value = plan.get(key) if isinstance(plan, dict) else None
        if isinstance(value, dict):
            evidence.update(value)
    details = evidence.get("details")
    if isinstance(details, dict):
        evidence.update(details)
    return evidence

def with_dependency_install_timeout(command):
    if is_apt_update_command(command):
        return command
    if not is_apt_dependency_command(command):
        return command
    return "timeout 300s " + command

def dependency_install_commands(plan):
    evidence = build_plan_evidence(plan)
    commands = evidence.get("dependency_install_commands") or evidence.get("install_commands") or []
    if not isinstance(commands, list):
        return []
    safe = []
    for command in commands:
        if not isinstance(command, str):
            continue
        command = command.strip()
        if not command:
            continue
        safe.append(command)
    return safe

def is_apt_dependency_command(command):
    normalized = command.strip().lower()
    return normalized.startswith("apt-get ") or normalized.startswith("apt ")

def dependency_installation_signal(output):
    lower_output = output.lower()
    missing_dependency_tokens = [
        "python.h",
        "fatal error:",
        "command not found",
        ": command not found",
        "cannot find -l",
        "no package ",
        "package requirements",
        "required package",
        "missing dependency",
        "dependency not found",
        "pkg-config package",
        "pkg-config could not find",
        "not found in the pkg-config search path",
    ]
    if any(token in lower_output for token in missing_dependency_tokens):
        return True
    return False

def is_apt_update_command(command):
    normalized = " ".join(command.strip().lower().split())
    return normalized == "apt-get update" or normalized == "apt update"

APT_MIRRORS = [
    ("mirrors.aliyun.com", "mirrors.aliyun.com"),
    ("mirrors.tuna.tsinghua.edu.cn", "mirrors.tuna.tsinghua.edu.cn"),
    ("mirrors.ustc.edu.cn", "mirrors.ustc.edu.cn"),
    ("deb.debian.org", "security.debian.org"),
]
APT_MIRROR_CHOICE = pathlib.Path("/tmp/argus-apt-mirror-choice.json")

def configure_apt_mirror_if_needed(command):
    if not is_apt_dependency_command(command):
        return
    for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
        os.environ.pop(key, None)
    apt_conf = pathlib.Path("/etc/apt/apt.conf.d/99-argus-cubesandbox-network")
    apt_conf.parent.mkdir(parents=True, exist_ok=True)
    apt_conf.write_text(
        'Acquire::http::Proxy "false";\n'
        'Acquire::https::Proxy "false";\n'
        'Acquire::Retries "5";\n'
        'Acquire::http::Timeout "30";\n'
        'Acquire::https::Timeout "30";\n'
        'Acquire::ForceIPv4 "true";\n'
    )
    os_release = {}
    try:
        for line in pathlib.Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip().strip('"')
    except OSError:
        pass
    codename = os_release.get("VERSION_CODENAME") or "trixie"
    disabled = pathlib.Path("/etc/apt/disabled-sources.list.d")
    disabled.mkdir(parents=True, exist_ok=True)
    for source_dir in [pathlib.Path("/etc/apt/sources.list.d")]:
        if not source_dir.exists():
            continue
        for source_file in source_dir.iterdir():
            if source_file.name.endswith((".list", ".sources")) and any(token in source_file.name for token in ["cran", "r-project", "nodesource"]):
                try:
                    source_file.rename(disabled / source_file.name)
                except OSError:
                    pass
    source_list_dir = pathlib.Path("/etc/apt/sources.list.d")
    if source_list_dir.exists():
        for source_file in source_list_dir.iterdir():
            if source_file.name.endswith((".list", ".sources")):
                try:
                    source_file.rename(disabled / source_file.name)
                except OSError:
                    pass
    main_host, security_host = selected_apt_mirror()
    write_apt_sources(codename, main_host, security_host)

def selected_apt_mirror():
    try:
        choice = json.loads(APT_MIRROR_CHOICE.read_text())
        main_host = choice.get("main_host")
        security_host = choice.get("security_host")
        if main_host and security_host:
            return main_host, security_host
    except (OSError, json.JSONDecodeError):
        pass
    return APT_MIRRORS[0]

def write_apt_sources(codename, main_host, security_host):
    pathlib.Path("/etc/apt/sources.list").write_text(
        f"deb http://{main_host}/debian {codename} main\n"
        f"deb http://{main_host}/debian {codename}-updates main\n"
        f"deb http://{security_host}/debian-security {codename}-security main\n"
    )

def run_apt_update_with_mirrors(command, cwd=None):
    try:
        values = {}
        for line in pathlib.Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        codename = values.get("VERSION_CODENAME") or "trixie"
    except OSError:
        codename = "trixie"
    attempts = []
    for main_host, security_host in APT_MIRRORS:
        write_apt_sources(codename, main_host, security_host)
        result = subprocess.run("timeout 90s " + command, cwd=cwd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        attempts.append(
            f"apt mirror {main_host}/{security_host} exit={result.returncode}\n"
            + result.stdout[-4096:]
            + result.stderr[-4096:]
        )
        if result.returncode == 0:
            APT_MIRROR_CHOICE.write_text(json.dumps({"main_host": main_host, "security_host": security_host}))
            return result
    return subprocess.CompletedProcess(command, 124, "\n".join(attempts)[-8192:], "")

def resolve_working_directory(working_directory):
    raw = str(working_directory or ".").strip() or "."
    build_cwd = (source / raw).resolve()
    source_root = source.resolve()
    if build_cwd != source_root and source_root not in build_cwd.parents:
        raise SystemExit("manual build plan working_directory escapes source root")
    if not build_cwd.exists():
        raise SystemExit(f"manual build plan working_directory does not exist: {raw}")
    return build_cwd

def write_manual_build_script(commands, build_cwd):
    build_script = work / "argus-codeql-build.sh"
    script = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for command in commands:
        script.append("( cd " + shlex.quote(str(build_cwd)) + " && " + command + " )")
    build_script.write_text("\n".join(script) + "\n")
    build_script.chmod(0o755)
    return build_script

language = payload.get("language") or "cpp"
build_mode = payload.get("build_mode")
build_plan = payload.get("build_plan")
exploration_rounds = payload.get("exploration_rounds") or []
threads = str(payload.get("threads") or 0)
ram = str(payload.get("ram_mb") or 6144)

if not source.exists() or not queries.exists():
    raise SystemExit("source and queries must be staged before CodeQL scan")
codeql_path = __import__("shutil").which("codeql")
if not codeql_path:
    event("failed", "codeql_unavailable", "CodeQL CLI is not installed in CubeSandbox template")
    raise SystemExit("CodeQL CLI is not installed in CubeSandbox template")

for index, round_payload in enumerate(exploration_rounds, start=1):
    commands = round_payload.get("commands") or []
    reasoning_summary = round_payload.get("reasoning_summary") or "candidate build command selected"
    event("llm_round", "started", reasoning_summary, round=index, reasoning_summary=reasoning_summary, commands=commands)
    for command in commands:
        result = subprocess.run(command, cwd=source, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        dependency_detected = dependency_installation_signal(result.stdout + "\n" + result.stderr)
        event(
            "sandbox_command",
            "completed" if result.returncode == 0 else "failed",
            "exploration command exited",
            round=index,
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout[-8192:],
            stderr=result.stderr[-8192:],
            failure_category="none" if result.returncode == 0 else "compile_error",
            dependency_installation={"detected": dependency_detected},
        )
    event("llm_round", "completed", "exploration round completed", round=index)

event("database_create", "started", f"creating CodeQL database in CubeSandbox language={language}")
create_cmd = ["codeql", "database", "create", str(database), f"--language={language}", f"--source-root={source}", "--overwrite"]
if build_plan:
    mode = build_plan.get("build_mode") or "none"
    commands = build_plan.get("commands") or []
    working_directory = build_plan.get("working_directory") or "."
    for index, command in enumerate(dependency_install_commands(build_plan), start=1):
        event("dependency_install", "started", f"installing dependency step {index}", command=command, step=index)
        run_shell(command, cwd=source, stage="dependency_install", name="started")
        event("dependency_install", "completed", f"installed dependency step {index}", command=command, step=index)
    if mode == "manual":
        if not commands:
            raise SystemExit("manual build plan requires commands")
        build_cwd = resolve_working_directory(working_directory)
        build_script = write_manual_build_script(commands, build_cwd)
        init_cmd = ["codeql", "database", "init", str(database), f"--language={language}", f"--source-root={source}", "--overwrite"]
        run(init_cmd, cwd=source)
        event("database_trace_command", "started", "tracing full manual build plan", command=str(build_script), step=1, build_commands=commands, working_directory=str(build_cwd))
        run(["codeql", "database", "trace-command", "--working-dir", str(build_cwd), "--", str(database), str(build_script)], cwd=source)
        event("database_trace_command", "completed", "traced full manual build plan", command=str(build_script), step=1, build_commands=commands, working_directory=str(build_cwd))
        run(["codeql", "database", "finalize", str(database)], cwd=source)
    elif mode == "autobuild":
        create_cmd.append("--build-mode=autobuild")
        run(create_cmd, cwd=source)
    else:
        create_cmd.append("--build-mode=none")
        run(create_cmd, cwd=source)
elif build_mode == "autobuild":
    create_cmd.append("--build-mode=autobuild")
    run(create_cmd, cwd=source)
else:
    create_cmd.append("--build-mode=none")
    run(create_cmd, cwd=source)
event("database_create", "completed", "CodeQL database created in CubeSandbox")

event("database_analyze", "started", "running CodeQL database analyze in CubeSandbox")
run(["codeql", "database", "analyze", str(database), str(queries), "--format=sarifv2.1.0", "--output", str(sarif), "--threads", threads, "--ram", ram])
event("database_analyze", "completed", "CodeQL SARIF generated in CubeSandbox")
summary = {"status": "scan_completed", "engine": "codeql", "executor": "cubesandbox"}

events_text = "\n".join(json.dumps(item, separators=(",", ":")) for item in events) + "\n"
result = {
    "sarif_b64": base64.b64encode(sarif.read_bytes()).decode("ascii"),
    "events_b64": base64.b64encode(events_text.encode("utf-8")).decode("ascii"),
    "summary": summary,
    "build_plan": build_plan,
}
# File-based envelope transport: SARIF payloads can easily exceed the
# run_command stdout cap, so write the envelope to a sandbox file and
# emit only the path marker.
result_path = "/tmp/argus-codeql-result.json"
pathlib.Path(result_path).write_text(
    json.dumps(result, separators=(",", ":")),
    encoding="utf-8",
)
print("ARGUS_CODEQL_RESULT_PATH=" + result_path)
"##;

const CUBESANDBOX_CODEQL_SETUP_PY: &str = r#"
import base64
import json
import os
import pathlib
import subprocess
import sys
import tarfile

with open(sys.argv[1], "rb") as _argus_payload_fh:
    _argus_payload_b64 = _argus_payload_fh.read().strip()
payload = json.loads(base64.b64decode(_argus_payload_b64).decode("utf-8"))
work = pathlib.Path("/tmp/argus-codeql-work")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir(parents=True)
archive_path = work / "workspace.tar.gz"
archive_path.write_bytes(base64.b64decode(payload["archive_b64"]))
with tarfile.open(archive_path, "r:gz") as bundle:
    root = work.resolve()
    for member in bundle.getmembers():
        target = (work / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"archive member escapes workspace: {member.name}")
    bundle.extractall(work)
print("ARGUS_CODEQL_SETUP_RESULT=" + json.dumps({"status": "ok"}, separators=(",", ":")))
"#;

const CUBESANDBOX_CODEQL_EXPLORE_PY: &str = r#"
import base64
import json
import os
import pathlib
import subprocess
import sys

with open(sys.argv[1], "rb") as _argus_payload_fh:
    _argus_payload_b64 = _argus_payload_fh.read().strip()
payload = json.loads(base64.b64decode(_argus_payload_b64).decode("utf-8"))
command = payload["command"]
source = pathlib.Path("/tmp/argus-codeql-work/source")
if not source.exists():
    raise SystemExit("CodeQL exploration workspace has not been staged")

def is_apt_dependency_command(command):
    normalized = command.strip().lower()
    return normalized.startswith("apt-get ") or normalized.startswith("apt ")

def dependency_installation_signal(output):
    lower_output = output.lower()
    missing_dependency_tokens = [
        "python.h",
        "fatal error:",
        "command not found",
        ": command not found",
        "cannot find -l",
        "no package ",
        "package requirements",
        "required package",
        "missing dependency",
        "dependency not found",
        "pkg-config package",
        "pkg-config could not find",
        "not found in the pkg-config search path",
    ]
    if any(token in lower_output for token in missing_dependency_tokens):
        return True
    return False

def is_apt_update_command(command):
    normalized = " ".join(command.strip().lower().split())
    return normalized == "apt-get update" or normalized == "apt update"

APT_MIRRORS = [
    ("mirrors.aliyun.com", "mirrors.aliyun.com"),
    ("mirrors.tuna.tsinghua.edu.cn", "mirrors.tuna.tsinghua.edu.cn"),
    ("mirrors.ustc.edu.cn", "mirrors.ustc.edu.cn"),
    ("deb.debian.org", "security.debian.org"),
]
APT_MIRROR_CHOICE = pathlib.Path("/tmp/argus-apt-mirror-choice.json")

def configure_apt_mirror_if_needed(command):
    if not is_apt_dependency_command(command):
        return
    for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
        os.environ.pop(key, None)
    apt_conf = pathlib.Path("/etc/apt/apt.conf.d/99-argus-cubesandbox-network")
    apt_conf.parent.mkdir(parents=True, exist_ok=True)
    apt_conf.write_text(
        'Acquire::http::Proxy "false";\n'
        'Acquire::https::Proxy "false";\n'
        'Acquire::Retries "5";\n'
        'Acquire::http::Timeout "30";\n'
        'Acquire::https::Timeout "30";\n'
        'Acquire::ForceIPv4 "true";\n'
    )
    os_release = {}
    try:
        for line in pathlib.Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_release[key] = value.strip().strip('"')
    except OSError:
        pass
    codename = os_release.get("VERSION_CODENAME") or "trixie"
    disabled = pathlib.Path("/etc/apt/disabled-sources.list.d")
    disabled.mkdir(parents=True, exist_ok=True)
    source_list_dir = pathlib.Path("/etc/apt/sources.list.d")
    if source_list_dir.exists():
        for source_file in source_list_dir.iterdir():
            if source_file.name.endswith((".list", ".sources")) and any(token in source_file.name for token in ["cran", "r-project", "nodesource"]):
                try:
                    source_file.rename(disabled / source_file.name)
                except OSError:
                    pass
    if source_list_dir.exists():
        for source_file in source_list_dir.iterdir():
            if source_file.name.endswith((".list", ".sources")):
                try:
                    source_file.rename(disabled / source_file.name)
                except OSError:
                    pass
    main_host, security_host = selected_apt_mirror()
    write_apt_sources(codename, main_host, security_host)

def selected_apt_mirror():
    try:
        choice = json.loads(APT_MIRROR_CHOICE.read_text())
        main_host = choice.get("main_host")
        security_host = choice.get("security_host")
        if main_host and security_host:
            return main_host, security_host
    except (OSError, json.JSONDecodeError):
        pass
    return APT_MIRRORS[0]

def current_debian_codename():
    try:
        values = {}
        for line in pathlib.Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        return values.get("VERSION_CODENAME") or "trixie"
    except OSError:
        return "trixie"

def write_apt_sources(codename, main_host, security_host):
    pathlib.Path("/etc/apt/sources.list").write_text(
        f"deb http://{main_host}/debian {codename} main\n"
        f"deb http://{main_host}/debian {codename}-updates main\n"
        f"deb http://{security_host}/debian-security {codename}-security main\n"
    )

def run_apt_update_with_mirrors(command, cwd=None):
    codename = current_debian_codename()
    attempts = []
    for main_host, security_host in APT_MIRRORS:
        write_apt_sources(codename, main_host, security_host)
        result = subprocess.run("timeout 90s " + command, cwd=cwd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        attempts.append(
            f"apt mirror {main_host}/{security_host} exit={result.returncode}\n"
            + result.stdout[-4096:]
            + result.stderr[-4096:]
        )
        if result.returncode == 0:
            APT_MIRROR_CHOICE.write_text(json.dumps({"main_host": main_host, "security_host": security_host}))
            return result
    return subprocess.CompletedProcess(command, 124, "\n".join(attempts)[-8192:], "")

def with_dependency_install_timeout(command):
    if is_apt_update_command(command):
        return command
    if not is_apt_dependency_command(command):
        return command
    return "timeout 300s " + command

try:
    configure_apt_mirror_if_needed(command)
    if is_apt_update_command(command):
        result = run_apt_update_with_mirrors(command, cwd=source)
    else:
        result = subprocess.run(with_dependency_install_timeout(command), cwd=source, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    stdout = result.stdout[-8192:]
    stderr = result.stderr[-8192:]
    exit_code = result.returncode
except subprocess.TimeoutExpired as error:
    stdout = (error.stdout or "")[-8192:] if isinstance(error.stdout, str) else ""
    stderr = (error.stderr or "")[-8192:] if isinstance(error.stderr, str) else "command timed out"
    exit_code = 124
dependency_detected = dependency_installation_signal(stdout + "\n" + stderr)
payload = {
    "command": command,
    "stdout": stdout,
    "stderr": stderr,
    "exit_code": exit_code,
    "failure_category": "none" if exit_code == 0 else ("timeout" if exit_code == 124 else "compile_error"),
    "dependency_installation": {"detected": dependency_detected},
}
# File-based envelope transport: even captured stdout/stderr can exceed the
# run_command 64 KiB cap, so write the envelope and emit only the path marker.
result_path = "/tmp/argus-codeql-exploration-result.json"
pathlib.Path(result_path).write_text(
    json.dumps(payload, separators=(",", ":")),
    encoding="utf-8",
)
print("ARGUS_CODEQL_EXPLORATION_RESULT_PATH=" + result_path)
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codeql_runner_script_passes_payload_as_python_argument() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: None,
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.starts_with("set -e\n"));
        assert!(script.contains("python3 - \"$_ARGUS_PAYLOAD\" <<'PY'"));
        assert!(script.ends_with("exit $_ARGUS_RC\n"));
    }

    fn decode_embedded_payload(script: &str) -> Value {
        let payload_b64 = script
            .split("cat > \"$_ARGUS_PAYLOAD\" <<'__ARGUS_B64__'\n")
            .nth(1)
            .and_then(|tail| tail.split("\n__ARGUS_B64__").next())
            .expect("script should contain embedded payload");
        let payload = STANDARD
            .decode(payload_b64)
            .expect("payload should be valid base64");
        serde_json::from_slice(&payload).expect("payload should be valid JSON")
    }

    #[test]
    fn workspace_archive_restores_build_script_execute_bits() {
        let temp = tempfile::tempdir().expect("temp dir");
        let source = temp.path().join("source");
        let queries = temp.path().join("queries");
        std::fs::create_dir_all(&source).expect("source dir");
        std::fs::create_dir_all(&queries).expect("queries dir");
        std::fs::write(source.join("autogen.sh"), "#!/bin/sh\n").expect("autogen");
        std::fs::write(source.join("git-version-gen"), "#!/bin/sh\n").expect("version helper");
        std::fs::write(source.join("README.md"), "plain\n").expect("readme");
        std::fs::write(queries.join("qlpack.yml"), "name: test\n").expect("qlpack");

        let archive_b64 = create_workspace_archive_b64(temp.path(), &source, &queries)
            .expect("workspace archive should build");
        let archive = STANDARD.decode(archive_b64).expect("archive base64");
        let decoder = flate2::read::GzDecoder::new(archive.as_slice());
        let mut archive = tar::Archive::new(decoder);
        let mut modes = std::collections::BTreeMap::new();
        for entry in archive.entries().expect("entries") {
            let entry = entry.expect("entry");
            let path = entry.path().expect("path").display().to_string();
            modes.insert(path, entry.header().mode().expect("mode"));
        }

        assert_eq!(modes.get("source/autogen.sh"), Some(&0o755));
        assert_eq!(modes.get("source/git-version-gen"), Some(&0o755));
        assert_eq!(modes.get("source/README.md"), Some(&0o644));
    }

    #[test]
    fn codeql_runner_script_traces_multi_step_manual_plans_and_round_events() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["cmake -S . -B build", "cmake --build build"],
                "working_directory": ".",
            })),
            exploration_rounds: vec![json!({
                "reasoning_summary": "first candidate failed and becomes context",
                "commands": ["false"],
            })],
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.contains("exploration_rounds"));
        assert!(script.contains("\"llm_round\""));
        assert!(script.contains("database\", \"init\""));
        assert!(script.contains("database\", \"trace-command\""));
        assert!(script.contains("database\", \"finalize\""));
    }

    #[test]
    fn codeql_runner_script_traces_shell_wrapped_manual_plan_once() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["cmake -S . -B build", "cmake --build build"],
                "working_directory": ".",
            })),
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.contains("build_script.write_text"));
        assert!(script.contains("for command in commands:"));
        assert!(script.contains("script.append(\"( cd \""));
        assert!(script.contains("database\", \"trace-command\""));
        assert!(script.contains("\"--\", str(database), str(build_script)"));
        assert!(!script.contains("--command\", str(build_script)"));
        assert!(!script.contains("for index, command in enumerate(commands"));
    }

    #[test]
    fn codeql_runner_script_supports_project_config_working_directory() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["./configure", "make -B -j2"],
                "working_directory": "libplist-master",
            })),
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.contains("def resolve_working_directory"));
        assert!(script.contains("build_cwd = resolve_working_directory(working_directory)"));
        assert!(script.contains("f\"--source-root={source}\""));
        assert!(script.contains("\"--working-dir\", str(build_cwd)"));
        assert!(!script.contains("non-root working_directory is not supported"));
    }

    #[test]
    fn codeql_runner_script_emits_events_when_capture_command_fails() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["make -B -j2"],
                "working_directory": ".",
            })),
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.contains("def emit_result_and_exit"));
        assert!(script.contains("\"events_b64\""));
        assert!(script.contains("\"scan_failed\""));
        assert!(script.contains("ARGUS_CODEQL_RESULT_PATH="));
    }

    #[test]
    fn parse_codeql_envelope_bytes_preserves_failure_event_envelope() {
        let events = serde_json::to_string(&json!({
            "stage": "database_trace_command",
            "event": "failed",
            "stderr": "trace-command failed",
        }))
        .expect("event json");
        let events_b64 = STANDARD.encode(events);
        let envelope = json!({
            "sarif_b64": "",
            "events_b64": events_b64,
            "summary": {"status": "scan_failed", "message": "trace command failed"},
            "build_plan": {"build_mode": "manual"},
        });
        let bytes = serde_json::to_vec(&envelope).expect("envelope serializes");

        let parsed =
            parse_codeql_envelope_bytes(&bytes).expect("failure envelope bytes should parse");

        assert_eq!(parsed.summary_json["status"], "scan_failed");
        assert!(parsed.events_text.contains("database_trace_command"));
        assert_eq!(parsed.sarif_text, "");
    }

    #[test]
    fn codeql_runner_script_installs_persisted_dependency_commands_before_capture() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["make -B -j2"],
                "working_directory": ".",
                "evidence_index": {
                    "dependency_install_commands": ["apt-get update", "apt-get install -y python3-dev"]
                }
            })),
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: true,
        })
        .expect("script should build");

        assert!(script.contains("dependency_install_commands"));
        assert!(script.contains("dependency_install\", \"started\""));
        assert!(script.contains("configure_apt_mirror_if_needed(command)"));
        assert!(script.contains("timeout 300s "));
        assert!(script.contains("run_apt_update_with_mirrors"));
        assert!(script.contains("mirrors.aliyun.com"));
        assert!(script.contains("mirrors.tuna.tsinghua.edu.cn"));
        assert!(script.contains("mirrors.ustc.edu.cn"));
        assert!(script.contains("deb http://{main_host}/debian"));
        assert!(script.contains("deb http://{security_host}/debian-security"));
        let payload = decode_embedded_payload(&script);
        assert_eq!(
            payload["build_plan"]["evidence_index"]["dependency_install_commands"][0],
            "apt-get update"
        );
        assert_eq!(
            payload["build_plan"]["evidence_index"]["dependency_install_commands"][1],
            "apt-get install -y python3-dev"
        );
    }

    #[test]
    fn codeql_exploration_script_mirrors_apt_dependency_installs() {
        let script =
            build_exploration_command_script("apt-get update").expect("script should build");

        assert!(script.contains("configure_apt_mirror_if_needed(command)"));
        assert!(script.contains("run_apt_update_with_mirrors"));
        assert!(script.contains("timeout 90s "));
        assert!(script.contains("mirrors.aliyun.com"));
        assert!(script.contains("mirrors.tuna.tsinghua.edu.cn"));
        assert!(script.contains("mirrors.ustc.edu.cn"));
        assert!(script.contains("deb http://{main_host}/debian"));
        assert!(script.contains("deb http://{security_host}/debian-security"));
        let payload = decode_embedded_payload(&script);
        assert_eq!(payload["command"], "apt-get update");
    }

    #[test]
    fn codeql_exploration_script_does_not_treat_autotools_version_as_dependency() {
        let script = build_exploration_command_script("./autogen.sh").expect("script should build");

        assert!(script.contains("def dependency_installation_signal"));
        assert!(!script.contains("\"package\"]"));
        assert!(!script.contains("\"no such file or directory\""));
        assert!(script.contains("\"required package\""));
        assert!(script.contains("\"pkg-config package\""));
        assert!(script.contains("\"not found in the pkg-config search path\""));
        assert!(script.contains("\"python.h\""));
    }

    #[tokio::test]
    async fn cancel_registry_records_pre_sandbox_cancellation() {
        assert!(!cancel_codeql_scan("codeql-cancel-before-sandbox")
            .await
            .expect("cancel request should be recorded"));
        assert!(take_cancel_request("codeql-cancel-before-sandbox"));
        assert!(!take_cancel_request("codeql-cancel-before-sandbox"));
    }
}
