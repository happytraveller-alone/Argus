use std::{
    collections::HashMap,
    sync::{Arc, OnceLock},
};

use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::Value;
use tokio::sync::{broadcast, Mutex as TokioMutex};

use crate::{
    db::cubesandbox_templates::{self, CubesandboxTemplateRecord, TemplateKind, TemplateStatus},
    runtime::cubesandbox::{
        config::CubeSandboxConfig,
        cubemaster_client::{CubemasterClient, CubemasterClientConfig},
        helper::{
            run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand,
            CubeSandboxHelperOutput,
        },
    },
    state::AppState,
};

const DEFAULT_CODEQL_CPP_IMAGE_REF: &str = "argus/cubesandbox-codeql-cpp:auto";
const DEFAULT_OPENGREP_IMAGE_REF: &str = "argus/cubesandbox-opengrep:auto";

#[derive(Clone, Debug, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum EnsureOutcome {
    Ready { template_id: String },
    InProgress { record_id: String },
    NotEligible { reason: String },
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvisionEvent {
    pub record_id: String,
    pub status: String,
    pub line: Option<String>,
    pub template_id: Option<String>,
    pub error_message: Option<String>,
}

#[derive(Clone)]
struct InFlightChannel {
    sender: broadcast::Sender<ProvisionEvent>,
}

impl InFlightChannel {
    fn new() -> Self {
        let (sender, _) = broadcast::channel(256);
        Self { sender }
    }
}

static IN_FLIGHT: OnceLock<Arc<TokioMutex<HashMap<TemplateKind, InFlightChannel>>>> =
    OnceLock::new();

fn in_flight() -> Arc<TokioMutex<HashMap<TemplateKind, InFlightChannel>>> {
    IN_FLIGHT
        .get_or_init(|| Arc::new(TokioMutex::new(HashMap::new())))
        .clone()
}

/// Snapshot the set of TemplateKinds currently in-flight (provisioning).
/// Used by reconcile (Fix 9) to avoid double-invalidating kinds mid-provision.
pub async fn snapshot_in_flight_kinds() -> std::collections::HashSet<TemplateKind> {
    let lock = in_flight();
    let guard = lock.lock().await;
    guard.keys().copied().collect()
}

/// Subscribe to provisioning events for a kind. Returns Some when a build is in flight.
pub async fn subscribe(kind: TemplateKind) -> Option<broadcast::Receiver<ProvisionEvent>> {
    let lock = in_flight();
    let map = lock.lock().await;
    map.get(&kind).map(|channel| channel.sender.subscribe())
}

/// Resolve the template id for a kind via env override → system_config override → DB ready record.
/// Returns Err when none are available; caller should kick off provisioning.
pub async fn resolve_existing_template_id(
    state: &AppState,
    config: &CubeSandboxConfig,
    kind: TemplateKind,
) -> Result<Option<String>> {
    if !config.template_id.trim().is_empty() {
        return Ok(Some(config.template_id.trim().to_string()));
    }
    if kind == TemplateKind::current_opengrep()
        && !state
            .config
            .cubesandbox_opengrep_template_id
            .trim()
            .is_empty()
    {
        return Ok(Some(
            state
                .config
                .cubesandbox_opengrep_template_id
                .trim()
                .to_string(),
        ));
    }
    let active = cubesandbox_templates::get_active(state, kind).await?;
    if let Some(record) = active {
        if record.status == TemplateStatus::Ready {
            if let Some(template_id) = record.template_id.clone() {
                return Ok(Some(template_id));
            }
        }
    }
    Ok(None)
}

/// Ensure that a CodeQL C/C++ template is ready. If not, kick off provisioning.
pub async fn ensure_codeql_cpp_template_ready(
    state: &AppState,
    config: &CubeSandboxConfig,
) -> Result<EnsureOutcome> {
    if let Some(template_id) =
        resolve_existing_template_id(state, config, TemplateKind::CodeqlCpp).await?
    {
        return Ok(EnsureOutcome::Ready { template_id });
    }
    if !should_run_local_lifecycle(config)? {
        return Ok(EnsureOutcome::NotEligible {
            reason: "CubeSandbox 控制面/数据面 URL 必须指向 localhost 或 host.docker.internal 才能自动构建; 请运维手动构建并设置 CUBESANDBOX_TEMPLATE_ID".to_string(),
        });
    }
    let record = start_provision_internal(state, config, TemplateKind::CodeqlCpp).await?;
    Ok(EnsureOutcome::InProgress {
        record_id: record.id,
    })
}

/// Ensure that an Opengrep template is ready. If not, kick off provisioning.
pub async fn ensure_opengrep_template_ready(
    state: &AppState,
    config: &CubeSandboxConfig,
) -> Result<EnsureOutcome> {
    if let Some(template_id) =
        resolve_existing_template_id(state, config, current_opengrep_provision_kind()).await?
    {
        return Ok(EnsureOutcome::Ready { template_id });
    }
    if !should_run_local_lifecycle(config)? {
        return Ok(EnsureOutcome::NotEligible {
            reason: "CubeSandbox 控制面/数据面 URL 必须指向 localhost 或 host.docker.internal 才能自动构建 Opengrep 模板; 请运维手动构建并设置 CUBESANDBOX_OPENGREP_TEMPLATE_ID".to_string(),
        });
    }
    let record = start_provision_internal(state, config, current_opengrep_provision_kind()).await?;
    Ok(EnsureOutcome::InProgress {
        record_id: record.id,
    })
}

pub async fn get_status(
    state: &AppState,
    kind: TemplateKind,
) -> Result<Option<CubesandboxTemplateRecord>> {
    if let Some(active) = cubesandbox_templates::get_active(state, kind).await? {
        return Ok(Some(active));
    }
    let history = cubesandbox_templates::list_history(state, kind, 1).await?;
    Ok(history.into_iter().next())
}

/// Force a fresh provisioning run. Refuses if a record is already pending/building/ready.
pub async fn start_provision(
    state: &AppState,
    config: &CubeSandboxConfig,
    kind: TemplateKind,
) -> Result<CubesandboxTemplateRecord> {
    if let Some(active) = cubesandbox_templates::get_active(state, kind).await? {
        match active.status {
            TemplateStatus::Pending | TemplateStatus::Building => return Ok(active),
            TemplateStatus::Ready => bail!(
                "模板已就绪 (template_id={}); 如需重建请先调用 invalidate",
                active.template_id.unwrap_or_default()
            ),
            TemplateStatus::Failed | TemplateStatus::Invalidated => {}
        }
    }
    if !should_run_local_lifecycle(config)? {
        bail!(
            "CubeSandbox 控制面/数据面 URL 必须指向 localhost 或 host.docker.internal 才能自动构建"
        );
    }
    start_provision_internal(state, config, kind).await
}

pub async fn invalidate(state: &AppState, kind: TemplateKind) -> Result<u64> {
    let affected = cubesandbox_templates::mark_invalidated(state, kind).await?;
    let lock = in_flight();
    let mut map = lock.lock().await;
    map.remove(&kind);
    Ok(affected)
}

async fn start_provision_internal(
    state: &AppState,
    config: &CubeSandboxConfig,
    kind: TemplateKind,
) -> Result<CubesandboxTemplateRecord> {
    let image_ref = template_image_ref(kind).to_string();
    let record = cubesandbox_templates::insert_pending(state, kind, &image_ref).await?;

    let lock = in_flight();
    let mut map = lock.lock().await;
    if map.contains_key(&kind) {
        // Another task already running; defer to it but keep our pending record alive
        // (it will be marked invalidated once the active one completes).
        return Ok(record);
    }
    let channel = InFlightChannel::new();
    map.insert(kind, channel.clone());
    drop(map);

    let helper_command = template_helper_command(kind);
    let state_clone = state.clone();
    let config_clone = config.clone();
    let record_id = record.id.clone();
    let sender = channel.sender.clone();

    tokio::spawn(async move {
        if let Err(error) = drive_provision(
            state_clone.clone(),
            config_clone.clone(),
            kind,
            record_id.clone(),
            helper_command,
            sender.clone(),
        )
        .await
        {
            let mut message = format!("{error:#}");

            // Fail-fast cubemaster template cleanup on any provision failure.
            // Look up the partial template_id from the DB record (set by
            // update_to_building/ready on partial progress). If present, delete
            // it from CubeMaster so it does not linger as an orphan.
            if let Ok(Some(record)) =
                cubesandbox_templates::load_by_id(&state_clone, &record_id).await
            {
                if let Some(tpl_id) = record.template_id.as_deref() {
                    match build_cubemaster_client(&config_clone) {
                        Ok(cm) => match cm.delete_template(tpl_id).await {
                            Ok(()) => {
                                tracing::info!(
                                    template_id = %tpl_id,
                                    record_id = %record_id,
                                    "cubemaster template cleaned up after provision failure"
                                );
                            }
                            Err(cleanup_err) => {
                                tracing::error!(
                                    template_id = %tpl_id,
                                    record_id = %record_id,
                                    error = %cleanup_err,
                                    "cubemaster template cleanup failed after provision failure"
                                );
                                message = format!(
                                    "{message}\ncubemaster cleanup failed: {cleanup_err:#}"
                                );
                            }
                        },
                        Err(build_err) => {
                            tracing::error!(
                                record_id = %record_id,
                                error = %build_err,
                                "failed to build cubemaster client for cleanup"
                            );
                            message =
                                format!("{message}\ncubemaster client init failed: {build_err:#}");
                        }
                    }
                } else {
                    tracing::info!(
                        record_id = %record_id,
                        "failure before template_id was recorded — nothing to clean up in cubemaster"
                    );
                }
            }

            let _ =
                cubesandbox_templates::update_to_failed(&state_clone, &record_id, &message).await;
            let _ = sender.send(ProvisionEvent {
                record_id: record_id.clone(),
                status: TemplateStatus::Failed.as_str().to_string(),
                line: None,
                template_id: None,
                error_message: Some(message),
            });
        }
        let lock = in_flight();
        let mut map = lock.lock().await;
        map.remove(&kind);
    });

    Ok(record)
}

pub fn template_image_ref(kind: TemplateKind) -> &'static str {
    match kind {
        TemplateKind::CodeqlCpp => DEFAULT_CODEQL_CPP_IMAGE_REF,
        TemplateKind::Opengrep | TemplateKind::OpengrepDedicated => DEFAULT_OPENGREP_IMAGE_REF,
    }
}

pub fn template_helper_command(kind: TemplateKind) -> CubeSandboxHelperCommand {
    match kind {
        TemplateKind::CodeqlCpp => CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
        TemplateKind::Opengrep | TemplateKind::OpengrepDedicated => {
            CubeSandboxHelperCommand::ProvisionOpengrepTemplate
        }
    }
}

pub fn current_opengrep_provision_kind() -> TemplateKind {
    TemplateKind::current_opengrep()
}

async fn drive_provision(
    state: AppState,
    config: CubeSandboxConfig,
    kind: TemplateKind,
    record_id: String,
    helper_command: CubeSandboxHelperCommand,
    sender: broadcast::Sender<ProvisionEvent>,
) -> Result<()> {
    let _ = sender.send(ProvisionEvent {
        record_id: record_id.clone(),
        status: TemplateStatus::Building.as_str().to_string(),
        line: Some("starting helper invocation".to_string()),
        template_id: None,
        error_message: None,
    });
    let _ = cubesandbox_templates::update_to_building(&state, &record_id, None).await?;

    let CubeSandboxHelperOutput {
        success,
        exit_code,
        stdout_tail,
        stderr_tail,
    } = run_helper_command(&config, helper_command).await?;

    for line in stdout_tail
        .lines()
        .chain(stderr_tail.lines())
        .filter(|l| !l.trim().is_empty())
    {
        let _ = cubesandbox_templates::append_build_log(&state, &record_id, line).await;
        let _ = sender.send(ProvisionEvent {
            record_id: record_id.clone(),
            status: TemplateStatus::Building.as_str().to_string(),
            line: Some(line.to_string()),
            template_id: None,
            error_message: None,
        });
    }

    let parsed = parse_provision_result(&stdout_tail);

    if !success {
        let reason = parsed
            .as_ref()
            .and_then(|payload| payload.error_summary())
            .unwrap_or_else(|| {
                format!(
                    "helper exit_code={} stderr_tail={}",
                    exit_code.unwrap_or(-1),
                    stderr_tail.trim()
                )
            });
        bail!("helper command failed: {reason}");
    }

    let payload = parsed.context("helper did not emit PROVISION_RESULT line")?;
    let template_id = payload
        .template_id
        .clone()
        .context("provision result missing template_id")?;
    if !payload.status.eq_ignore_ascii_case("READY") {
        bail!(
            "provision result status was {} (template_id={:?})",
            payload.status,
            payload.template_id
        );
    }
    let _ = cubesandbox_templates::update_to_ready(
        &state,
        &record_id,
        &template_id,
        payload.artifact_id.as_deref(),
    )
    .await?;

    // Record the Dockerfile fingerprint at provision-success time so reconcile
    // can detect stale templates on next startup (Signal-A).
    match crate::runtime::cubesandbox::reconcile::compute_dockerfile_fingerprint(kind) {
        Ok(fp) => {
            if let Err(e) =
                cubesandbox_templates::set_image_fingerprint(&state, &template_id, &fp).await
            {
                tracing::warn!(
                    template_id = %template_id,
                    error = %e,
                    "failed to store image_fingerprint after provision — reconcile will treat as no fingerprint"
                );
            }
        }
        Err(e) => {
            tracing::warn!(
                template_id = %template_id,
                error = %e,
                "compute_dockerfile_fingerprint failed after provision — image_fingerprint not stored"
            );
        }
    }

    let _ = sender.send(ProvisionEvent {
        record_id,
        status: TemplateStatus::Ready.as_str().to_string(),
        line: Some(format!("template ready: {template_id}")),
        template_id: Some(template_id),
        error_message: None,
    });
    Ok(())
}

#[derive(Debug, Clone)]
struct ProvisionResult {
    template_id: Option<String>,
    artifact_id: Option<String>,
    status: String,
}

impl ProvisionResult {
    fn error_summary(&self) -> Option<String> {
        if self.status.eq_ignore_ascii_case("READY") {
            None
        } else {
            Some(format!("status={}", self.status))
        }
    }
}

fn build_cubemaster_client(config: &CubeSandboxConfig) -> Result<CubemasterClient> {
    CubemasterClient::new(
        CubemasterClientConfig {
            base_url: config.cubemaster_base_url.clone(),
            cleanup_timeout_seconds: config.cubemaster_cleanup_timeout_seconds,
            instance_type: "cubebox".to_string(),
        },
        config.clone(),
    )
}

fn parse_provision_result(stdout: &str) -> Option<ProvisionResult> {
    for line in stdout.lines().rev() {
        let trimmed = line.trim();
        let Some(payload) = trimmed.strip_prefix("PROVISION_RESULT=") else {
            continue;
        };
        let value: Value = match serde_json::from_str(payload) {
            Ok(value) => value,
            Err(_) => continue,
        };
        return Some(ProvisionResult {
            template_id: value
                .get("template_id")
                .and_then(|v| v.as_str().map(|s| s.to_string())),
            artifact_id: value
                .get("artifact_id")
                .and_then(|v| v.as_str().map(|s| s.to_string())),
            status: value
                .get("status")
                .and_then(|v| v.as_str().map(|s| s.to_string()))
                .unwrap_or_else(|| "UNKNOWN".to_string()),
        });
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_provision_result_extracts_fields() {
        let stdout = "noise\nPROVISION_RESULT={\"template_id\":\"tpl-x\",\"artifact_id\":\"rfs-y\",\"status\":\"READY\",\"job_id\":\"j-1\",\"image_ref\":\"i\"}\n";
        let parsed = parse_provision_result(stdout).expect("should parse");
        assert_eq!(parsed.template_id.as_deref(), Some("tpl-x"));
        assert_eq!(parsed.artifact_id.as_deref(), Some("rfs-y"));
        assert_eq!(parsed.status, "READY");
    }

    #[test]
    fn parse_provision_result_returns_none_when_missing() {
        assert!(parse_provision_result("hello\nworld\n").is_none());
    }

    #[test]
    fn parse_provision_result_picks_last_match() {
        let stdout = "PROVISION_RESULT={\"template_id\":\"old\",\"status\":\"FAILED\"}\nPROVISION_RESULT={\"template_id\":\"new\",\"status\":\"READY\"}\n";
        let parsed = parse_provision_result(stdout).expect("should parse");
        assert_eq!(parsed.template_id.as_deref(), Some("new"));
        assert_eq!(parsed.status, "READY");
    }

    #[test]
    fn provision_mapping_keeps_codeql_and_maps_dedicated_opengrep() {
        assert_eq!(
            template_image_ref(TemplateKind::CodeqlCpp),
            DEFAULT_CODEQL_CPP_IMAGE_REF
        );
        assert_eq!(
            template_helper_command(TemplateKind::CodeqlCpp),
            CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate
        );
        assert_eq!(
            template_image_ref(TemplateKind::current_opengrep()),
            DEFAULT_OPENGREP_IMAGE_REF
        );
        assert_eq!(
            template_helper_command(TemplateKind::current_opengrep()),
            CubeSandboxHelperCommand::ProvisionOpengrepTemplate
        );
    }

    #[test]
    fn opengrep_provision_current_kind_is_dedicated() {
        assert_eq!(
            current_opengrep_provision_kind(),
            TemplateKind::OpengrepDedicated
        );
        assert_ne!(current_opengrep_provision_kind(), TemplateKind::Opengrep);
    }
}
