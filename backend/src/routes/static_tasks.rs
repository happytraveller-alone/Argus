use std::{
    collections::{BTreeMap, HashSet},
    env,
    num::NonZeroUsize,
    path::{Path, PathBuf},
    sync::{Arc, Condvar, LazyLock, Mutex},
};

use async_stream::stream;
use axum::http::StatusCode;
use axum::{
    extract::{Multipart, Path as AxumPath, Query, State},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse,
    },
    routing::{get, post},
    Extension, Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::{
    archive::{
        collect_relative_paths_from_directory, extract_archive_path_to_directory,
        read_file_lines_from_archive_path,
    },
    db::{codeql_build_plans, projects, system_config, task_state},
    error::ApiError,
    llm_rule,
    runtime::{
        a3s_box_runner,
        intelligent::code_intel::{
            cache::CodeGraphCache, codegraph_client::CodeGraphClient, CodeIntelligence,
        },
        runner::{
            self, ContainerRuntime, RunnerMount, RunnerMountPlan, RunnerSpec, SCANNER_MOUNT_PATH,
        },
        shutdown::ShutdownGate,
    },
    scan::{codeql, joern, opengrep, scope_filters},
    state::{AppState, StoredProjectArchive},
};

static OPENGREP_RESOURCE_SCHEDULER: LazyLock<OpengrepResourceScheduler> =
    LazyLock::new(OpengrepResourceScheduler::from_environment);

#[derive(Clone, Debug, Default)]
struct CodeqlTaskOptions {
    languages: Vec<String>,
    build_mode: Option<String>,
    allow_network: Option<bool>,
    reset_build_plan: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum StaticEngineKind {
    Opengrep,
    Codeql,
    Joern,
}

impl StaticEngineKind {
    fn from_optional(value: Option<&str>) -> Result<Self, ApiError> {
        match value.map(str::trim).filter(|value| !value.is_empty()) {
            None => Ok(Self::Opengrep),
            Some(value) => Self::from_value(value).ok_or_else(|| {
                ApiError::BadRequest(format!(
                    "unsupported static scan engine '{value}'; supported engines: opengrep, codeql, joern"
                ))
            }),
        }
    }

    fn from_value(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "opengrep" => Some(Self::Opengrep),
            "codeql" => Some(Self::Codeql),
            "joern" => Some(Self::Joern),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Opengrep => "opengrep",
            Self::Codeql => "codeql",
            Self::Joern => "joern",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum OpengrepSandboxKind {
    DockerfileContainer,
    A3sBox,
}

impl OpengrepSandboxKind {
    fn from_value(value: Option<&str>) -> Self {
        match value
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase()
            .as_str()
        {
            "a3s_box" | "a3s-box" | "box" | "a3sbox" => Self::A3sBox,
            _ => Self::DockerfileContainer,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::DockerfileContainer => "dockerfile_container",
            Self::A3sBox => "a3s_box",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct OpengrepTaskOptions {
    sandbox: OpengrepSandboxKind,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/rules", get(list_opengrep_rules))
        .route("/rules/stats", get(get_opengrep_rule_stats))
        .route("/rules/generating/status", get(get_generating_rules))
        .route("/rules/create", post(create_opengrep_rule_from_patch))
        .route("/rules/create-generic", post(create_opengrep_generic_rule))
        .route("/rules/select", post(batch_update_opengrep_rules))
        .route("/rules/upload", post(upload_opengrep_rules_archive))
        .route(
            "/rules/upload/directory",
            post(upload_opengrep_rules_directory),
        )
        .route("/rules/upload/json", post(upload_opengrep_rule_json))
        .route("/rules/upload/patch-archive", post(upload_patch_archive))
        .route(
            "/rules/upload/patch-directory",
            post(upload_patch_directory),
        )
        .route(
            "/rules/{rule_id}",
            get(get_opengrep_rule)
                .put(toggle_opengrep_rule)
                .patch(update_opengrep_rule)
                .delete(delete_opengrep_rule),
        )
        .route("/tasks", get(list_opengrep_tasks).post(create_static_task))
        .route("/codeql/rules", get(list_codeql_rules))
        .route("/codeql/rules/stats", get(get_codeql_rule_stats))
        .route(
            "/codeql/tasks",
            get(list_codeql_tasks).post(create_codeql_task),
        )
        .route(
            "/codeql/tasks/{task_id}",
            get(get_codeql_task).delete(delete_codeql_task),
        )
        .route(
            "/codeql/tasks/{task_id}/interrupt",
            post(interrupt_codeql_task),
        )
        .route("/codeql/tasks/{task_id}/progress", get(get_codeql_progress))
        .route("/codeql/tasks/{task_id}/stream", get(stream_codeql_task))
        .route(
            "/codeql/projects/{project_id}/build-plan/reset",
            post(reset_codeql_project_build_plan),
        )
        .route(
            "/codeql/tasks/{task_id}/findings",
            get(list_codeql_findings),
        )
        .route(
            "/codeql/tasks/{task_id}/findings/{finding_id}/context",
            get(get_codeql_finding_context),
        )
        .route(
            "/codeql/tasks/{task_id}/findings/{finding_id}",
            get(get_codeql_finding),
        )
        .route(
            "/codeql/findings/{finding_id}/status",
            post(update_codeql_finding_status),
        )
        .route(
            "/joern/tasks",
            get(list_joern_tasks).post(create_joern_task),
        )
        .route(
            "/joern/tasks/{task_id}",
            get(get_joern_task).delete(delete_joern_task),
        )
        .route(
            "/joern/tasks/{task_id}/interrupt",
            post(interrupt_joern_task),
        )
        .route("/joern/tasks/{task_id}/progress", get(get_joern_progress))
        .route("/joern/tasks/{task_id}/findings", get(list_joern_findings))
        .route(
            "/joern/tasks/{task_id}/findings/{finding_id}/context",
            get(get_joern_finding_context),
        )
        .route(
            "/joern/tasks/{task_id}/findings/{finding_id}",
            get(get_joern_finding),
        )
        .route(
            "/joern/findings/{finding_id}/status",
            post(update_joern_finding_status),
        )
        .route(
            "/tasks/{task_id}",
            get(get_opengrep_task).delete(delete_opengrep_task),
        )
        .route("/tasks/{task_id}/ai-analysis", post(ai_analysis))
        .route("/tasks/{task_id}/ai-analyze-code", post(ai_analyze_code))
        .route(
            "/tasks/{task_id}/ai-evaluate-rules",
            post(ai_evaluate_rules),
        )
        .route("/tasks/{task_id}/ai-suggest-fixes", post(ai_suggest_fixes))
        .route(
            "/tasks/{task_id}/ai-analysis/start",
            post(ai_analysis_start),
        )
        .route(
            "/tasks/{task_id}/ai-analysis/status",
            get(ai_analysis_status),
        )
        .route("/tasks/{task_id}/interrupt", post(interrupt_opengrep_task))
        .route("/tasks/{task_id}/progress", get(get_opengrep_progress))
        .route("/tasks/{task_id}/findings", get(list_opengrep_findings))
        .route(
            "/tasks/{task_id}/findings/{finding_id}/context",
            get(get_opengrep_finding_context),
        )
        .route(
            "/tasks/{task_id}/findings/{finding_id}",
            get(get_opengrep_finding),
        )
        .route(
            "/findings/{finding_id}/status",
            post(update_opengrep_finding_status),
        )
        .route("/cache/repo-stats", get(get_repo_cache_stats))
        .route("/cache/cleanup-unused", post(cleanup_unused_cache))
        .route("/cache/clear-all", post(clear_all_cache))
}

#[derive(Clone, Debug)]
struct OpengrepResourceScheduler {
    inner: Arc<OpengrepResourceSchedulerInner>,
}

#[derive(Debug)]
struct OpengrepResourceSchedulerInner {
    state: Mutex<OpengrepResourceState>,
    available: Condvar,
}

#[derive(Debug)]
struct OpengrepResourceState {
    total_cores: usize,
    used_cores: usize,
    active_project_ids: HashSet<String>,
}

#[derive(Debug)]
struct OpengrepResourcePermit {
    scheduler: OpengrepResourceScheduler,
    allocated_cores: usize,
    total_cores: usize,
    project_id: Option<String>,
}

#[derive(Clone, Copy, Debug)]
struct OpengrepRunnerResources {
    jobs: usize,
    cpu_limit: f64,
    allocated_cores: usize,
    total_cores: usize,
}

impl OpengrepResourceScheduler {
    fn from_environment() -> Self {
        Self::new(detect_opengrep_available_cores())
    }

    fn new(total_cores: usize) -> Self {
        Self {
            inner: Arc::new(OpengrepResourceSchedulerInner {
                state: Mutex::new(OpengrepResourceState {
                    total_cores: total_cores.max(1),
                    used_cores: 0,
                    active_project_ids: HashSet::new(),
                }),
                available: Condvar::new(),
            }),
        }
    }

    fn acquire_for_project(
        &self,
        project_id: &str,
        requested_cores: Option<usize>,
    ) -> OpengrepResourcePermit {
        self.acquire_inner(requested_cores, Some(project_id.to_string()))
    }

    fn acquire_inner(
        &self,
        requested_cores: Option<usize>,
        project_id: Option<String>,
    ) -> OpengrepResourcePermit {
        let mut state = self.inner.state.lock().expect("opengrep resource lock");
        loop {
            if let Some(allocated_cores) =
                next_opengrep_allocation(&state, requested_cores, project_id.as_deref())
            {
                state.used_cores += allocated_cores;
                if let Some(project_id) = &project_id {
                    state.active_project_ids.insert(project_id.clone());
                }
                return OpengrepResourcePermit {
                    scheduler: self.clone(),
                    allocated_cores,
                    total_cores: state.total_cores,
                    project_id,
                };
            }
            state = self
                .inner
                .available
                .wait(state)
                .expect("opengrep resource wait");
        }
    }
}

impl Drop for OpengrepResourcePermit {
    fn drop(&mut self) {
        let mut state = self
            .scheduler
            .inner
            .state
            .lock()
            .expect("opengrep resource lock");
        state.used_cores = state.used_cores.saturating_sub(self.allocated_cores);
        if let Some(project_id) = &self.project_id {
            state.active_project_ids.remove(project_id);
        }
        self.scheduler.inner.available.notify_all();
    }
}

fn detect_opengrep_available_cores() -> usize {
    env::var("OPENGREP_AVAILABLE_CORES")
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .filter(|value| *value > 0)
        .or_else(|| {
            std::thread::available_parallelism()
                .ok()
                .map(NonZeroUsize::get)
        })
        .unwrap_or(1)
}

fn next_opengrep_allocation(
    state: &OpengrepResourceState,
    requested_cores: Option<usize>,
    project_id: Option<&str>,
) -> Option<usize> {
    if project_id.is_some_and(|id| state.active_project_ids.contains(id)) {
        return None;
    }

    let remaining_cores = state.total_cores.saturating_sub(state.used_cores);
    if remaining_cores == 0 {
        return None;
    }

    let allocated_cores = requested_cores
        .filter(|value| *value > 0)
        .unwrap_or_else(|| (remaining_cores / 2).max(1))
        .min(state.total_cores);

    if allocated_cores > remaining_cores {
        return None;
    }

    let post_launch_remaining = remaining_cores.saturating_sub(allocated_cores);
    if state.used_cores > 0 && post_launch_remaining < 2 {
        return None;
    }

    Some(allocated_cores)
}

fn requested_opengrep_cpu_cores(config: &crate::config::AppConfig) -> Option<usize> {
    if config.opengrep_runner_cpu_limit_explicit && config.opengrep_runner_cpu_limit > 0.0 {
        Some(config.opengrep_runner_cpu_limit.ceil() as usize)
    } else {
        None
    }
}

fn resolve_opengrep_runner_resources(
    config: &crate::config::AppConfig,
    permit: &OpengrepResourcePermit,
) -> OpengrepRunnerResources {
    let jobs = if config.opengrep_scan_jobs_explicit && config.opengrep_scan_jobs > 0 {
        config.opengrep_scan_jobs
    } else {
        permit.allocated_cores.max(1)
    };
    let cpu_limit =
        if config.opengrep_runner_cpu_limit_explicit && config.opengrep_runner_cpu_limit > 0.0 {
            config.opengrep_runner_cpu_limit
        } else {
            permit.allocated_cores.max(1) as f64
        };

    OpengrepRunnerResources {
        jobs,
        cpu_limit,
        allocated_cores: permit.allocated_cores,
        total_cores: permit.total_cores,
    }
}

#[derive(Debug, Deserialize)]
struct ListQuery {
    project_id: Option<String>,
    #[serde(rename = "projectId")]
    project_id_alias: Option<String>,
    status: Option<String>,
    source: Option<String>,
    keyword: Option<String>,
    language: Option<String>,
    confidence: Option<String>,
    severity: Option<String>,
    is_active: Option<bool>,
    skip: Option<usize>,
    limit: Option<usize>,
}

#[derive(Debug, Deserialize)]
struct StatusQuery {
    status: String,
}

#[derive(Debug, Deserialize)]
struct ProgressQuery {
    include_logs: Option<bool>,
}

async fn list_opengrep_rules(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Value>, ApiError> {
    let filtered = filter_opengrep_rules(merged_opengrep_rules(&state).await?, &query);
    let total = filtered.len();
    let items = filtered
        .into_iter()
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
        .map(|record| opengrep_rule_value(&record))
        .collect::<Vec<_>>();
    Ok(Json(json!({
        "data": items,
        "total": total,
    })))
}

async fn get_opengrep_rule_stats(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let rules = merged_opengrep_rules(&state)
        .await?
        .into_iter()
        .filter(|rule| rule.severity.eq_ignore_ascii_case("ERROR"))
        .collect::<Vec<_>>();

    let mut languages = std::collections::BTreeSet::new();
    let mut vulnerability_types = std::collections::BTreeSet::new();
    let active = rules.iter().filter(|rule| rule.is_active).count();

    for rule in &rules {
        let language = rule.language.trim().to_ascii_lowercase();
        if !language.is_empty() {
            languages.insert(language);
        }
        if let Some(cwe) = &rule.cwe {
            for item in cwe {
                let normalized = item.trim();
                if !normalized.is_empty() {
                    vulnerability_types.insert(normalized.to_string());
                }
            }
        }
    }

    let total = rules.len();
    Ok(Json(json!({
        "total": total,
        "active": active,
        "inactive": total.saturating_sub(active),
        "language_count": languages.len(),
        "languages": languages.into_iter().collect::<Vec<_>>(),
        "vulnerability_type_count": vulnerability_types.len(),
    })))
}

async fn get_generating_rules() -> Json<Vec<Value>> {
    Json(Vec::new())
}

async fn list_codeql_rules(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Value>, ApiError> {
    let assets = crate::scan::codeql_rules::load_rule_assets(&state)
        .await
        .map_err(|e| ApiError::Internal(format!("failed to load codeql rules: {e}")))?;

    let filtered: Vec<_> = if let Some(ref keyword) = query.keyword {
        let kw = keyword.to_ascii_lowercase();
        assets
            .into_iter()
            .filter(|a| {
                a.asset_path.to_ascii_lowercase().contains(&kw)
                    || a.metadata_json
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_ascii_lowercase()
                        .contains(&kw)
            })
            .collect()
    } else {
        assets
    };

    let filtered: Vec<_> = if let Some(ref language) = query.language {
        let lang = language.to_ascii_lowercase();
        filtered
            .into_iter()
            .filter(|a| {
                let parts: Vec<&str> = a.asset_path.split('/').collect();
                parts
                    .get(1)
                    .map(|l| l.to_ascii_lowercase() == lang)
                    .unwrap_or(false)
            })
            .collect()
    } else {
        filtered
    };

    let total = filtered.len();
    let items: Vec<Value> = filtered
        .into_iter()
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
        .map(|asset| {
            let parts: Vec<&str> = asset.asset_path.split('/').collect();
            let language = parts.get(1).unwrap_or(&"unknown").to_string();
            let filename = parts.last().unwrap_or(&"").to_string();
            let name = asset
                .metadata_json
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or(&filename)
                .to_string();
            json!({
                "id": asset.sha256,
                "name": name,
                "language": language,
                "asset_path": asset.asset_path,
                "file_format": asset.file_format,
                "source": asset.source_kind,
                "is_active": true,
                "metadata": asset.metadata_json,
                "content": asset.content,
            })
        })
        .collect();

    Ok(Json(json!({
        "data": items,
        "total": total,
    })))
}

async fn get_codeql_rule_stats(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let assets = crate::scan::codeql_rules::load_rule_assets(&state)
        .await
        .map_err(|e| ApiError::Internal(format!("failed to load codeql rules: {e}")))?;

    let mut languages = std::collections::BTreeSet::new();
    for asset in &assets {
        let parts: Vec<&str> = asset.asset_path.split('/').collect();
        if let Some(lang) = parts.get(1) {
            languages.insert(lang.to_string());
        }
    }

    let total = assets.len();
    Ok(Json(json!({
        "total": total,
        "active": total,
        "inactive": 0,
        "language_count": languages.len(),
        "languages": languages.into_iter().collect::<Vec<_>>(),
    })))
}

async fn get_opengrep_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let rule = find_opengrep_rule(&state, &rule_id).await?;
    Ok(Json(opengrep_rule_detail_value(&rule)))
}

async fn toggle_opengrep_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    let current = find_opengrep_rule(&state, &rule_id).await?;
    let next_active = !current.is_active;
    let mut rule = current.clone();
    rule.is_active = next_active;
    snapshot.opengrep_rules.insert(rule_id.clone(), rule);
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "opengrep rule toggled in rust backend",
        "rule_id": rule_id,
        "is_active": next_active,
    })))
}

async fn delete_opengrep_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    snapshot.opengrep_rules.remove(&rule_id);
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "opengrep rule deleted in rust backend",
        "rule_id": rule_id,
    })))
}

async fn create_opengrep_rule_from_patch(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let repo_name =
        optional_string(&payload, "repo_name").unwrap_or_else(|| "generated".to_string());
    let commit_hash =
        optional_string(&payload, "commit_hash").unwrap_or_else(|| Uuid::new_v4().to_string());
    let repo_owner =
        optional_string(&payload, "repo_owner").unwrap_or_else(|| "generated".to_string());
    let commit_content = optional_string(&payload, "commit_content").unwrap_or_default();
    let patch_filename = format!("github.com_{repo_owner}_{repo_name}_{commit_hash}.patch");
    let patch_info = llm_rule::patch::process_patch_text(&patch_filename, &commit_content);
    let record = task_state::OpengrepRuleRecord {
        id: format!("patch:{}", Uuid::new_v4()),
        name: patch_info
            .as_ref()
            .map(|info| format!("{}-{}", info.repo_name, info.commit_id))
            .unwrap_or_else(|| format!("{repo_name}-{commit_hash}")),
        language: patch_info
            .as_ref()
            .and_then(|info| info.file_changes.first())
            .map(|change| change.language.clone())
            .unwrap_or_else(|| "generic".to_string()),
        severity: "ERROR".to_string(),
        confidence: Some("MEDIUM".to_string()),
        description: Some("patch-derived rule shell created in rust backend".to_string()),
        cwe: None,
        source: "patch".to_string(),
        correct: true,
        is_active: true,
        created_at: now_rfc3339(),
        pattern_yaml: if commit_content.trim().is_empty() {
            "rules: []".to_string()
        } else {
            commit_content.clone()
        },
        patch: if commit_content.trim().is_empty() {
            None
        } else {
            Some(commit_content)
        },
    };
    upsert_opengrep_rule(&state, record.clone()).await?;
    Ok(Json(opengrep_rule_detail_value(&record)))
}

async fn create_opengrep_generic_rule(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let record = build_rule_record_from_payload(
        &payload,
        "rule_yaml",
        "generic",
        "json",
        None,
        None,
        Some("generic rule created in rust backend"),
    )?;
    upsert_opengrep_rule(&state, record.clone()).await?;
    Ok(Json(opengrep_rule_detail_value(&record)))
}

async fn upload_opengrep_rule_json(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let source = optional_string(&payload, "source").unwrap_or_else(|| "json".to_string());
    let description = optional_string(&payload, "description");
    let record = build_rule_record_from_payload(
        &payload,
        "pattern_yaml",
        "json",
        &source,
        description.as_deref(),
        payload.get("correct").and_then(Value::as_bool),
        None,
    )?;
    upsert_opengrep_rule(&state, record.clone()).await?;
    Ok(Json(opengrep_rule_detail_value(&record)))
}

async fn upload_opengrep_rules_archive(
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let count = persist_uploaded_opengrep_rules(&state, multipart, "upload").await?;
    Ok(Json(json!({
        "total_files": count,
        "success_count": count,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    })))
}

async fn upload_opengrep_rules_directory(
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let count = persist_uploaded_opengrep_rules(&state, multipart, "upload").await?;
    Ok(Json(json!({
        "total_files": count,
        "success_count": count,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    })))
}

async fn upload_patch_archive(
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let rule_ids = persist_uploaded_patch_rules(&state, multipart).await?;
    Ok(Json(json!({
        "rule_ids": rule_ids,
        "total_files": rule_ids.len(),
        "message": "patch archive imported in rust backend",
    })))
}

async fn upload_patch_directory(
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let rule_ids = persist_uploaded_patch_rules(&state, multipart).await?;
    Ok(Json(json!({
        "rule_ids": rule_ids,
        "total_files": rule_ids.len(),
        "message": "patch directory imported in rust backend",
    })))
}

async fn update_opengrep_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    let mut rule = find_opengrep_rule(&state, &rule_id).await?;

    if let Some(value) = optional_string(&payload, "pattern_yaml") {
        let normalized =
            llm_rule::normalize_and_validate_rule_yaml(&value).map_err(ApiError::BadRequest)?;
        rule.pattern_yaml = normalized.pattern_yaml;
        if payload.get("language").is_none() {
            rule.language = normalized.summary.primary_language().to_string();
        }
        if payload.get("severity").is_none() {
            rule.severity = normalized.summary.severity;
        }
        if payload.get("name").is_none() {
            rule.name = normalized.summary.id.clone();
        }
    }

    if let Some(value) = optional_string(&payload, "name") {
        rule.name = value;
    }
    if let Some(value) = optional_string(&payload, "language") {
        rule.language = value;
    }
    if let Some(value) = optional_string(&payload, "severity") {
        rule.severity = value;
    }
    if let Some(value) = optional_bool(&payload, "is_active") {
        rule.is_active = value;
    }
    snapshot
        .opengrep_rules
        .insert(rule_id.clone(), rule.clone());
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "opengrep rule updated in rust backend",
        "rule": opengrep_rule_detail_value(&rule),
    })))
}

async fn batch_update_opengrep_rules(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = required_bool(&payload, "is_active")?;
    let rule_ids = match payload.get("rule_ids") {
        None => Vec::new(),
        Some(value) => strict_string_array(value)
            .ok_or_else(|| ApiError::BadRequest("rule_ids must be a string array".to_string()))?,
    };
    let keyword = optional_string(&payload, "keyword");
    let language = optional_string(&payload, "language");
    let source = optional_string(&payload, "source");
    let severity = optional_string(&payload, "severity");
    let confidence = optional_string(&payload, "confidence");
    let current_is_active = match payload.get("current_is_active") {
        None => None,
        Some(value) => Some(value.as_bool().ok_or_else(|| {
            ApiError::BadRequest("current_is_active must be a boolean".to_string())
        })?),
    };

    let mut snapshot = load_task_snapshot(&state).await?;
    let current = merged_opengrep_rules_from_snapshot(&snapshot, &state).await?;
    let mut updated = 0usize;
    for mut rule in current.into_iter().filter(|rule| {
        if !rule_ids.is_empty() && !rule_ids.iter().any(|id| id == &rule.id) {
            return false;
        }
        if !contains_keyword(&rule.name, keyword.as_deref())
            && !contains_keyword(&rule.id, keyword.as_deref())
        {
            return false;
        }
        if let Some(language) = language.as_deref() {
            if !rule.language.eq_ignore_ascii_case(language) {
                return false;
            }
        }
        if let Some(source) = source.as_deref() {
            if rule.source != source {
                return false;
            }
        }
        if let Some(severity) = severity.as_deref() {
            if !rule.severity.eq_ignore_ascii_case(severity) {
                return false;
            }
        }
        if let Some(confidence) = confidence.as_deref() {
            if rule
                .confidence
                .as_deref()
                .is_none_or(|value| !value.eq_ignore_ascii_case(confidence))
            {
                return false;
            }
        }
        if let Some(current_is_active) = current_is_active {
            if rule.is_active != current_is_active {
                return false;
            }
        }
        true
    }) {
        rule.is_active = is_active;
        snapshot.opengrep_rules.insert(rule.id.clone(), rule);
        updated += 1;
    }
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "opengrep rule selection updated in rust backend",
        "updated_count": updated,
        "is_active": is_active,
    })))
}

async fn create_static_task(
    State(state): State<AppState>,
    Extension(gate): Extension<ShutdownGate>,
    Json(payload): Json<Value>,
) -> impl IntoResponse {
    if gate.is_set() {
        return (StatusCode::SERVICE_UNAVAILABLE, "server shutting down").into_response();
    }
    let engine =
        match StaticEngineKind::from_optional(optional_string(&payload, "engine").as_deref()) {
            Ok(engine) => engine,
            Err(error) => return error.into_response(),
        };
    create_static_task_for_engine(state, payload, engine)
        .await
        .into_response()
}

async fn create_codeql_task(
    State(state): State<AppState>,
    Extension(gate): Extension<ShutdownGate>,
    Json(payload): Json<Value>,
) -> impl IntoResponse {
    if gate.is_set() {
        return (StatusCode::SERVICE_UNAVAILABLE, "server shutting down").into_response();
    }
    create_static_task_for_engine(state, payload, StaticEngineKind::Codeql)
        .await
        .into_response()
}

async fn create_joern_task(
    State(state): State<AppState>,
    Extension(gate): Extension<ShutdownGate>,
    Json(payload): Json<Value>,
) -> impl IntoResponse {
    if gate.is_set() {
        return (StatusCode::SERVICE_UNAVAILABLE, "server shutting down").into_response();
    }
    create_static_task_for_engine(state, payload, StaticEngineKind::Joern)
        .await
        .into_response()
}

async fn create_static_task_for_engine(
    state: AppState,
    payload: Value,
    engine: StaticEngineKind,
) -> Result<Json<Value>, ApiError> {
    let project_id = required_string(&payload, "project_id")?;

    let now = now_rfc3339();
    let task_id = Uuid::new_v4().to_string();
    let target_path = optional_string(&payload, "target_path").unwrap_or_else(|| ".".to_string());
    let engine_name = engine.as_str();
    let rule_ids = payload
        .get("rule_ids")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let codeql_options = if engine == StaticEngineKind::Codeql {
        Some(extract_codeql_task_options(&payload))
    } else {
        None
    };
    let opengrep_options = if engine == StaticEngineKind::Opengrep {
        Some(extract_opengrep_task_options(&payload))
    } else {
        None
    };

    let _guard = state.file_store_lock.lock().await;
    let project = projects::get_project_while_locked(&state, &project_id)
        .await
        .map_err(internal_error)?;
    let Some(project) = project else {
        return Err(ApiError::NotFound(format!(
            "project not found: {project_id}"
        )));
    };

    if matches!(engine, StaticEngineKind::Codeql | StaticEngineKind::Joern) {
        if let Err(failure) = is_cpp_project(&project) {
            return Err(ApiError::BadRequest(
                serde_json::json!({
                    "error": failure.error_code(),
                    "sub_reason": failure.sub_reason(),
                    "message": failure.user_message(),
                })
                .to_string(),
            ));
        }
    }

    let mut record = task_state::StaticTaskRecord {
        id: task_id.clone(),
        engine: engine_name.to_string(),
        project_id: project_id.clone(),
        project_name: None,
        name: optional_string(&payload, "name").unwrap_or_else(|| format!("{engine_name}-task")),
        status: "running".to_string(),
        target_path: target_path.clone(),
        total_findings: 0,
        scan_duration_ms: 0,
        files_scanned: 0,
        error_message: None,
        created_at: now.clone(),
        updated_at: Some(now.clone()),
        extra: json!({
            "engine": engine_name,
            "error_count": 0,
            "warning_count": 0,
            "high_confidence_count": 0,
            "lines_scanned": 0,
            "first_version_complete": false,
        }),
        progress: task_state::StaticTaskProgressRecord {
            progress: 0.0,
            current_stage: Some("initializing".to_string()),
            message: Some(format!("preparing {engine_name} scan")),
            started_at: Some(now.clone()),
            updated_at: Some(now.clone()),
            logs: vec![task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: "initializing".to_string(),
                message: format!("{engine_name} scan task created"),
                progress: 0.0,
                level: "info".to_string(),
            }],
            events: Vec::new(),
        },
        findings: Vec::new(),
        ai_analysis_status: None,
        ai_analysis_step: None,
        ai_analysis_step_name: None,
        ai_analysis_result: None,
        ai_analysis_error: None,
        ai_analysis_model: None,
        ai_analysis_started_at: None,
        ai_analysis_completed_at: None,
    };

    record.project_name = Some(project.name.clone());
    if let Some(extra) = record.extra.as_object_mut() {
        if let Some(options) = &codeql_options {
            extra.insert("requested_languages".to_string(), json!(options.languages));
            if let Some(build_mode) = &options.build_mode {
                extra.insert(
                    "requested_build_mode".to_string(),
                    Value::String(build_mode.clone()),
                );
            }
            if let Some(allow_network) = options.allow_network {
                extra.insert(
                    "requested_allow_network".to_string(),
                    Value::Bool(allow_network),
                );
            }
            if options.reset_build_plan {
                extra.insert("requested_build_plan_reset".to_string(), Value::Bool(true));
            }
        }
        if let Some(options) = &opengrep_options {
            extra.insert(
                "requested_opengrep_sandbox".to_string(),
                Value::String(options.sandbox.as_str().to_string()),
            );
        }
    }
    let mut snapshot = task_state::load_snapshot_unlocked(&state)
        .await
        .map_err(internal_error)?;
    snapshot
        .static_tasks
        .insert(task_id.clone(), record.clone());
    task_state::save_snapshot_unlocked(&state, &snapshot)
        .await
        .map_err(internal_error)?;

    let response = static_task_value(&record);

    let bg_state = state.clone();
    let bg_task_id = task_id.clone();
    tokio::spawn(async move {
        // Hold an ActiveScanGuard for the lifetime of this scan task.
        // shutdown_signal waits for ACTIVE_SCAN_COUNT to reach zero before
        // letting axum exit, ensuring best_effort_delete_sandbox always runs.
        let _scan_guard = crate::runtime::shutdown::ActiveScanGuard::enter();
        match engine {
            StaticEngineKind::Codeql => {
                run_codeql_scan(
                    bg_state,
                    bg_task_id,
                    project_id,
                    target_path,
                    rule_ids,
                    codeql_options.unwrap_or_default(),
                )
                .await;
            }
            StaticEngineKind::Joern => {
                run_joern_scan(bg_state, bg_task_id, project_id, target_path, rule_ids).await;
            }
            StaticEngineKind::Opengrep => {
                run_opengrep_scan(
                    bg_state,
                    bg_task_id,
                    project_id,
                    target_path,
                    rule_ids,
                    opengrep_options.unwrap_or(OpengrepTaskOptions {
                        sandbox: OpengrepSandboxKind::DockerfileContainer,
                    }),
                )
                .await;
            }
        }
    });

    Ok(Json(response))
}

async fn list_opengrep_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "opengrep", query).await
}

async fn get_opengrep_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "opengrep", &task_id).await
}

async fn delete_opengrep_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "opengrep", &task_id).await
}

async fn interrupt_opengrep_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let _ = a3s_box_runner::stop_active_task_sync(&task_id);
    interrupt_static_task(&state, "opengrep", &task_id).await
}

async fn list_codeql_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "codeql", query).await
}

async fn stream_codeql_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> impl IntoResponse {
    // Load persisted events outside the stream block to avoid borrowing state inside stream!.
    let replay_events: Vec<Value> = match find_static_task(&state, "codeql", &task_id).await {
        Ok(record) => record
            .progress
            .events
            .into_iter()
            .map(|evt| {
                let message = evt
                    .payload
                    .get("message")
                    .and_then(Value::as_str)
                    .map(String::from);
                json!({
                    "kind": evt.event_type,
                    "timestamp": evt.timestamp,
                    "message": message,
                    "data": {
                        "stage": evt.stage,
                        "progress": evt.progress,
                        "round": evt.round,
                        "payload": evt.payload,
                    },
                })
            })
            .collect(),
        Err(_) => Vec::new(),
    };

    let output = stream! {
        // Replay all persisted events in unified { kind, timestamp, message?, data? } shape.
        for unified in replay_events {
            if let Ok(data) = serde_json::to_string(&unified) {
                yield Ok::<Event, std::convert::Infallible>(Event::default().data(data));
            }
        }
        // CodeQL has no broadcast channel yet — replay-only SSE, stream closes after replay.
    };

    Sse::new(output).keep_alive(KeepAlive::default())
}

async fn get_codeql_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "codeql", &task_id).await
}

async fn delete_codeql_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "codeql", &task_id).await
}

async fn interrupt_codeql_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    tracing::info!(
        target: "argus::codeql",
        task_id = %task_id,
        "codeql scan cancellation: no-op (codeql path disabled)"
    );
    interrupt_static_task(&state, "codeql", &task_id).await
}

async fn list_joern_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "joern", query).await
}

async fn get_joern_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "joern", &task_id).await
}

async fn delete_joern_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "joern", &task_id).await
}

async fn interrupt_joern_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    interrupt_static_task(&state, "joern", &task_id).await
}

async fn get_opengrep_progress(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ProgressQuery>,
) -> Result<Json<Value>, ApiError> {
    get_static_progress(&state, "opengrep", &task_id, query).await
}

async fn get_static_progress(
    state: &AppState,
    engine: &str,
    task_id: &str,
    query: ProgressQuery,
) -> Result<Json<Value>, ApiError> {
    let record = find_static_task(state, engine, task_id).await?;
    let logs = if query.include_logs.unwrap_or(false) {
        record
            .progress
            .logs
            .iter()
            .map(|log| {
                json!({
                    "timestamp": log.timestamp,
                    "stage": log.stage,
                    "message": log.message,
                    "progress": log.progress,
                    "level": log.level,
                })
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    let events = if query.include_logs.unwrap_or(false) {
        record
            .progress
            .events
            .iter()
            .map(|event| {
                json!({
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "stage": event.stage,
                    "progress": event.progress,
                    "round": event.round,
                    "redaction": event.redaction,
                    "payload": event.payload,
                })
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    let llm_model: Option<String> = if engine == "codeql" {
        if let Some(pool) = state.db_pool.as_ref() {
            if let Ok(project_uuid) = Uuid::parse_str(&record.project_id) {
                sqlx::query_scalar(
                    "SELECT llm_model FROM rust_codeql_build_plans WHERE project_id = $1 AND llm_model IS NOT NULL ORDER BY updated_at DESC NULLS LAST LIMIT 1",
                )
                .bind(project_uuid)
                .fetch_optional(pool)
                .await
                .unwrap_or(None)
            } else {
                None
            }
        } else {
            None
        }
    } else {
        None
    };

    Ok(Json(json!({
        "task_id": record.id,
        "engine": record.engine,
        "status": record.status,
        "progress": record.progress.progress,
        "current_stage": record.progress.current_stage,
        "message": record.progress.message,
        "started_at": record.progress.started_at,
        "updated_at": record.progress.updated_at,
        "logs": logs,
        "events": events,
        "llm_model": llm_model,
    })))
}

async fn list_opengrep_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "opengrep", &task_id, &query).await
}

async fn get_codeql_progress(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ProgressQuery>,
) -> Result<Json<Value>, ApiError> {
    get_static_progress(&state, "codeql", &task_id, query).await
}

async fn get_joern_progress(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ProgressQuery>,
) -> Result<Json<Value>, ApiError> {
    get_static_progress(&state, "joern", &task_id, query).await
}

async fn reset_codeql_project_build_plan(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    projects::get_project(&state, &project_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound(format!("project not found: {project_id}")))?;
    let reset_count = reset_codeql_build_plan_for_project(&state, &project_id, "cpp")
        .await
        .map_err(internal_error)?;

    // 接力创建新的 CodeQL 任务以兑现 "重置并重新探索" 的语义。
    // Why: 仅重置 build_plan 不会触发新的 compile exploration —— 该路径只在
    // create_static_task_for_engine spawn 的后台扫描里被走到。
    let snapshot = task_state::load_snapshot(&state)
        .await
        .map_err(internal_error)?;
    let prior = snapshot
        .static_tasks
        .values()
        .filter(|r| r.engine == "codeql" && r.project_id == project_id)
        .max_by(|a, b| a.created_at.cmp(&b.created_at))
        .cloned();
    drop(snapshot);

    let new_task_id = if let Some(prior) = prior {
        let mut payload = json!({
            "project_id": project_id,
            "reset_build_plan": true,
            "name": prior.name,
            "target_path": prior.target_path,
        });
        if let Some(obj) = prior.extra.as_object() {
            if let Some(v) = obj.get("requested_languages").cloned() {
                payload["languages"] = v;
            }
            if let Some(v) = obj.get("requested_build_mode").cloned() {
                payload["build_mode"] = v;
            }
            if let Some(v) = obj.get("requested_allow_network").cloned() {
                payload["allow_network"] = v;
            }
        }
        let Json(resp) =
            create_static_task_for_engine(state.clone(), payload, StaticEngineKind::Codeql).await?;
        resp.get("id").and_then(Value::as_str).map(String::from)
    } else {
        None
    };

    Ok(Json(json!({
        "message": "CodeQL project build plan reset",
        "project_id": project_id,
        "language": "cpp",
        "reset_count": reset_count,
        "manual_editing": false,
        "task_id": new_task_id,
    })))
}

async fn list_codeql_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "codeql", &task_id, &query).await
}

async fn get_codeql_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "codeql", &task_id, &finding_id).await
}

async fn get_codeql_finding_context(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding_context(&state, "codeql", &task_id, &finding_id).await
}

async fn update_codeql_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "codeql", &finding_id, &query.status).await
}

async fn list_joern_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "joern", &task_id, &query).await
}

async fn get_joern_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "joern", &task_id, &finding_id).await
}

async fn get_joern_finding_context(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding_context(&state, "joern", &task_id, &finding_id).await
}

async fn update_joern_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "joern", &finding_id, &query.status).await
}

async fn get_opengrep_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "opengrep", &task_id, &finding_id).await
}

async fn get_opengrep_finding_context(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding_context(&state, "opengrep", &task_id, &finding_id).await
}

async fn get_static_finding_context(
    state: &AppState,
    engine: &str,
    task_id: &str,
    finding_id: &str,
) -> Result<Json<Value>, ApiError> {
    let task = find_static_task(state, engine, task_id).await?;
    let finding = get_static_finding_value(state, engine, task_id, finding_id).await?;

    let file_path = finding
        .get("resolved_file_path")
        .or_else(|| finding.get("file_path"))
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let start_line = finding
        .get("start_line")
        .and_then(Value::as_u64)
        .unwrap_or(1) as usize;
    let end_line = finding
        .get("end_line")
        .and_then(Value::as_u64)
        .unwrap_or(start_line as u64) as usize;

    let context_before = 5usize;
    let context_after = 5usize;
    let range_start = start_line.saturating_sub(context_before).max(1);
    let range_end = end_line + context_after;

    let (archive_path, archive_name) =
        resolve_project_archive_input(state, &task.project_id).await?;

    let file_path_owned = file_path.to_string();
    let lines_result = tokio::task::spawn_blocking(move || {
        read_file_lines_from_archive_path(
            &archive_path,
            &archive_name,
            &file_path_owned,
            range_start,
            range_end,
        )
    })
    .await
    .map_err(|e| ApiError::Internal(e.to_string()))?;

    let (source_lines, total_lines) = lines_result;

    let lines_json: Vec<Value> = source_lines
        .iter()
        .map(|(line_number, content)| {
            let is_hit = *line_number >= start_line && *line_number <= end_line;
            json!({
                "line_number": line_number,
                "content": content,
                "is_hit": is_hit,
            })
        })
        .collect();

    Ok(Json(json!({
        "task_id": task_id,
        "finding_id": finding_id,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "before": context_before,
        "after": context_after,
        "total_lines": total_lines,
        "lines": lines_json,
    })))
}

async fn update_opengrep_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "opengrep", &finding_id, &query.status).await
}

async fn get_repo_cache_stats() -> Json<Value> {
    Json(json!({
        "total_repositories": 0,
        "active_repositories": 0,
        "total_size_bytes": 0,
    }))
}

async fn cleanup_unused_cache() -> Json<Value> {
    Json(json!({
        "message": "cache cleanup completed in rust backend",
        "removed_entries": 0,
    }))
}

async fn clear_all_cache() -> Json<Value> {
    Json(json!({
        "message": "cache clear completed in rust backend",
        "removed_entries": 0,
    }))
}

async fn resolve_project_archive_input(
    state: &AppState,
    project_id: &str,
) -> Result<(PathBuf, String), ApiError> {
    if let Some(project) = projects::get_project(state, project_id)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?
    {
        if let Some(archive) = project.archive {
            let storage_path = PathBuf::from(&archive.storage_path);
            if storage_path.exists() {
                return Ok((storage_path, archive.original_filename));
            }
        }
    }

    let legacy_zip_path = state
        .config
        .zip_storage_path
        .join(format!("{project_id}.zip"));
    if legacy_zip_path.exists() {
        return Ok((legacy_zip_path, format!("{project_id}.zip")));
    }

    Err(ApiError::NotFound(format!(
        "project archive not found for {project_id}"
    )))
}

async fn run_opengrep_scan(
    state: AppState,
    task_id: String,
    project_id: String,
    _target_path: String,
    rule_ids: Vec<String>,
    options: OpengrepTaskOptions,
) {
    let started_at = std::time::Instant::now();
    if let Err(error) =
        run_opengrep_scan_inner(&state, &task_id, &project_id, &rule_ids, options).await
    {
        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        let _ = update_scan_task_failed(&state, &task_id, &error.to_string(), elapsed_ms).await;
    }
}

async fn run_codeql_scan(
    state: AppState,
    task_id: String,
    project_id: String,
    target_path: String,
    _rule_ids: Vec<String>,
    options: CodeqlTaskOptions,
) {
    let started_at = std::time::Instant::now();
    if let Err(error) =
        run_codeql_scan_inner(&state, &task_id, &project_id, &target_path, options).await
    {
        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        let _ = update_scan_task_failed(&state, &task_id, &error.to_string(), elapsed_ms).await;
    }
}

async fn run_joern_scan(
    state: AppState,
    task_id: String,
    project_id: String,
    target_path: String,
    _rule_ids: Vec<String>,
) {
    let started_at = std::time::Instant::now();
    if let Err(error) = run_joern_scan_inner(&state, &task_id, &project_id, &target_path).await {
        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        let _ = update_scan_task_failed(&state, &task_id, &error.to_string(), elapsed_ms).await;
    }
}

async fn run_joern_scan_inner(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    _target_path: &str,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let started_at = std::time::Instant::now();
    update_scan_progress(
        state,
        task_id,
        5.0,
        "preparing",
        "resolving project archive",
    )
    .await;

    let (archive_path, archive_name) = resolve_project_archive_input(state, project_id).await?;
    let workspace_root = scan_workspace_root();
    let workspace_dir = workspace_root
        .join("joern-runtime")
        .join(Uuid::new_v4().to_string());
    let source_dir = workspace_dir.join("source");
    let output_dir = workspace_dir.join("output");
    tokio::fs::create_dir_all(&source_dir).await?;
    tokio::fs::create_dir_all(&output_dir).await?;

    update_scan_progress(state, task_id, 15.0, "extracting", "extracting source").await;
    extract_archive_to_dir(&archive_path, &archive_name, &source_dir).await?;
    flatten_single_top_level_dir(&source_dir).await?;
    let scan_input_paths = collect_relative_paths_from_directory(&source_dir)?;
    let files_scanned = scan_input_paths.len();

    update_scan_progress(
        state,
        task_id,
        30.0,
        "preparing_rules",
        "preparing joern query package",
    )
    .await;
    let query_dir = joern::materialize_query_directory(state, &workspace_dir).await?;
    let wrapper_script = joern::build_wrapper_script(&joern::JoernOutputPaths::default());
    let wrapper_path = workspace_dir.join("argus-joern-wrapper.sh");
    tokio::fs::write(&wrapper_path, wrapper_script).await?;

    update_scan_progress(
        state,
        task_id,
        45.0,
        "building_cpg",
        "running joern CPG construction and queries",
    )
    .await;
    let spec = build_joern_runner_spec(
        &state.config,
        &workspace_dir,
        &source_dir,
        &query_dir,
        &output_dir,
    );
    let runner_result =
        tokio::task::spawn_blocking(move || crate::runtime::runner::execute(spec)).await?;
    if !runner_result.success {
        let error_msg = runner_result.error.unwrap_or_else(|| {
            format!("joern runner exited with code {}", runner_result.exit_code)
        });
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Err(format!("joern scan failed: {error_msg}").into());
    }

    update_scan_progress(state, task_id, 75.0, "processing", "parsing joern output").await;
    let parsed = joern::parse_output_dir(
        &output_dir,
        task_id,
        source_dir.to_str(),
        Some(&scan_input_paths),
        state.config.joern_results_json_limit_bytes,
    )
    .await?;

    update_scan_progress(state, task_id, 90.0, "finalizing", "saving joern findings").await;
    let elapsed_ms = started_at.elapsed().as_millis() as i64;
    store_joern_results(
        state,
        task_id,
        &parsed.findings,
        parsed.summary,
        parsed.graph_proof,
        files_scanned,
        elapsed_ms,
    )
    .await?;

    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
    Ok(())
}

async fn run_codeql_scan_inner(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    _target_path: &str,
    options: CodeqlTaskOptions,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let started_at = std::time::Instant::now();

    // ── AC3 codegraph init (Plan §AC1.D + Step 1.6) ──────────────────────────
    // Run BEFORE the existing CodeQL flow so its 30s timeout never overlaps
    // the build container lifecycle (no race). Best-effort: failure falls
    // through to the original 6-pattern probe with a degraded badge.
    update_scan_progress(
        state,
        task_id,
        2.0,
        "codegraph_handoff",
        "initialising codegraph for CodeQL language identification",
    )
    .await;
    let codegraph_handoff =
        try_init_codegraph_for_codeql_with_events(state, task_id, project_id).await;
    let language = match (options.languages.first(), codegraph_handoff.as_ref()) {
        (Some(lang), _) if !lang.trim().is_empty() => lang.clone(),
        (_, Some(handoff)) => handoff
            .primary_language
            .clone()
            .unwrap_or_else(|| "cpp".to_string()),
        _ => "cpp".to_string(),
    };
    let lang_signal_missing = options.languages.is_empty()
        || matches!(options.languages.first(), Some(l) if l.trim().is_empty());
    let codegraph_lang_missing = codegraph_handoff
        .as_ref()
        .and_then(|h| h.primary_language.as_deref())
        .is_none();
    if lang_signal_missing && codegraph_lang_missing {
        tracing::warn!(
            target: "argus::codeql",
            task_id = %task_id,
            "language_fallback_to_cpp: no codegraph or LLM language signal — falling back to cpp"
        );
        push_exploration_event(
            state,
            task_id,
            "language_fallback_to_cpp",
            "codegraph_handoff",
            3.0,
            None,
            json!({
                "reason": "no_codegraph_or_llm_signal",
                "fallback_language": "cpp",
            }),
        )
        .await;
    }

    update_scan_progress(
        state,
        task_id,
        5.0,
        "preparing",
        "resolving project archive",
    )
    .await;

    let (archive_path, archive_name) = resolve_project_archive_input(state, project_id).await?;
    let workspace_root = scan_workspace_root();
    let workspace_dir = workspace_root
        .join("codeql-runtime")
        .join(uuid::Uuid::new_v4().to_string());
    let source_dir = workspace_dir.join("source");
    let output_dir = workspace_dir.join("output");
    tokio::fs::create_dir_all(&source_dir).await?;
    tokio::fs::create_dir_all(&output_dir).await?;

    update_scan_progress(state, task_id, 10.0, "preparing", "extracting source").await;
    extract_archive_to_dir(&archive_path, &archive_name, &source_dir).await?;
    flatten_single_top_level_dir(&source_dir).await?;

    // Phase 1: Build plan check
    update_scan_progress(
        state,
        task_id,
        15.0,
        "build_plan_reuse_check",
        "checking existing build plan",
    )
    .await;

    let existing_plan =
        codeql_build_plans::load_active_project_build_plan(state, project_id, &language).await?;

    let build_plan = if options.reset_build_plan || existing_plan.is_none() {
        // Phase 2: Compile exploration
        update_scan_progress(
            state,
            task_id,
            20.0,
            "compile_sandbox",
            "starting compile exploration",
        )
        .await;

        let image = state.config.scanner_codeql_image.clone();
        let memory_mb = state.config.codeql_ram_mb;
        let max_rounds = state.config.codeql_max_build_inference_rounds;
        let allow_network = options
            .allow_network
            .unwrap_or(state.config.codeql_allow_network_during_build);

        let mut plan = run_codeql_compile_exploration(
            state,
            task_id,
            project_id,
            &source_dir,
            &language,
            &image,
            memory_mb,
            max_rounds,
            allow_network,
        )
        .await?;
        // Inject codegraph handoff into the build plan's evidence_json so the
        // downstream consumer (CodeQL build plan persistence + frontend) can
        // see the primary language + vendor paths that codegraph discovered.
        // See AC1.E.
        if let Some(handoff) = codegraph_handoff.as_ref() {
            attach_codegraph_handoff_to_plan(&mut plan, handoff);
        }

        update_scan_progress(
            state,
            task_id,
            50.0,
            "build_plan_accepted",
            "build plan determined",
        )
        .await;
        plan
    } else {
        update_scan_progress(
            state,
            task_id,
            20.0,
            "build_plan_reused",
            "reusing existing build plan",
        )
        .await;
        let rec = existing_plan.unwrap();
        crate::scan::codeql::CompileSandboxPlan {
            language: rec.language.clone(),
            target_path: rec.target_path.clone(),
            build_mode: rec.build_mode.clone(),
            commands: rec.commands.clone(),
            working_directory: rec.working_directory.clone(),
            allow_network: rec
                .evidence_json
                .get("allow_network")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
            query_suite: rec.query_suite.clone(),
            source_fingerprint: rec.source_fingerprint.clone(),
            dependency_fingerprint: rec.dependency_fingerprint.clone(),
            status: rec.status.clone(),
            evidence_json: rec.evidence_json.clone(),
            language_fallback_used: false,
        }
    };

    // Phase 3: Formal scan
    update_scan_progress(
        state,
        task_id,
        55.0,
        "scanning",
        "generating scan entrypoint",
    )
    .await;

    let entrypoint_script = generate_codeql_entrypoint_script(
        &build_plan,
        &language,
        state.config.codeql_ram_mb,
        state.config.codeql_threads,
    );
    let entrypoint_path = workspace_dir.join(".codeql-entrypoint.sh");
    tokio::fs::write(&entrypoint_path, &entrypoint_script).await?;

    update_scan_progress(
        state,
        task_id,
        60.0,
        "scanning",
        "executing codeql analysis",
    )
    .await;

    let runner_spec = build_codeql_runner_spec(&state.config, &workspace_dir, &options);

    let scan_result =
        tokio::task::spawn_blocking(move || crate::runtime::runner::execute(runner_spec)).await?;

    if !scan_result.success {
        let error_msg = scan_result
            .error
            .unwrap_or_else(|| "unknown scanner error".to_string());
        return Err(format!("codeql scan failed: {error_msg}").into());
    }

    // Phase 4: Parse results
    update_scan_progress(state, task_id, 90.0, "processing", "parsing SARIF output").await;

    let sarif_path = workspace_dir.join("output").join("results.sarif");
    if sarif_path.exists() {
        let sarif_text = tokio::fs::read_to_string(&sarif_path).await?;
        let findings = codeql::parse_sarif_output(&sarif_text, task_id, None, None);

        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        update_scan_task_completed(state, task_id, findings.len(), elapsed_ms).await?;
        store_codeql_findings(state, task_id, project_id, &findings).await?;
    } else {
        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        update_scan_task_completed(state, task_id, 0, elapsed_ms).await?;
    }

    // Cleanup workspace
    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;

    Ok(())
}

// ---------------------------------------------------------------------------
// AC3 codegraph handoff (Plan §AC1.D + Step 1.6 + 1.7 + 1.8)
// ---------------------------------------------------------------------------

/// Lightweight structure carrying the slice of codegraph state we hand off to
/// the CodeQL flow. Persisted into the build plan's `evidence_json` so
/// downstream consumers (build plan record + frontend) can see what codegraph
/// observed.
#[derive(Debug, Clone)]
struct CodegraphHandoff {
    primary_language: Option<String>,
    languages_indexed: Vec<String>,
    vendor_paths: Vec<String>,
}

impl CodegraphHandoff {
    fn to_evidence_json(&self) -> Value {
        json!({
            "primary_language": self.primary_language,
            "languages_indexed": self.languages_indexed,
            "vendor_paths": self.vendor_paths,
        })
    }
}

/// RAII guard wrapping a `CodeGraphClient`. On drop, detaches a tokio task
/// that calls `shutdown()` — mirrors `audit_pipeline/mod.rs:294-301`. Outside
/// a Tokio runtime context the Drop is a no-op (the underlying PodmanSession
/// is itself a fallback guard).
struct CodegraphHandoffGuard {
    client: Option<Arc<CodeGraphClient>>,
}

impl Drop for CodegraphHandoffGuard {
    fn drop(&mut self) {
        if let Some(client) = self.client.take() {
            // Detach shutdown so Drop never blocks. The PodmanSession's own
            // Drop is the final safety net for cancellation paths.
            tokio::spawn(async move {
                if let Err(err) = client.shutdown().await {
                    tracing::warn!(
                        target: "argus::codeql",
                        error = %err,
                        "codegraph handoff shutdown failed"
                    );
                }
            });
        }
    }
}

/// Best-effort init of codegraph for CodeQL handoff. Wraps the actual init in
/// `tokio::time::timeout(30s)` and pushes exploration events on success /
/// failure. Returns `Some(CodegraphHandoff)` on success, `None` on every
/// failure path (timeout / no archive / codegraph error).
///
/// **No `select!`** — the timeout is a straight `tokio::time::timeout().await`
/// to avoid race windows around the build container (Critic R7 fix).
async fn try_init_codegraph_for_codeql_with_events(
    state: &AppState,
    task_id: &str,
    project_id: &str,
) -> Option<CodegraphHandoff> {
    let archive_meta: StoredProjectArchive = match projects::get_project(state, project_id).await {
        Ok(Some(project)) => match project.archive {
            Some(a) => a,
            None => {
                push_exploration_event(
                    state,
                    task_id,
                    "codegraph_init_skipped_no_archive",
                    "codegraph_handoff",
                    2.5,
                    None,
                    json!({"reason": "no_archive"}),
                )
                .await;
                set_codegraph_unavailable_flag(state, task_id, "no_archive").await;
                return None;
            }
        },
        Ok(None) | Err(_) => {
            set_codegraph_unavailable_flag(state, task_id, "project_lookup_failed").await;
            return None;
        }
    };
    let sandbox_image = state.config.scanner_codeql_image.clone();
    let init_fut = try_init_codegraph_for_codeql(&archive_meta, &sandbox_image);
    match tokio::time::timeout(std::time::Duration::from_secs(30), init_fut).await {
        Ok(Ok(handoff)) => {
            push_exploration_event(
                state,
                task_id,
                "codegraph_init_completed_for_codeql",
                "codegraph_handoff",
                4.0,
                None,
                json!({
                    "primary_language": handoff.primary_language,
                    "languages_indexed": handoff.languages_indexed,
                    "vendor_paths_count": handoff.vendor_paths.len(),
                }),
            )
            .await;
            Some(handoff)
        }
        Ok(Err(err)) => {
            tracing::warn!(
                target: "argus::codeql",
                task_id = %task_id,
                error = %err,
                "codegraph_init_failed_for_codeql"
            );
            push_exploration_event(
                state,
                task_id,
                "codegraph_init_failed_for_codeql",
                "codegraph_handoff",
                3.0,
                None,
                json!({"error": err.to_string()}),
            )
            .await;
            set_codegraph_unavailable_flag(state, task_id, &err.to_string()).await;
            None
        }
        Err(_elapsed) => {
            tracing::warn!(
                target: "argus::codeql",
                task_id = %task_id,
                "codegraph_init_failed_for_codeql: 30s timeout"
            );
            push_exploration_event(
                state,
                task_id,
                "codegraph_init_failed_for_codeql",
                "codegraph_handoff",
                3.0,
                None,
                json!({"error": "timeout_30s"}),
            )
            .await;
            set_codegraph_unavailable_flag(state, task_id, "timeout_30s").await;
            None
        }
    }
}

/// Inner init: spin up CodeGraphClient (cache-aware via CodeGraphClient::init),
/// then derive primary_language + vendor_paths from the index. Drops the
/// client (which detaches shutdown via the RAII guard) before returning the
/// handoff. We do NOT keep the codegraph client alive across the build
/// container lifecycle — the handoff is a one-shot summary.
async fn try_init_codegraph_for_codeql(
    archive_meta: &StoredProjectArchive,
    sandbox_image: &str,
) -> anyhow::Result<CodegraphHandoff> {
    let cache = Arc::new(CodeGraphCache::new()?);
    let archive_path = std::path::Path::new(&archive_meta.storage_path);
    let client = CodeGraphClient::init(
        archive_path,
        &archive_meta.original_filename,
        archive_meta.sha256.clone(),
        sandbox_image,
        cache,
    )
    .await?;
    let client = Arc::new(client);
    // Wrap in RAII guard so any early return / panic still detaches shutdown.
    let guard = CodegraphHandoffGuard {
        client: Some(Arc::clone(&client)),
    };

    let languages_indexed = client.languages_indexed();
    // Pick the first indexed language as primary. Codegraph orders by
    // detection frequency in `detect_languages` so this is the dominant
    // language. CodeQL's normalize_language will canonicalise.
    let primary_language = languages_indexed.first().cloned();

    // Vendor path discovery: query codegraph for files under the canonical
    // vendor directory prefixes and bucket them by top-level segment. We avoid
    // adding a new trait surface (the plan explicitly prohibits a
    // dependency_graph trait method in v0.1) by using `search_symbol` with
    // vendor-style names.
    let vendor_paths = derive_vendor_paths_from_codegraph(client.as_ref()).await;

    drop(guard);
    Ok(CodegraphHandoff {
        primary_language,
        languages_indexed,
        vendor_paths,
    })
}

/// Best-effort vendor-path discovery. Walks `search_symbol("vendor")` /
/// `"third_party"` / `"node_modules"` results, extracts the leading directory
/// component, and dedupes. Errors are swallowed (returns Vec::new()) — vendor
/// reduction is an optimisation, not a correctness requirement.
async fn derive_vendor_paths_from_codegraph(client: &CodeGraphClient) -> Vec<String> {
    let mut out: BTreeMap<String, ()> = BTreeMap::new();
    for hint in ["vendor", "third_party", "node_modules"] {
        let Ok(matches) = client.search_symbol(hint).await else {
            continue;
        };
        for m in matches {
            // m.file may look like `vendor/lib/foo.go` — extract the leading
            // segment when it matches one of the known vendor roots.
            if let Some(top) = m.file.split('/').next() {
                if matches!(top, "vendor" | "third_party" | "node_modules") {
                    out.insert(format!("{top}/"), ());
                }
            }
        }
    }
    out.into_keys().collect()
}

/// Persist the `codegraph_unavailable: true` flag (plus the reason) into the
/// static task record's `extra` field so the frontend can render the degraded
/// badge without a schema migration.
async fn set_codegraph_unavailable_flag(state: &AppState, task_id: &str, reason: &str) {
    let Ok(mut snapshot) = task_state::load_snapshot(state).await else {
        return;
    };
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        // record.extra is free-form Value — merge in the flag.
        if !record.extra.is_object() {
            record.extra = json!({});
        }
        if let Value::Object(map) = &mut record.extra {
            map.insert("codegraph_unavailable".to_string(), json!(true));
            map.insert("codegraph_unavailable_reason".to_string(), json!(reason));
        }
    }
    let _ = task_state::save_snapshot(state, &snapshot).await;
}

/// Stamp the codegraph handoff onto the build plan's `evidence_json` so the
/// downstream build-plan record + the frontend get a stable structural view.
fn attach_codegraph_handoff_to_plan(
    plan: &mut crate::scan::codeql::CompileSandboxPlan,
    handoff: &CodegraphHandoff,
) {
    if !plan.evidence_json.is_object() {
        plan.evidence_json = json!({});
    }
    if let Value::Object(map) = &mut plan.evidence_json {
        map.insert("codegraph_handoff".to_string(), handoff.to_evidence_json());
    }
}

async fn extract_archive_to_dir(
    archive_path: &std::path::Path,
    original_filename: &str,
    target_dir: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let archive = archive_path.to_path_buf();
    let target = target_dir.to_path_buf();
    let filename = original_filename.to_string();
    tokio::task::spawn_blocking(move || {
        crate::archive::extract_archive_path_to_directory(&archive, &filename, &target)
    })
    .await??;
    Ok(())
}

async fn flatten_single_top_level_dir(
    dir: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut entries = tokio::fs::read_dir(dir).await?;
    let mut first_entry: Option<PathBuf> = None;
    let mut count = 0usize;
    while let Some(entry) = entries.next_entry().await? {
        count += 1;
        if count == 1 {
            first_entry = Some(entry.path());
        }
        if count > 1 {
            return Ok(());
        }
    }
    let Some(single) = first_entry else {
        return Ok(());
    };
    if !tokio::fs::metadata(&single).await?.is_dir() {
        return Ok(());
    }
    let tmp_name = dir.join(format!(".flatten-tmp-{}", uuid::Uuid::new_v4()));
    tokio::fs::rename(&single, &tmp_name).await?;
    let mut inner = tokio::fs::read_dir(&tmp_name).await?;
    while let Some(child) = inner.next_entry().await? {
        tokio::fs::rename(child.path(), dir.join(child.file_name())).await?;
    }
    tokio::fs::remove_dir(&tmp_name).await?;
    Ok(())
}

/// Build the LLM prompt for compile exploration inference.
fn build_inference_prompt(
    round: u32,
    language: &str,
    workspace_listing: &str,
    prior_output: Option<&str>,
    error_feedback: Option<&str>,
) -> String {
    let mut prompt = format!(
        "You are a build system expert. Analyze the following workspace and produce a JSON compile plan for CodeQL static analysis.\n\
         Language: {language}\n\
         Workspace files:\n{workspace_listing}\n\n\
         Respond with ONLY a JSON object in this exact format:\n\
         {{\"language\":\"{language}\",\"commands\":[\"<cmd1>\",\"<cmd2>\"],\"build_mode\":\"manual\",\
         \"working_directory\":\"/scan/workspace\",\"target_path\":\"/scan/workspace\",\
         \"allow_network\":false,\"query_suite\":null}}\n\
         If no build is needed (e.g. interpreted language), use build_mode \"none\" and empty commands array.\n"
    );
    if let Some(output) = prior_output {
        prompt.push_str(&format!(
            "\nRound {round} — previous command output:\n{output}\n"
        ));
    }
    if let Some(err) = error_feedback {
        prompt.push_str(&format!(
            "\nThe previous attempt failed with:\n{err}\nPlease adjust the build commands.\n"
        ));
    }
    prompt
}

async fn run_codeql_compile_exploration(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    source_dir: &std::path::Path,
    language: &str,
    image: &str,
    memory_mb: u64,
    max_rounds: u64,
    allow_network: bool,
) -> Result<crate::scan::codeql::CompileSandboxPlan, Box<dyn std::error::Error + Send + Sync>> {
    use crate::runtime::{
        codeql_container,
        intelligent::{
            config::resolve_intelligent_llm_config,
            llm::{HttpIntelligentLlmInvoker, IntelligentLlmInvoker},
        },
    };

    // Resolve LLM config before starting the container — fail fast if unconfigured.
    let llm_config = match system_config::load_current(state).await {
        Ok(Some(cfg)) => match resolve_intelligent_llm_config(&cfg, &state.config) {
            Ok(c) => Some(c),
            Err(e) => {
                tracing::warn!(
                    target: "argus::codeql",
                    task_id = %task_id,
                    error = %e,
                    "LLM not configured for compile exploration, falling back to autobuild"
                );
                None
            }
        },
        Ok(None) => {
            tracing::warn!(
                target: "argus::codeql",
                task_id = %task_id,
                "no system config for compile exploration, falling back to autobuild"
            );
            None
        }
        Err(e) => {
            tracing::warn!(
                target: "argus::codeql",
                task_id = %task_id,
                error = %e,
                "failed to load system config for compile exploration, falling back to autobuild"
            );
            None
        }
    };

    // Start the exploration container — guard lives for the entire loop.
    let guard = tokio::task::spawn_blocking({
        let task_id = task_id.to_string();
        let image = image.to_string();
        let source_dir = source_dir.to_path_buf();
        move || {
            codeql_container::start_exploration_container(&task_id, &image, &source_dir, memory_mb)
        }
    })
    .await??;

    let container_name = guard.container_name().to_string();

    // Probe workspace for build files (limit to 4KB).
    let workspace_listing = {
        let cn = container_name.clone();
        let raw = tokio::task::spawn_blocking(move || {
            codeql_container::exec_in_container(
                &cn,
                "find /scan/workspace -maxdepth 3 -name 'Makefile' -o -name 'CMakeLists.txt' \
                 -o -name 'pom.xml' -o -name 'build.gradle' -o -name 'package.json' \
                 -o -name 'setup.py' 2>/dev/null; echo '---'; ls /scan/workspace",
                30,
                None,
            )
        })
        .await??;
        tracing::info!(
            target: "argus::codeql",
            task_id = %task_id,
            exit_code = raw.exit_code,
            "compile exploration workspace probe completed"
        );
        push_exploration_event(
            state,
            task_id,
            "compile_sandbox",
            "compile_sandbox",
            20.0,
            None,
            json!({
                "message": "workspace probe completed",
                "stdout": text_excerpt_chars(&raw.stdout, 2048),
                "exit_code": raw.exit_code,
            }),
        )
        .await;
        text_excerpt_chars(&raw.stdout, 4096)
    };

    // If LLM is not configured, skip inference and return autobuild fallback immediately.
    let Some(llm_config) = llm_config else {
        let plan = crate::scan::codeql::CompileSandboxPlan {
            language: language.to_string(),
            target_path: source_dir.display().to_string(),
            build_mode: "none".to_string(),
            commands: vec![],
            working_directory: "/scan/workspace".to_string(),
            allow_network,
            query_suite: None,
            source_fingerprint: String::new(),
            dependency_fingerprint: String::new(),
            status: "accepted".to_string(),
            evidence_json: serde_json::json!({"source": "exploration_no_llm"}),
            language_fallback_used: false,
        };
        drop(guard);
        return Ok(plan);
    };

    let invoker = HttpIntelligentLlmInvoker::default();
    let mut prompt = build_inference_prompt(0, language, &workspace_listing, None, None);
    let mut last_exec_output: Option<String> = None;
    let mut final_plan: Option<crate::scan::codeql::CompileSandboxPlan> = None;

    for round in 0..max_rounds {
        tracing::info!(
            target: "argus::codeql",
            task_id = %task_id,
            round = round,
            "compile exploration LLM round starting"
        );
        push_exploration_event(
            state,
            task_id,
            "llm_round_started",
            "compile_sandbox",
            20.0,
            Some(round as i64),
            json!({"message": format!("LLM round {} starting", round)}),
        )
        .await;

        // Call LLM.
        let invocation = match invoker.invoke(&prompt, &llm_config).await {
            Ok(inv) => inv,
            Err(e) => {
                tracing::warn!(
                    target: "argus::codeql",
                    task_id = %task_id,
                    round = round,
                    error = %e,
                    "LLM invocation failed, aborting exploration"
                );
                break;
            }
        };

        let response_text = invocation.content.trim().to_string();

        // Parse the plan from LLM response.
        let parsed = crate::scan::codeql::parse_compile_sandbox_plan(&response_text);
        let plan = match parsed {
            Ok(p) => p,
            Err(e) => {
                tracing::warn!(
                    target: "argus::codeql",
                    task_id = %task_id,
                    round = round,
                    error = %e,
                    "failed to parse LLM compile plan, feeding error back"
                );
                prompt = build_inference_prompt(
                    round as u32 + 1,
                    language,
                    &workspace_listing,
                    last_exec_output.as_deref(),
                    Some(&format!("JSON parse error: {e}")),
                );
                continue;
            }
        };

        // If plan has no commands, accept it directly (autobuild / none mode).
        if plan.commands.is_empty() {
            tracing::info!(
                target: "argus::codeql",
                task_id = %task_id,
                round = round,
                build_mode = %plan.build_mode,
                "LLM returned no-command plan, accepting"
            );
            final_plan = Some(plan);
            break;
        }

        // Execute all commands joined by && to verify the full build sequence.
        let full_cmd = plan.commands.join(" && ");
        let full_cmd_display = full_cmd.clone();
        let cn = container_name.clone();
        let exec_result = tokio::task::spawn_blocking(move || {
            codeql_container::exec_in_container(&cn, &full_cmd, 300, Some(2048))
        })
        .await??;

        let exec_summary = format!(
            "exit_code={}\nstdout:\n{}\nstderr:\n{}",
            exec_result.exit_code,
            text_excerpt_chars(&exec_result.stdout, 1024),
            text_excerpt_chars(&exec_result.stderr, 1024),
        );
        last_exec_output = Some(exec_summary.clone());

        tracing::info!(
            target: "argus::codeql",
            task_id = %task_id,
            round = round,
            exit_code = exec_result.exit_code,
            "compile exploration command verification"
        );
        push_exploration_event(
            state,
            task_id,
            "sandbox_command_completed",
            "compile_sandbox",
            20.0,
            Some(round as i64),
            json!({
                "command": full_cmd_display,
                "stdout": text_excerpt_chars(&exec_result.stdout, 2048),
                "stderr": text_excerpt_chars(&exec_result.stderr, 2048),
                "exit_code": exec_result.exit_code,
            }),
        )
        .await;

        if exec_result.exit_code != 0 {
            // Full sequence failed — also run just the first command to accumulate
            // container state (e.g., chmod fixes) for subsequent rounds.
            if plan.commands.len() > 1 {
                let first_cmd = plan.commands[0].clone();
                let cn2 = container_name.clone();
                let _ = tokio::task::spawn_blocking(move || {
                    codeql_container::exec_in_container(&cn2, &first_cmd, 60, None)
                })
                .await;
            }
            prompt = build_inference_prompt(
                round as u32 + 1,
                language,
                &workspace_listing,
                Some(&exec_summary),
                Some("The command exited with a non-zero exit code."),
            );
            continue;
        }

        // Exit code is 0 but check for stderr errors or stdout error patterns.
        // A build plan is only acceptable if there are no compilation errors.
        let stderr_trimmed = exec_result.stderr.trim();
        let stdout_lower = exec_result.stdout.to_lowercase();
        let has_stderr_errors = !stderr_trimmed.is_empty()
            && (stderr_trimmed.contains("error:")
                || stderr_trimmed.contains("Error:")
                || stderr_trimmed.contains("ERROR")
                || stderr_trimmed.contains("fatal:")
                || stderr_trimmed.contains("FAILED")
                || stderr_trimmed.contains("BUILD FAILURE")
                || stderr_trimmed.contains("compilation failed")
                || stderr_trimmed.contains("cannot find symbol"));
        let has_stdout_errors = stdout_lower.contains("build failure")
            || stdout_lower.contains("compilation error")
            || stdout_lower.contains("fatal error")
            || stdout_lower.contains("[error]");

        if has_stderr_errors || has_stdout_errors {
            let hint = if has_stderr_errors {
                "The command exited with code 0 but stderr contains error messages. The build is not clean — fix the errors."
            } else {
                "The command exited with code 0 but stdout contains error messages. The build is not clean — fix the errors."
            };
            prompt = build_inference_prompt(
                round as u32 + 1,
                language,
                &workspace_listing,
                Some(&exec_summary),
                Some(hint),
            );
            continue;
        }

        // Full build sequence succeeded — accept the plan.
        // The successful execution of the complete command chain is sufficient
        // proof that CodeQL can trace the compilation.
        final_plan = Some(plan);
        break;
    }

    // Use inferred plan or fall back to autobuild.
    let plan = final_plan.unwrap_or_else(|| {
        tracing::info!(
            target: "argus::codeql",
            task_id = %task_id,
            "compile exploration exhausted rounds, falling back to autobuild"
        );
        crate::scan::codeql::CompileSandboxPlan {
            language: language.to_string(),
            target_path: source_dir.display().to_string(),
            build_mode: "none".to_string(),
            commands: vec![],
            working_directory: "/scan/workspace".to_string(),
            allow_network,
            query_suite: None,
            source_fingerprint: String::new(),
            dependency_fingerprint: String::new(),
            status: "accepted".to_string(),
            evidence_json: serde_json::json!({"source": "exploration_fallback"}),
            language_fallback_used: false,
        }
    });

    push_exploration_event(
        state,
        task_id,
        "build_plan_accepted",
        "build_plan_accepted",
        50.0,
        None,
        json!({
            "message": format!("build plan accepted: mode={}", plan.build_mode),
            "commands": plan.commands,
        }),
    )
    .await;

    let now = now_rfc3339();
    let record = crate::scan::codeql::build_plan_record_from_compile_plan(
        uuid::Uuid::new_v4().to_string(),
        project_id.to_string(),
        &plan,
        now,
    );
    crate::db::codeql_build_plans::upsert_accepted_build_plan(state, &record).await?;

    drop(guard);
    Ok(plan)
}

fn generate_codeql_entrypoint_script(
    plan: &crate::scan::codeql::CompileSandboxPlan,
    language: &str,
    ram_mb: u64,
    threads: usize,
) -> String {
    let mut script = String::from("#!/bin/sh\ncd /scan/workspace/source\n\n");

    let build_command = if plan.commands.is_empty() {
        String::new()
    } else {
        script.push_str("cat > /scan/workspace/source/.codeql-build.sh << 'BUILDEOF'\n");
        script.push_str(
            "#!/bin/sh\nset -e\ncd /scan/workspace/source\nmake clean 2>/dev/null || true\n",
        );
        for cmd in &plan.commands {
            script.push_str(cmd);
            script.push('\n');
        }
        script.push_str("BUILDEOF\n");
        script.push_str("chmod +x /scan/workspace/source/.codeql-build.sh\n\n");
        " --command=/scan/workspace/source/.codeql-build.sh".to_string()
    };

    let threads_arg = if threads > 0 {
        format!(" --threads={threads}")
    } else {
        String::new()
    };

    script.push_str(&format!(
        "codeql database create /scan/codeql-db --language={language}{build_command} --ram={ram_mb}{threads_arg} --overwrite || CREATE_RC=$?\n"
    ));
    script.push_str("CREATE_RC=${CREATE_RC:-0}\n");
    script.push_str("if [ \"$CREATE_RC\" -eq 2 ]; then\n");
    script.push_str("  echo 'codeql database create exited with code 2 (extraction issues), continuing with analysis'\n");
    script.push_str("elif [ \"$CREATE_RC\" -ne 0 ]; then\n");
    script.push_str("  exit $CREATE_RC\n");
    script.push_str("fi\n\n");

    let query_suite = plan
        .query_suite
        .as_deref()
        .unwrap_or(&format!("{language}-security-and-quality.qls"))
        .to_string();
    script.push_str("mkdir -p /scan/workspace/output\n\n");
    script.push_str(&format!(
        "codeql database analyze /scan/codeql-db --format=sarif-latest --output=/scan/workspace/output/results.sarif --ram={ram_mb}{threads_arg} {query_suite} || ANALYZE_RC=$?\n"
    ));
    script.push_str("ANALYZE_RC=${ANALYZE_RC:-0}\n");
    script.push_str("if [ \"$ANALYZE_RC\" -eq 2 ]; then\n");
    script.push_str("  echo 'codeql analyze exited with code 2 (some queries failed), treating as partial success'\n");
    script.push_str("elif [ \"$ANALYZE_RC\" -ne 0 ]; then\n");
    script.push_str("  exit $ANALYZE_RC\n");
    script.push_str("fi\n");

    script
}

fn build_joern_runner_spec(
    config: &crate::config::AppConfig,
    workspace_dir: &std::path::Path,
    source_dir: &std::path::Path,
    query_dir: &std::path::Path,
    output_dir: &std::path::Path,
) -> RunnerSpec {
    let mut env = BTreeMap::new();
    env.insert("JOERN_SOURCE_DIR".to_string(), "/scan/source".to_string());
    env.insert("JOERN_OUTPUT_DIR".to_string(), "/scan/output".to_string());
    env.insert(
        "JOERN_QUERY_DIR".to_string(),
        "/scan/joern-queries".to_string(),
    );

    RunnerSpec {
        scanner_type: "joern".to_string(),
        image: config.scanner_joern_image.clone(),
        container_runtime: ContainerRuntime::Podman,
        workspace_dir: workspace_dir.display().to_string(),
        command: vec![
            "/bin/sh".to_string(),
            "/scan/workspace/argus-joern-wrapper.sh".to_string(),
        ],
        timeout_seconds: config.joern_scan_timeout_seconds,
        env,
        expected_exit_codes: vec![0],
        artifact_paths: Vec::new(),
        capture_stdout_path: Some(joern::STDOUT_REL_PATH.to_string()),
        capture_stderr_path: Some(joern::STDERR_REL_PATH.to_string()),
        stdout_limit_bytes: Some(config.joern_stdout_limit_bytes),
        stderr_limit_bytes: Some(config.joern_stderr_limit_bytes),
        completion_summary_path: Some(joern::SUMMARY_REL_PATH.to_string()),
        workspace_root_override: None,
        memory_limit_mb: Some(config.joern_runner_memory_limit_mb),
        memory_swap_limit_mb: Some(config.joern_runner_memory_limit_mb),
        cpu_limit: (config.joern_runner_cpu_limit > 0.0).then_some(config.joern_runner_cpu_limit),
        pids_limit: Some(config.joern_runner_pids_limit),
        network_disabled: config.joern_network_disabled,
        mount_plan: Some(RunnerMountPlan::new(vec![
            RunnerMount::read_write(workspace_dir.display().to_string(), "/scan/workspace"),
            RunnerMount::read_only(source_dir.display().to_string(), "/scan/source"),
            RunnerMount::read_only(query_dir.display().to_string(), "/scan/joern-queries"),
            RunnerMount::read_write(output_dir.display().to_string(), "/scan/output"),
        ])),
    }
}

async fn store_joern_results(
    state: &AppState,
    task_id: &str,
    findings: &[task_state::StaticFindingRecord],
    summary: Value,
    graph_proof: Value,
    files_scanned: usize,
    elapsed_ms: i64,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let now = now_rfc3339();
    let error_count = findings
        .iter()
        .filter(|finding| {
            finding
                .payload
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|severity| severity.eq_ignore_ascii_case("ERROR"))
        })
        .count();
    let warning_count = findings
        .iter()
        .filter(|finding| {
            finding
                .payload
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|severity| severity.eq_ignore_ascii_case("WARNING"))
        })
        .count();
    let high_confidence_count = findings
        .iter()
        .filter(|finding| {
            finding
                .payload
                .get("confidence")
                .and_then(Value::as_str)
                .is_some_and(|confidence| confidence.eq_ignore_ascii_case("HIGH"))
        })
        .count();

    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record.status = "completed".to_string();
        record.total_findings = findings.len() as i64;
        record.scan_duration_ms = elapsed_ms;
        record.files_scanned = files_scanned as i64;
        record.error_message = None;
        record.updated_at = Some(now.clone());
        record.extra = json!({
            "engine": "joern",
            "executor": "runner_spec_podman",
            "error_count": error_count,
            "warning_count": warning_count,
            "high_confidence_count": high_confidence_count,
            "lines_scanned": 0,
            "files_scanned": files_scanned,
            "joern_summary": summary,
            "joern_graph_proof": graph_proof,
            "joern_docs_evidence": joern::docs_evidence(),
        });
        record.findings = findings.to_vec();
        let events = record.progress.events.clone();
        record.progress = task_state::StaticTaskProgressRecord {
            progress: 100.0,
            current_stage: Some("completed".to_string()),
            message: Some(format!(
                "joern scan completed: {} findings in {}ms",
                findings.len(),
                elapsed_ms
            )),
            started_at: record.progress.started_at.clone(),
            updated_at: Some(now.clone()),
            logs: {
                let mut logs = record.progress.logs.clone();
                logs.push(task_state::StaticTaskProgressLogRecord {
                    timestamp: now,
                    stage: "completed".to_string(),
                    message: format!(
                        "joern scan completed: {} findings, {} files scanned",
                        findings.len(),
                        files_scanned
                    ),
                    progress: 100.0,
                    level: "info".to_string(),
                });
                logs
            },
            events,
        };
    }
    task_state::save_snapshot(state, &snapshot).await?;
    Ok(())
}

fn build_codeql_runner_spec(
    config: &crate::config::AppConfig,
    workspace_dir: &std::path::Path,
    options: &CodeqlTaskOptions,
) -> RunnerSpec {
    let allow_network = options
        .allow_network
        .unwrap_or(config.codeql_allow_network_during_build);
    RunnerSpec {
        scanner_type: "codeql".to_string(),
        image: config.scanner_codeql_image.clone(),
        container_runtime: ContainerRuntime::Podman,
        workspace_dir: workspace_dir.display().to_string(),
        command: vec![
            "/bin/sh".to_string(),
            "/scan/workspace/.codeql-entrypoint.sh".to_string(),
        ],
        timeout_seconds: 1800,
        env: BTreeMap::new(),
        expected_exit_codes: vec![0],
        artifact_paths: Vec::new(),
        capture_stdout_path: Some("output/stdout.log".to_string()),
        capture_stderr_path: Some("output/stderr.log".to_string()),
        stdout_limit_bytes: None,
        stderr_limit_bytes: None,
        completion_summary_path: None,
        workspace_root_override: None,
        memory_limit_mb: Some(config.codeql_ram_mb),
        memory_swap_limit_mb: None,
        cpu_limit: None,
        pids_limit: Some(512),
        network_disabled: !allow_network,
        mount_plan: Some(RunnerMountPlan::new(vec![RunnerMount::read_write(
            workspace_dir.display().to_string(),
            "/scan/workspace".to_string(),
        )])),
    }
}

async fn update_scan_task_completed(
    state: &AppState,
    task_id: &str,
    findings_count: usize,
    elapsed_ms: i64,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let now = now_rfc3339();
    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record.status = "completed".to_string();
        record.total_findings = findings_count as i64;
        record.scan_duration_ms = elapsed_ms;
        record.updated_at = Some(now.clone());
        record.progress.progress = 100.0;
        record.progress.current_stage = Some("completed".to_string());
        record.progress.message = Some(format!(
            "codeql scan completed: {findings_count} findings in {elapsed_ms}ms"
        ));
        record.progress.updated_at = Some(now.clone());
        record
            .progress
            .logs
            .push(task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: "completed".to_string(),
                message: format!("scan completed: {findings_count} findings"),
                progress: 100.0,
                level: "info".to_string(),
            });
    }
    task_state::save_snapshot(state, &snapshot).await?;
    Ok(())
}

async fn store_codeql_findings(
    state: &AppState,
    task_id: &str,
    _project_id: &str,
    findings: &[task_state::StaticFindingRecord],
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record.findings = findings.to_vec();
    }
    task_state::save_snapshot(state, &snapshot).await?;
    Ok(())
}

async fn reset_codeql_build_plan_for_project(
    state: &AppState,
    project_id: &str,
    language: &str,
) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
    let db_reset =
        codeql_build_plans::reset_active_project_build_plan(state, project_id, language).await?;
    let mut snapshot = task_state::load_snapshot(state).await?;
    let now = now_rfc3339();
    let mut file_reset = 0usize;
    for record in snapshot.codeql_build_plans.values_mut() {
        if record.project_id == project_id
            && record.language == language
            && record.status == "accepted"
        {
            record.status = "reset".to_string();
            record.updated_at = Some(now.clone());
            file_reset += 1;
        }
    }
    if file_reset > 0 {
        task_state::save_snapshot(state, &snapshot).await?;
    }
    Ok(file_reset.max(db_reset as usize))
}

fn is_supported_codeql_language(language: &str) -> bool {
    matches!(
        language,
        "cpp" | "javascript-typescript" | "python" | "java" | "go"
    )
}

/// Pure: returns parsed threshold for the given env-var value, or 0.5 on
/// missing/invalid. Emits a `warn!` log on invalid (non-empty, non-parseable
/// or out-of-range) input. Empty/None is the normal "unset" case — no log.
fn cpp_project_threshold_from(env: Option<&str>) -> f64 {
    let Some(raw) = env else { return 0.5; };
    let s = raw.trim();
    if s.is_empty() {
        return 0.5;
    }
    match s.parse::<f64>() {
        Ok(v) if (0.0..=1.0).contains(&v) => v,
        _ => {
            tracing::warn!(threshold = %raw, "ARGUS_CPP_PROJECT_THRESHOLD invalid; falling back to 0.5");
            0.5
        }
    }
}

fn cpp_project_threshold() -> f64 {
    cpp_project_threshold_from(std::env::var("ARGUS_CPP_PROJECT_THRESHOLD").ok().as_deref())
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ProjectGateFailure {
    LanguageDetectionPending,
    NotCppProject,
}

impl ProjectGateFailure {
    fn error_code(&self) -> &'static str {
        "engine_not_supported_for_project_language"
    }

    fn sub_reason(&self) -> &'static str {
        match self {
            Self::LanguageDetectionPending => "language_detection_pending",
            Self::NotCppProject => "not_cpp_project",
        }
    }

    fn user_message(&self) -> &'static str {
        match self {
            Self::LanguageDetectionPending => "项目语言检测未完成，完成后才可使用",
            Self::NotCppProject => "当前功能仅支持 C/C++ 项目",
        }
    }
}

fn is_cpp_project(project: &crate::state::StoredProject) -> Result<(), ProjectGateFailure> {
    if project.info_status != "completed" {
        return Err(ProjectGateFailure::LanguageDetectionPending);
    }
    let langs_ok = serde_json::from_str::<Vec<String>>(&project.programming_languages_json)
        .map(|v| !v.is_empty())
        .unwrap_or(false);
    if !langs_ok {
        return Err(ProjectGateFailure::LanguageDetectionPending);
    }
    let info: serde_json::Value = match serde_json::from_str(&project.language_info) {
        Ok(v) => v,
        Err(_) => return Err(ProjectGateFailure::LanguageDetectionPending),
    };
    let Some(languages) = info.get("languages").and_then(|v| v.as_object()) else {
        return Err(ProjectGateFailure::LanguageDetectionPending);
    };
    if languages.is_empty() {
        return Err(ProjectGateFailure::LanguageDetectionPending);
    }
    let prop = |key: &str| -> f64 {
        languages
            .get(key)
            .and_then(|v| v.get("proportion"))
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0)
    };
    let sum = prop("C") + prop("C++");
    if sum >= cpp_project_threshold() {
        Ok(())
    } else {
        Err(ProjectGateFailure::NotCppProject)
    }
}

fn extract_codeql_task_options(payload: &Value) -> CodeqlTaskOptions {
    let languages = payload
        .get("languages")
        .and_then(string_array)
        .unwrap_or_default()
        .into_iter()
        .map(|language| codeql::normalize_language(&language))
        .filter(|language| is_supported_codeql_language(language))
        .collect::<Vec<_>>();
    let build_mode = optional_string(payload, "build_mode")
        .map(|mode| mode.to_ascii_lowercase())
        .filter(|mode| matches!(mode.as_str(), "none" | "autobuild" | "manual"));
    CodeqlTaskOptions {
        languages,
        build_mode,
        allow_network: optional_bool(payload, "allow_network"),
        reset_build_plan: optional_bool(payload, "reset_build_plan").unwrap_or(false),
    }
}

fn extract_opengrep_task_options(payload: &Value) -> OpengrepTaskOptions {
    let sandbox = optional_string(payload, "opengrep_sandbox")
        .or_else(|| optional_string(payload, "sandbox"))
        .or_else(|| optional_string(payload, "sandbox_mode"));
    OpengrepTaskOptions {
        sandbox: OpengrepSandboxKind::from_value(sandbox.as_deref()),
    }
}

async fn run_opengrep_scan_inner(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    rule_ids: &[String],
    options: OpengrepTaskOptions,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let started_at = std::time::Instant::now();

    update_scan_progress(state, task_id, 5.0, "preparing", "locating project archive").await;

    let (archive_path, archive_name) = resolve_project_archive_input(state, project_id).await?;

    let workspace_root = scan_workspace_root();
    let workspace_dir = workspace_root
        .join("opengrep-runtime")
        .join(Uuid::new_v4().to_string());
    let source_dir = workspace_dir.join("source");
    let output_dir = workspace_dir.join("output");
    tokio::fs::create_dir_all(&source_dir).await?;
    tokio::fs::create_dir_all(&output_dir).await?;

    update_scan_progress(
        state,
        task_id,
        15.0,
        "extracting",
        "extracting project archive",
    )
    .await;

    let source_dir_clone = source_dir.clone();
    let archive_path_clone = archive_path.clone();
    let archive_name_clone = archive_name.clone();
    let files_extracted = tokio::task::spawn_blocking(
        move || -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
            extract_archive_path_to_directory(
                &archive_path_clone,
                &archive_name_clone,
                &source_dir_clone,
            )
            .map_err(|error| error.into())
        },
    )
    .await??;

    let source_dir_for_prune = source_dir.clone();
    let files_excluded = tokio::task::spawn_blocking(
        move || -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
            prune_static_scan_non_source_paths(&source_dir_for_prune)
        },
    )
    .await??;
    let scan_input_paths = collect_relative_paths_from_directory(&source_dir)?;
    let files_scanned = scan_input_paths.len();
    if files_excluded > 0 {
        update_scan_progress(
            state,
            task_id,
            25.0,
            "filtering",
            &format!("excluded {files_excluded} non-source files from opengrep scan input"),
        )
        .await;
    }

    update_scan_progress(
        state,
        task_id,
        30.0,
        "preparing_rules",
        "preparing opengrep rule directory",
    )
    .await;

    let project_languages = match projects::get_project(state, project_id).await {
        Ok(Some(project)) => {
            serde_json::from_str::<Vec<String>>(&project.programming_languages_json)
                .unwrap_or_default()
        }
        _ => Vec::new(),
    };

    let Some(rule_inputs) =
        prepare_opengrep_runner_inputs(state, &workspace_dir, rule_ids, &project_languages).await?
    else {
        return Err("no opengrep rules available for scan".into());
    };

    update_scan_progress(
        state,
        task_id,
        40.0,
        "queued",
        "waiting for opengrep CPU resources",
    )
    .await;

    let requested_cores = requested_opengrep_cpu_cores(&state.config);
    let scheduler = OPENGREP_RESOURCE_SCHEDULER.clone();
    let project_slot_id = project_id.to_string();
    let resource_permit = tokio::task::spawn_blocking(move || {
        scheduler.acquire_for_project(&project_slot_id, requested_cores)
    })
    .await
    .map_err(|error| format!("opengrep resource scheduler failed: {error}"))?;
    let runner_resources = resolve_opengrep_runner_resources(&state.config, &resource_permit);

    update_scan_progress(
        state,
        task_id,
        40.0,
        "scanning",
        &format!(
            "running opengrep scanner with {} jobs on {} CPU cores ({} cores available)",
            runner_resources.jobs, runner_resources.allocated_cores, runner_resources.total_cores
        ),
    )
    .await;

    let known_paths = scan_input_paths;
    let output_rel_path = format!("output/results-{}.json", Uuid::new_v4());
    let summary_rel_path = format!("output/summary-{}.json", Uuid::new_v4());
    let log_rel_path = format!("output/log-{}.txt", Uuid::new_v4());
    let stdout_rel_path = format!("output/stdout-{}.txt", Uuid::new_v4());
    let stderr_rel_path = format!("output/stderr-{}.txt", Uuid::new_v4());
    let sandbox_label = options.sandbox.as_str();
    let mut effective_executor_label = match sandbox_label {
        "a3s_box" => "a3s_box".to_string(),
        _ => "docker_runner".to_string(),
    };
    match options.sandbox {
        OpengrepSandboxKind::DockerfileContainer => {
            validate_opengrep_runner_deployment_config(&state.config)?;
            let scanner_image = state.config.scanner_opengrep_image.clone();
            let container_source_dir = "/scan/source";
            let config_container_path = rule_inputs
                .workspace_rules_dir
                .as_ref()
                .map(|path| workspace_container_path(&workspace_dir, path))
                .transpose()?;
            let output_container_path = format!("/scan/{output_rel_path}");
            let summary_container_path = format!("/scan/{summary_rel_path}");
            let log_container_path = format!("/scan/{log_rel_path}");
            let spec = build_opengrep_runner_spec(
                &state.config,
                scanner_image,
                &workspace_dir,
                runner_resources,
                OpengrepRunnerPaths {
                    container_source_dir,
                    manifest_container_path: None,
                    config_container_path: config_container_path.as_deref(),
                    output_container_path: &output_container_path,
                    summary_rel_path: &summary_rel_path,
                    summary_container_path: &summary_container_path,
                    log_container_path: &log_container_path,
                    stdout_rel_path: &stdout_rel_path,
                    stderr_rel_path: &stderr_rel_path,
                },
            );

            let runner_result = tokio::task::spawn_blocking(move || runner::execute(spec)).await?;
            drop(resource_permit);
            if !runner_result.success {
                let error_msg = format_opengrep_runner_error(
                    &runner_result,
                    Some(&workspace_dir.join(&log_rel_path)),
                )
                .await;
                let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
                return Err(format!("opengrep scan failed: {error_msg}").into());
            }
        }

        OpengrepSandboxKind::A3sBox => {
            validate_opengrep_runner_deployment_config(&state.config)?;
            let scanner_image = state.config.scanner_opengrep_a3s_box_image.clone();
            let container_source_dir = "/scan/source";
            let config_container_path = rule_inputs
                .workspace_rules_dir
                .as_ref()
                .map(|path| workspace_container_path(&workspace_dir, path))
                .transpose()?;
            let output_container_path = format!("/scan/{output_rel_path}");
            let summary_container_path = format!("/scan/{summary_rel_path}");
            let log_container_path = format!("/scan/{log_rel_path}");
            let a3s_spec = build_opengrep_a3s_box_runner_spec(
                &state.config,
                scanner_image.clone(),
                &workspace_dir,
                runner_resources,
                Some(task_id),
                OpengrepRunnerPaths {
                    container_source_dir,
                    manifest_container_path: None,
                    config_container_path: config_container_path.as_deref(),
                    output_container_path: &output_container_path,
                    summary_rel_path: &summary_rel_path,
                    summary_container_path: &summary_container_path,
                    log_container_path: &log_container_path,
                    stdout_rel_path: &stdout_rel_path,
                    stderr_rel_path: &stderr_rel_path,
                },
            );
            let fallback_workspace_dir = workspace_dir.clone();
            let fallback_config = state.config.clone();
            let fallback_config_container_path_str =
                config_container_path.as_deref().map(str::to_string);
            let fallback_output_container_path = output_container_path.clone();
            let fallback_summary_container_path = summary_container_path.clone();
            let fallback_log_container_path = log_container_path.clone();
            let fallback_stdout_rel_path = stdout_rel_path.clone();
            let fallback_stderr_rel_path = stderr_rel_path.clone();
            let fallback_summary_rel_path = summary_rel_path.clone();
            let fallback_spec_builder = move || {
                build_opengrep_podman_fallback_runner_spec(
                    &fallback_config,
                    scanner_image,
                    &fallback_workspace_dir,
                    runner_resources,
                    OpengrepRunnerPaths {
                        container_source_dir,
                        manifest_container_path: None,
                        config_container_path: fallback_config_container_path_str.as_deref(),
                        output_container_path: &fallback_output_container_path,
                        summary_rel_path: &fallback_summary_rel_path,
                        summary_container_path: &fallback_summary_container_path,
                        log_container_path: &fallback_log_container_path,
                        stdout_rel_path: &fallback_stdout_rel_path,
                        stderr_rel_path: &fallback_stderr_rel_path,
                    },
                )
            };
            let a3s_executor = crate::scan::opengrep_a3s::DefaultA3sBoxExecutor;
            let fallback_executor = crate::scan::opengrep_a3s::DefaultFallbackRunnerExecutor;
            let outcome = crate::scan::opengrep_a3s::scan_with_fallback(
                &a3s_executor,
                &fallback_executor,
                a3s_spec,
                fallback_spec_builder,
                task_id,
                Some(project_id),
            )
            .await?;
            drop(resource_permit);
            effective_executor_label = match outcome.runtime_used {
                crate::scan::opengrep_a3s::RuntimeUsed::A3s => "a3s_box".to_string(),
                crate::scan::opengrep_a3s::RuntimeUsed::PodmanFallback => {
                    "a3s_box_fallback_podman".to_string()
                }
            };
            match outcome.output {
                crate::scan::opengrep_a3s::ScanOutput::A3s(ref a3s_result) => {
                    if !a3s_result.success {
                        let error_msg = a3s_result.error.clone().unwrap_or_else(|| {
                            format!("opengrep a3s-box exited with code {}", a3s_result.exit_code)
                        });
                        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
                        return Err(format!("opengrep scan failed: {error_msg}").into());
                    }
                }
                crate::scan::opengrep_a3s::ScanOutput::Fallback(ref runner_result) => {
                    if !runner_result.success {
                        let error_msg = format_opengrep_runner_error(
                            runner_result,
                            Some(&workspace_dir.join(&log_rel_path)),
                        )
                        .await;
                        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
                        return Err(format!("opengrep scan failed: {error_msg}").into());
                    }
                }
            }
        }
    }

    let summary_path = workspace_dir.join(&summary_rel_path);
    if let Ok(summary_text) = tokio::fs::read_to_string(&summary_path).await {
        if summary_text.contains("\"status\":\"scan_failed\"") {
            let reason = serde_json::from_str::<serde_json::Value>(&summary_text)
                .ok()
                .and_then(|v| v.get("reason")?.as_str().map(String::from))
                .filter(|r| !r.is_empty());
            let log_excerpt = read_text_excerpt(Some(&workspace_dir.join(&log_rel_path))).await;
            let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
            let detail = reason
                .or(log_excerpt)
                .unwrap_or_else(|| "no log available".to_string());
            return Err(format!("opengrep scan failed: {detail}").into());
        }
    }

    update_scan_progress(state, task_id, 75.0, "parsing", "parsing scan results").await;

    let results_path = workspace_dir.join(&output_rel_path);
    let json_text = read_opengrep_results_text(
        &results_path,
        state.config.opengrep_results_json_limit_bytes,
    )
    .await
    .map_err(|error| format!("opengrep results unavailable: {error}"))?;
    if !opengrep::scan_output_has_results_array(&json_text) {
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Err("opengrep output missing results array".into());
    }

    let findings =
        opengrep::parse_scan_output(&json_text, task_id, source_dir.to_str(), Some(&known_paths));

    update_scan_progress(state, task_id, 90.0, "finalizing", "saving findings").await;

    let elapsed_ms = started_at.elapsed().as_millis() as i64;
    let error_count = findings
        .iter()
        .filter(|f| {
            f.payload
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|s| s.eq_ignore_ascii_case("ERROR"))
        })
        .count();
    let warning_count = findings
        .iter()
        .filter(|f| {
            f.payload
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|s| s.eq_ignore_ascii_case("WARNING"))
        })
        .count();
    let high_confidence_count = findings
        .iter()
        .filter(|f| {
            f.payload
                .get("confidence")
                .and_then(Value::as_str)
                .is_some_and(|s| s.eq_ignore_ascii_case("HIGH"))
        })
        .count();

    let now = now_rfc3339();
    let mut snapshot = match task_state::load_snapshot(state).await {
        Ok(s) => s,
        Err(_) => {
            let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
            return Err("failed to load task snapshot".into());
        }
    };

    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record.status = "completed".to_string();
        record.total_findings = findings.len() as i64;
        record.scan_duration_ms = elapsed_ms;
        record.files_scanned = files_scanned as i64;
        record.updated_at = Some(now.clone());
        record.extra = json!({
            "engine": "opengrep",
            "opengrep_sandbox": sandbox_label,
            "executor": effective_executor_label,
            "error_count": error_count,
            "warning_count": warning_count,
            "high_confidence_count": high_confidence_count,
            "lines_scanned": 0,
            "files_extracted": files_extracted,
            "files_excluded": files_excluded,
        });
        let events = record.progress.events.clone();
        record.progress = task_state::StaticTaskProgressRecord {
            progress: 100.0,
            current_stage: Some("completed".to_string()),
            message: Some(format!(
                "opengrep scan completed: {} findings in {}ms",
                findings.len(),
                elapsed_ms
            )),
            started_at: record.progress.started_at.clone(),
            updated_at: Some(now.clone()),
            logs: {
                let mut logs = record.progress.logs.clone();
                logs.push(task_state::StaticTaskProgressLogRecord {
                    timestamp: now,
                    stage: "completed".to_string(),
                    message: format!(
                        "scan completed: {} findings, {} files scanned",
                        findings.len(),
                        files_scanned
                    ),
                    progress: 100.0,
                    level: "info".to_string(),
                });
                logs
            },
            events,
        };
        record.findings = findings;
    }

    let _ = task_state::save_snapshot(state, &snapshot).await;
    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
    Ok(())
}

async fn read_opengrep_results_text(
    results_path: &std::path::Path,
    limit_bytes: usize,
) -> Result<String, String> {
    let metadata = tokio::fs::metadata(results_path)
        .await
        .map_err(|e| format!("missing opengrep results output: stat results.json: {e}"))?;
    let file_size = metadata.len();
    if file_size > limit_bytes as u64 {
        return Err(format!(
            "results.json size {file_size} bytes exceeds \
             OPENGREP_RESULTS_JSON_LIMIT_BYTES={limit_bytes}; \
             scan likely produced too many findings or rule output was too verbose. \
             Increase the limit or refine the rule set."
        ));
    }
    let mut file = tokio::fs::File::open(results_path)
        .await
        .map_err(|e| format!("open results.json: {e}"))?;
    use tokio::io::AsyncReadExt;
    // Pre-allocate up to known size to avoid repeated grow.
    let cap = (file_size as usize).min(limit_bytes);
    let mut bytes = Vec::with_capacity(cap.min(64 * 1024));
    (&mut file)
        .take(limit_bytes as u64)
        .read_to_end(&mut bytes)
        .await
        .map_err(|e| format!("read results.json: {e}"))?;
    String::from_utf8(bytes).map_err(|e| format!("results.json is not valid UTF-8: {e}"))
}

fn prune_static_scan_non_source_paths(
    source_dir: &Path,
) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
    let mut stack = vec![source_dir.to_path_buf()];
    let mut files = Vec::new();
    while let Some(path) = stack.pop() {
        for entry in std::fs::read_dir(&path)? {
            let entry = entry?;
            let entry_path = entry.path();
            let file_type = entry.file_type()?;
            if file_type.is_dir() {
                stack.push(entry_path);
            } else if file_type.is_file() {
                files.push(entry_path);
            }
        }
    }

    let mut removed = 0usize;
    for file_path in files {
        let relative = file_path
            .strip_prefix(source_dir)?
            .to_string_lossy()
            .replace('\\', "/");
        if scope_filters::is_static_scan_test_or_fuzz_path(&relative)
            || scope_filters::is_core_ignored_path(&relative, None)
        {
            std::fs::remove_file(&file_path)?;
            removed += 1;
        }
    }

    Ok(removed)
}

struct OpengrepRunnerPaths<'a> {
    container_source_dir: &'a str,
    manifest_container_path: Option<&'a str>,
    config_container_path: Option<&'a str>,
    output_container_path: &'a str,
    summary_rel_path: &'a str,
    summary_container_path: &'a str,
    log_container_path: &'a str,
    stdout_rel_path: &'a str,
    stderr_rel_path: &'a str,
}

fn opengrep_container_runtime(config: &crate::config::AppConfig) -> ContainerRuntime {
    ContainerRuntime::from_config_value(&config.opengrep_runner_runtime)
}

fn build_opengrep_mount_plan(
    workspace_dir: &std::path::Path,
    source_host_dir: &std::path::Path,
    output_host_dir: &std::path::Path,
) -> RunnerMountPlan {
    RunnerMountPlan::new(vec![
        RunnerMount::read_only(
            source_host_dir.display().to_string(),
            format!("{SCANNER_MOUNT_PATH}/source"),
        ),
        RunnerMount::read_write(
            output_host_dir.display().to_string(),
            format!("{SCANNER_MOUNT_PATH}/output"),
        ),
        RunnerMount::read_only(
            workspace_dir.join("opengrep-rules").display().to_string(),
            format!("{SCANNER_MOUNT_PATH}/opengrep-rules"),
        ),
    ])
}

fn build_opengrep_runner_spec(
    config: &crate::config::AppConfig,
    image: String,
    workspace_dir: &std::path::Path,
    resources: OpengrepRunnerResources,
    paths: OpengrepRunnerPaths<'_>,
) -> RunnerSpec {
    let container_runtime = opengrep_container_runtime(config);
    let cpu_limit = match container_runtime {
        // Rootless Podman deployments may not expose the `cpu` cgroup
        // controller. Keep default Podman portable by relying on scheduler
        // permits plus opengrep --jobs; honor an explicit CPU hard-limit opt-in.
        ContainerRuntime::Podman
            if config.opengrep_runner_cpu_limit_explicit
                && config.opengrep_runner_cpu_limit > 0.0 =>
        {
            Some(resources.cpu_limit)
        }
        ContainerRuntime::Podman => None,
    };
    RunnerSpec {
        scanner_type: "opengrep".to_string(),
        image,
        container_runtime,
        workspace_dir: workspace_dir.display().to_string(),
        command: opengrep::build_scan_command(&opengrep::ScanCommandArgs {
            manifest_path: paths.manifest_container_path,
            config_dir: paths.config_container_path,
            target_dir: paths.container_source_dir,
            output_path: paths.output_container_path,
            summary_path: paths.summary_container_path,
            log_path: paths.log_container_path,
            jobs: resources.jobs,
            max_memory_mb: config.opengrep_scan_max_memory_mb,
        }),
        timeout_seconds: config.opengrep_scan_timeout_seconds,
        env: BTreeMap::new(),
        expected_exit_codes: vec![0, 1],
        artifact_paths: Vec::new(),
        capture_stdout_path: Some(paths.stdout_rel_path.to_string()),
        capture_stderr_path: Some(paths.stderr_rel_path.to_string()),
        stdout_limit_bytes: None,
        stderr_limit_bytes: None,
        completion_summary_path: Some(paths.summary_rel_path.to_string()),
        workspace_root_override: None,
        memory_limit_mb: Some(config.opengrep_runner_memory_limit_mb),
        memory_swap_limit_mb: Some(config.opengrep_runner_memory_limit_mb),
        cpu_limit,
        pids_limit: Some(config.opengrep_runner_pids_limit),
        network_disabled: true,
        mount_plan: match container_runtime {
            ContainerRuntime::Podman => Some(build_opengrep_mount_plan(
                workspace_dir,
                &workspace_dir.join("source"),
                &workspace_dir.join("output"),
            )),
        },
    }
}

fn build_opengrep_podman_fallback_runner_spec(
    config: &crate::config::AppConfig,
    image: String,
    workspace_dir: &std::path::Path,
    resources: OpengrepRunnerResources,
    paths: OpengrepRunnerPaths<'_>,
) -> anyhow::Result<RunnerSpec> {
    let mut fallback_config = config.clone();
    fallback_config.opengrep_runner_runtime = "podman".to_string();
    validate_opengrep_runner_deployment_config(&fallback_config)
        .map_err(|error| anyhow::anyhow!(error.to_string()))?;
    Ok(build_opengrep_runner_spec(
        &fallback_config,
        image,
        workspace_dir,
        resources,
        paths,
    ))
}

fn validate_opengrep_runner_deployment_config(
    config: &crate::config::AppConfig,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    match opengrep_container_runtime(config) {
        ContainerRuntime::Podman => {
            let container_host = env::var("CONTAINER_HOST").unwrap_or_default();
            if container_host.contains("docker.sock") {
                return Err("podman runner must not use a Docker socket as CONTAINER_HOST".into());
            }
            Ok(())
        }
    }
}

fn build_opengrep_a3s_box_runner_spec(
    config: &crate::config::AppConfig,
    image: String,
    workspace_dir: &std::path::Path,
    resources: OpengrepRunnerResources,
    task_id: Option<&str>,
    paths: OpengrepRunnerPaths<'_>,
) -> a3s_box_runner::A3sBoxRunnerSpec {
    a3s_box_runner::A3sBoxRunnerSpec {
        scanner_type: "opengrep".to_string(),
        task_id: task_id.map(str::to_string),
        image,
        workspace_dir: workspace_dir.display().to_string(),
        command: opengrep::build_scan_command(&opengrep::ScanCommandArgs {
            manifest_path: paths.manifest_container_path,
            config_dir: paths.config_container_path,
            target_dir: paths.container_source_dir,
            output_path: paths.output_container_path,
            summary_path: paths.summary_container_path,
            log_path: paths.log_container_path,
            jobs: resources.jobs,
            max_memory_mb: config.opengrep_scan_max_memory_mb,
        }),
        timeout_seconds: config.opengrep_scan_timeout_seconds,
        env: BTreeMap::new(),
        expected_exit_codes: vec![0, 1],
        capture_stdout_path: Some(paths.stdout_rel_path.to_string()),
        capture_stderr_path: Some(paths.stderr_rel_path.to_string()),
        memory_limit_mb: Some(config.opengrep_runner_memory_limit_mb),
        cpu_limit: Some(resources.cpu_limit),
        pids_limit: None,
        network_disabled: true,
        stdout_limit_bytes: config.a3s_box_stdout_limit_bytes,
        stderr_limit_bytes: config.a3s_box_stderr_limit_bytes,
        localize_max_source_bytes: Some(
            config
                .argus_a3s_localize_limit_mb
                .saturating_mul(1024 * 1024),
        ),
    }
}

#[derive(Clone, Debug)]
struct OpengrepRunnerInputs {
    workspace_rules_dir: Option<PathBuf>,
    #[cfg(test)]
    image_rule_manifest_paths: Vec<String>,
    #[cfg(test)]
    user_rule_count: usize,
}

async fn prepare_opengrep_runner_inputs(
    state: &AppState,
    workspace_dir: &std::path::Path,
    rule_ids: &[String],
    project_languages: &[String],
) -> Result<Option<OpengrepRunnerInputs>, Box<dyn std::error::Error + Send + Sync>> {
    let image_rule_assets = selected_image_rule_assets(state, rule_ids, project_languages).await?;
    let image_rule_count = image_rule_assets.len();
    #[cfg(test)]
    let image_rule_manifest_paths = image_rule_assets
        .iter()
        .map(|asset| asset.asset_path.clone())
        .collect();
    let workspace_rules_dir =
        opengrep::materialize_rule_assets(workspace_dir, image_rule_assets).await?;
    let rules_root = workspace_rules_dir.unwrap_or_else(|| workspace_dir.join("opengrep-rules"));
    let user_rule_count = materialize_selected_user_rules(state, &rules_root, rule_ids).await?;

    let rule_count = image_rule_count + user_rule_count;
    if rule_count == 0 {
        return Ok(None);
    }

    Ok(Some(OpengrepRunnerInputs {
        workspace_rules_dir: Some(rules_root),
        #[cfg(test)]
        image_rule_manifest_paths,
        #[cfg(test)]
        user_rule_count,
    }))
}

async fn selected_image_rule_assets(
    state: &AppState,
    rule_ids: &[String],
    project_languages: &[String],
) -> Result<Vec<crate::state::ScanRuleAsset>, Box<dyn std::error::Error + Send + Sync>> {
    let assets = if rule_ids.is_empty() {
        opengrep::load_rule_assets_for_languages(state, project_languages).await?
    } else {
        opengrep::load_rule_assets_for_languages(state, project_languages)
            .await?
            .into_iter()
            .filter(|asset| rule_ids.iter().any(|id| id == &asset.asset_path))
            .collect()
    };

    Ok(assets)
}

async fn materialize_selected_user_rules(
    state: &AppState,
    rules_root: &std::path::Path,
    rule_ids: &[String],
) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
    if rule_ids.is_empty() {
        return Ok(0);
    }

    let snapshot = task_state::load_snapshot(state).await?;
    let mut written = 0usize;
    for rule in snapshot
        .opengrep_rules
        .values()
        .filter(|rule| rule.is_active && rule_ids.iter().any(|id| id == &rule.id))
    {
        let filename = format!("{}.yaml", rule.id.replace([':', '/'], "_"));
        let target = rules_root.join("user").join(filename);
        if let Some(parent) = target.parent() {
            tokio::fs::create_dir_all(parent).await?;
        }
        tokio::fs::write(target, &rule.pattern_yaml).await?;
        written += 1;
    }

    Ok(written)
}

async fn format_opengrep_runner_error(
    result: &runner::RunnerResult,
    opengrep_log_path: Option<&std::path::Path>,
) -> String {
    let mut parts = vec![result
        .error
        .clone()
        .unwrap_or_else(|| format!("opengrep exited with code {}", result.exit_code))];

    if let Some(stdout_excerpt) = read_runner_output_excerpt(result.stdout_path.as_deref()).await {
        parts.push(format!("stdout={stdout_excerpt}"));
    }
    if let Some(stderr_excerpt) = read_runner_output_excerpt(result.stderr_path.as_deref()).await {
        parts.push(format!("stderr={stderr_excerpt}"));
    }
    if let Some(log_excerpt) = read_text_excerpt(opengrep_log_path).await {
        parts.push(format!("log={log_excerpt}"));
    }

    parts.join("; ")
}

fn text_excerpt_chars(text: &str, max_chars: usize) -> String {
    let mut chars = text.chars();
    let excerpt: String = chars.by_ref().take(max_chars).collect();
    if chars.next().is_some() {
        format!("{excerpt}[truncated]")
    } else {
        excerpt
    }
}

async fn read_runner_output_excerpt(path: Option<&str>) -> Option<String> {
    read_text_excerpt(path.map(std::path::Path::new)).await
}

async fn read_text_excerpt(path: Option<&std::path::Path>) -> Option<String> {
    let path = path?;
    let text = tokio::fs::read_to_string(path).await.ok()?;
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return None;
    }

    const MAX_EXCERPT_CHARS: usize = 400;
    let excerpt = if trimmed.chars().count() > MAX_EXCERPT_CHARS {
        let tail: String = trimmed
            .chars()
            .rev()
            .take(MAX_EXCERPT_CHARS)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        format!("[truncated] {tail}")
    } else {
        trimmed.to_string()
    };
    Some(excerpt.replace('\n', "\\n"))
}

fn workspace_container_path(
    workspace_dir: &std::path::Path,
    target_path: &std::path::Path,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let relative = target_path.strip_prefix(workspace_dir)?;
    let suffix = relative.to_string_lossy().replace('\\', "/");
    Ok(format!("/scan/{suffix}"))
}

async fn update_scan_progress(
    state: &AppState,
    task_id: &str,
    progress: f64,
    stage: &str,
    message: &str,
) {
    let now = now_rfc3339();
    let Ok(mut snapshot) = task_state::load_snapshot(state).await else {
        return;
    };
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        if record.status == "interrupted" {
            return;
        }
        record.progress.progress = progress;
        record.progress.current_stage = Some(stage.to_string());
        record.progress.message = Some(message.to_string());
        record.progress.updated_at = Some(now.clone());
        record.updated_at = Some(now.clone());
        record
            .progress
            .logs
            .push(task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: stage.to_string(),
                message: message.to_string(),
                progress,
                level: "info".to_string(),
            });
    }
    let _ = task_state::save_snapshot(state, &snapshot).await;
}

async fn push_exploration_event(
    state: &AppState,
    task_id: &str,
    event_type: &str,
    stage: &str,
    progress: f64,
    round: Option<i64>,
    payload: serde_json::Value,
) {
    let now = now_rfc3339();
    let Ok(mut snapshot) = task_state::load_snapshot(state).await else {
        return;
    };
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record
            .progress
            .events
            .push(task_state::StaticTaskProgressEventRecord {
                timestamp: now,
                event_type: event_type.to_string(),
                stage: stage.to_string(),
                progress,
                round,
                redaction: serde_json::Value::Null,
                payload,
            });
    }
    let _ = task_state::save_snapshot(state, &snapshot).await;
}

async fn update_scan_task_failed(
    state: &AppState,
    task_id: &str,
    error_message: &str,
    elapsed_ms: i64,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let now = now_rfc3339();
    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        if record.status == "interrupted" {
            record.progress.progress = 100.0;
            record.progress.current_stage = Some("interrupted".to_string());
            record.progress.message = Some(format!(
                "{} task interrupted in rust backend",
                record.engine
            ));
            record.progress.updated_at = Some(now);
            task_state::save_snapshot(state, &snapshot).await?;
            return Ok(());
        }
        record.status = "failed".to_string();
        record.error_message = Some(error_message.to_string());
        record.scan_duration_ms = elapsed_ms;
        record.updated_at = Some(now.clone());
        record.progress.progress = 100.0;
        record.progress.current_stage = Some("failed".to_string());
        record.progress.message = Some(error_message.to_string());
        record.progress.updated_at = Some(now.clone());
        record
            .progress
            .logs
            .push(task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: "failed".to_string(),
                message: error_message.to_string(),
                progress: 100.0,
                level: "error".to_string(),
            });
    }
    task_state::save_snapshot(state, &snapshot).await?;
    Ok(())
}

fn scan_workspace_root() -> PathBuf {
    std::env::var("SCAN_WORKSPACE_ROOT")
        .ok()
        .map(|v| PathBuf::from(v.trim()))
        .filter(|v| !v.as_os_str().is_empty())
        .unwrap_or_else(|| PathBuf::from("/tmp/Argus/scans"))
}

async fn list_static_tasks(
    state: &AppState,
    engine: &str,
    query: ListQuery,
) -> Result<Json<Vec<Value>>, ApiError> {
    let project_id = query.project_id.or(query.project_id_alias);
    let mut items = load_task_snapshot(state)
        .await?
        .static_tasks
        .into_values()
        .filter(|record| record.engine == engine)
        .filter(|record| match project_id.as_deref() {
            Some(project_id) => record.project_id == project_id,
            None => true,
        })
        .filter(|record| match query.status.as_deref() {
            Some(status) => record.status == status,
            None => true,
        })
        .collect::<Vec<_>>();
    items.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    let mut values = Vec::new();
    for record in items
        .into_iter()
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
    {
        let record = bind_static_task_project_name(state, record).await?;
        values.push(static_task_value(&record));
    }
    Ok(Json(values))
}

async fn get_static_task(
    state: &AppState,
    engine: &str,
    task_id: &str,
) -> Result<Json<Value>, ApiError> {
    let record = find_static_task(state, engine, task_id).await?;
    let record = bind_static_task_project_name(state, record).await?;
    Ok(Json(static_task_value(&record)))
}

async fn delete_static_task(
    state: &AppState,
    engine: &str,
    task_id: &str,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    let existing = snapshot
        .static_tasks
        .get(task_id)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} task not found: {task_id}")))?;
    if existing.engine != engine {
        return Err(ApiError::NotFound(format!(
            "{engine} task not found: {task_id}"
        )));
    }
    snapshot.static_tasks.remove(task_id);
    save_task_snapshot(state, &snapshot).await?;
    Ok(Json(json!({
        "message": format!("{engine} task deleted in rust backend"),
        "task_id": task_id,
    })))
}

async fn interrupt_static_task(
    state: &AppState,
    engine: &str,
    task_id: &str,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    let record = snapshot
        .static_tasks
        .get_mut(task_id)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} task not found: {task_id}")))?;
    if record.engine != engine {
        return Err(ApiError::NotFound(format!(
            "{engine} task not found: {task_id}"
        )));
    }
    record.status = "interrupted".to_string();
    record.progress.current_stage = Some("interrupted".to_string());
    record.progress.message = Some(format!("{engine} task interrupted in rust backend"));
    record.updated_at = Some(now_rfc3339());
    save_task_snapshot(state, &snapshot).await?;
    Ok(Json(json!({
        "message": format!("{engine} task interrupted in rust backend"),
        "task_id": task_id,
        "status": "interrupted",
    })))
}

async fn list_static_findings(
    state: &AppState,
    engine: &str,
    task_id: &str,
    query: &ListQuery,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    let record = snapshot
        .static_tasks
        .get(task_id)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} task not found: {task_id}")))?;
    if record.engine != engine {
        return Err(ApiError::NotFound(format!(
            "{engine} task not found: {task_id}"
        )));
    }

    let items = record
        .findings
        .iter()
        .filter(|finding| match query.status.as_deref() {
            Some(status) => finding.status.eq_ignore_ascii_case(status),
            None => true,
        })
        .filter_map(static_finding_visible_payload)
        .filter(|payload| match query.severity.as_deref() {
            Some(severity) => payload
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|value| value.eq_ignore_ascii_case(severity)),
            None => true,
        })
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
        .collect();

    Ok(Json(items))
}

async fn get_static_finding(
    state: &AppState,
    engine: &str,
    task_id: &str,
    finding_id: &str,
) -> Result<Json<Value>, ApiError> {
    let value = get_static_finding_value(state, engine, task_id, finding_id).await?;
    Ok(Json(value))
}

async fn get_static_finding_value(
    state: &AppState,
    engine: &str,
    task_id: &str,
    finding_id: &str,
) -> Result<Value, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    let record = snapshot
        .static_tasks
        .get(task_id)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} task not found: {task_id}")))?;
    if record.engine != engine {
        return Err(ApiError::NotFound(format!(
            "{engine} task not found: {task_id}"
        )));
    }

    record
        .findings
        .iter()
        .find(|finding| finding.id == finding_id)
        .and_then(static_finding_visible_payload)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} finding not found: {finding_id}")))
}

fn visible_static_finding_count(record: &task_state::StaticTaskRecord) -> i64 {
    record
        .findings
        .iter()
        .filter(|finding| static_finding_display_severity(&finding.payload).is_some())
        .count() as i64
}

fn visible_static_finding_severity_counts(
    record: &task_state::StaticTaskRecord,
) -> (i64, i64, i64) {
    let mut high = 0;
    let mut medium = 0;
    let mut low = 0;

    for finding in &record.findings {
        match static_finding_display_severity(&finding.payload) {
            Some("HIGH") => high += 1,
            Some("MEDIUM") => medium += 1,
            Some("LOW") => low += 1,
            _ => {}
        }
    }

    (high, medium, low)
}

fn static_finding_visible_payload(finding: &task_state::StaticFindingRecord) -> Option<Value> {
    let display_severity = static_finding_display_severity(&finding.payload)?;
    let mut payload = finding.payload.clone();
    if let Some(object) = payload.as_object_mut() {
        if !object.contains_key("raw_severity") {
            let raw_severity = object.get("severity").cloned().unwrap_or(Value::Null);
            object.insert("raw_severity".to_string(), raw_severity);
        }
        object.insert("severity".to_string(), json!(display_severity));
    }
    Some(payload)
}

fn static_finding_display_severity(payload: &Value) -> Option<&'static str> {
    let normalized = payload
        .get("severity")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_uppercase();
    match normalized.as_str() {
        "CRITICAL" => Some("HIGH"),
        "HIGH" => Some("MEDIUM"),
        "ERROR" | "WARNING" | "MEDIUM" => Some("LOW"),
        _ => None,
    }
}

async fn update_static_finding_status(
    state: &AppState,
    engine: &str,
    finding_id: &str,
    status: &str,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    for record in snapshot.static_tasks.values_mut() {
        if record.engine != engine {
            continue;
        }
        if let Some(finding) = record
            .findings
            .iter_mut()
            .find(|finding| finding.id == finding_id)
        {
            finding.status = status.to_string();
            if let Some(object) = finding.payload.as_object_mut() {
                object.insert("status".to_string(), json!(status));
            }
            save_task_snapshot(state, &snapshot).await?;
            return Ok(Json(json!({
                "message": format!("{engine} finding status updated in rust backend"),
                "finding_id": finding_id,
                "status": status,
            })));
        }
    }
    Err(ApiError::NotFound(format!(
        "{engine} finding not found: {finding_id}"
    )))
}

async fn find_static_task(
    state: &AppState,
    engine: &str,
    task_id: &str,
) -> Result<task_state::StaticTaskRecord, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    let record = snapshot
        .static_tasks
        .get(task_id)
        .ok_or_else(|| ApiError::NotFound(format!("{engine} task not found: {task_id}")))?;
    if record.engine != engine {
        return Err(ApiError::NotFound(format!(
            "{engine} task not found: {task_id}"
        )));
    }
    Ok(record.clone())
}

async fn find_opengrep_rule(
    state: &AppState,
    rule_id: &str,
) -> Result<task_state::OpengrepRuleRecord, ApiError> {
    merged_opengrep_rules(state)
        .await?
        .into_iter()
        .find(|rule| rule.id == rule_id)
        .ok_or_else(|| ApiError::NotFound(format!("opengrep rule not found: {rule_id}")))
}

async fn upsert_opengrep_rule(
    state: &AppState,
    record: task_state::OpengrepRuleRecord,
) -> Result<(), ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    snapshot.opengrep_rules.insert(record.id.clone(), record);
    save_task_snapshot(state, &snapshot).await
}

async fn persist_uploaded_opengrep_rules(
    state: &AppState,
    mut multipart: Multipart,
    source: &str,
) -> Result<usize, ApiError> {
    let mut count = 0usize;
    while let Some(field) = multipart.next_field().await.map_err(internal_error)? {
        let filename = field
            .file_name()
            .unwrap_or("uploaded-rule.yaml")
            .to_string();
        let bytes = field.bytes().await.map_err(internal_error)?;
        let pattern_yaml =
            String::from_utf8(bytes.to_vec()).unwrap_or_else(|_| "rules: []".to_string());
        let record = task_state::OpengrepRuleRecord {
            id: format!("{source}:{}", Uuid::new_v4()),
            name: filename.clone(),
            language: "generic".to_string(),
            severity: extract_highest_rule_severity(&pattern_yaml)
                .unwrap_or_else(|| "WARNING".to_string()),
            confidence: Some("MEDIUM".to_string()),
            description: Some("uploaded opengrep rule in rust backend".to_string()),
            cwe: None,
            source: source.to_string(),
            correct: true,
            is_active: true,
            created_at: now_rfc3339(),
            pattern_yaml,
            patch: None,
        };
        upsert_opengrep_rule(state, record).await?;
        count += 1;
    }
    Ok(count)
}

async fn persist_uploaded_patch_rules(
    state: &AppState,
    mut multipart: Multipart,
) -> Result<Vec<String>, ApiError> {
    let mut rule_ids = Vec::new();
    while let Some(field) = multipart.next_field().await.map_err(internal_error)? {
        let filename = field.file_name().unwrap_or("uploaded.patch").to_string();
        let bytes = field.bytes().await.map_err(internal_error)?;
        let patch_text = String::from_utf8(bytes.to_vec()).unwrap_or_default();
        let patch_info = llm_rule::patch::process_patch_text(&filename, &patch_text);
        let record = task_state::OpengrepRuleRecord {
            id: format!("patch:{}", Uuid::new_v4()),
            name: patch_info
                .as_ref()
                .map(|info| format!("{}-{}", info.repo_name, info.commit_id))
                .unwrap_or_else(|| filename.clone()),
            language: patch_info
                .as_ref()
                .and_then(|info| info.file_changes.first())
                .map(|change| change.language.clone())
                .unwrap_or_else(|| "generic".to_string()),
            severity: "ERROR".to_string(),
            confidence: Some("MEDIUM".to_string()),
            description: Some("patch-derived rule shell created in rust backend".to_string()),
            cwe: None,
            source: "patch".to_string(),
            correct: true,
            is_active: true,
            created_at: now_rfc3339(),
            pattern_yaml: patch_text.clone(),
            patch: Some(patch_text),
        };
        let id = record.id.clone();
        upsert_opengrep_rule(state, record).await?;
        rule_ids.push(id);
    }
    Ok(rule_ids)
}

async fn builtin_opengrep_rules(
    state: &AppState,
) -> Result<Vec<task_state::OpengrepRuleRecord>, ApiError> {
    let assets = opengrep::load_rule_assets(state)
        .await
        .map_err(internal_error)?;
    Ok(assets
        .into_iter()
        .filter(|asset| asset.source_kind == "internal_rule")
        .map(|asset| {
            let language = builtin_rule_language(&asset.asset_path);
            task_state::OpengrepRuleRecord {
                id: asset.asset_path.clone(),
                name: file_stem(&asset.asset_path),
                language,
                severity: extract_highest_rule_severity(&asset.content)
                    .unwrap_or_else(|| "WARNING".to_string()),
                confidence: Some("MEDIUM".to_string()),
                description: Some("builtin opengrep rule served by rust backend".to_string()),
                cwe: None,
                source: "internal".to_string(),
                correct: true,
                is_active: true,
                created_at: "2026-01-01T00:00:00Z".to_string(),
                pattern_yaml: asset.content,
                patch: None,
            }
        })
        .collect())
}

fn builtin_rule_language(asset_path: &str) -> String {
    asset_path
        .strip_prefix("rules_opengrep/")
        .and_then(|path| path.split_once('/').map(|(language, _)| language))
        .filter(|language| !language.trim().is_empty())
        .unwrap_or("generic")
        .to_string()
}

async fn merged_opengrep_rules(
    state: &AppState,
) -> Result<Vec<task_state::OpengrepRuleRecord>, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    merged_opengrep_rules_from_snapshot(&snapshot, state).await
}

async fn merged_opengrep_rules_from_snapshot(
    snapshot: &task_state::TaskStateSnapshot,
    state: &AppState,
) -> Result<Vec<task_state::OpengrepRuleRecord>, ApiError> {
    let mut merged = builtin_opengrep_rules(state)
        .await?
        .into_iter()
        .map(|rule| (rule.id.clone(), rule))
        .collect::<BTreeMap<_, _>>();
    for rule in snapshot.opengrep_rules.values() {
        merged.insert(rule.id.clone(), rule.clone());
    }
    let mut items = merged.into_values().collect::<Vec<_>>();
    items.sort_by(|left, right| left.id.cmp(&right.id));
    Ok(items)
}

fn static_task_value(record: &task_state::StaticTaskRecord) -> Value {
    let mut value = json!({});
    let (high_count, medium_count, low_count) = visible_static_finding_severity_counts(record);
    let project_name = record.project_name.as_deref().unwrap_or("-").trim();
    merge_json_object(&mut value, &record.extra);
    merge_json_object(
        &mut value,
        &json!({
        "id": record.id,
        "engine": record.engine,
        "project_id": record.project_id,
        "project_name": if project_name.is_empty() { "-" } else { project_name },
        "name": record.name,
        "status": record.status,
        "target_path": record.target_path,
        "total_findings": visible_static_finding_count(record),
        "critical_count": 0,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "scan_duration_ms": record.scan_duration_ms,
        "files_scanned": record.files_scanned,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "ai_analysis_status": record.ai_analysis_status,
        }),
    );
    value
}

async fn bind_static_task_project_name(
    state: &AppState,
    mut record: task_state::StaticTaskRecord,
) -> Result<task_state::StaticTaskRecord, ApiError> {
    let project = projects::get_project(state, &record.project_id)
        .await
        .map_err(internal_error)?;
    record.project_name = match project {
        Some(project) => Some(project.name),
        None => {
            tracing::warn!(
                task_id = %record.id,
                project_id = %record.project_id,
                "project binding missing for static task; rendering as orphan"
            );
            Some("<项目已删除>".to_string())
        }
    };
    Ok(record)
}

fn opengrep_rule_value(record: &task_state::OpengrepRuleRecord) -> Value {
    json!({
        "id": record.id,
        "name": record.name,
        "language": record.language,
        "severity": record.severity,
        "confidence": record.confidence,
        "description": record.description,
        "cwe": record.cwe,
        "source": record.source,
        "correct": record.correct,
        "is_active": record.is_active,
        "created_at": record.created_at,
    })
}

fn opengrep_rule_detail_value(record: &task_state::OpengrepRuleRecord) -> Value {
    let mut value = opengrep_rule_value(record);
    merge_json_object(
        &mut value,
        &json!({
            "pattern_yaml": record.pattern_yaml,
            "patch": record.patch,
        }),
    );
    value
}

fn filter_opengrep_rules(
    items: Vec<task_state::OpengrepRuleRecord>,
    query: &ListQuery,
) -> Vec<task_state::OpengrepRuleRecord> {
    items
        .into_iter()
        .filter(|rule| match query.source.as_deref() {
            Some(source) => rule.source == source,
            None => true,
        })
        .filter(|rule| match query.language.as_deref() {
            Some(language) => rule.language.eq_ignore_ascii_case(language),
            None => true,
        })
        .filter(|rule| match query.confidence.as_deref() {
            Some(confidence) => rule
                .confidence
                .as_deref()
                .is_some_and(|value| value.eq_ignore_ascii_case(confidence)),
            None => true,
        })
        .filter(|rule| match query.severity.as_deref() {
            Some(severity) => rule.severity.eq_ignore_ascii_case(severity),
            None => true,
        })
        .filter(|rule| match query.is_active {
            Some(is_active) => rule.is_active == is_active,
            None => true,
        })
        .filter(|rule| {
            contains_keyword(&rule.name, query.keyword.as_deref())
                || contains_keyword(&rule.id, query.keyword.as_deref())
        })
        .collect()
}

fn build_rule_record_from_payload(
    payload: &Value,
    yaml_field: &str,
    storage_id_prefix: &str,
    default_source: &str,
    default_description: Option<&str>,
    default_correct: Option<bool>,
    fallback_description: Option<&str>,
) -> Result<task_state::OpengrepRuleRecord, ApiError> {
    let normalized =
        llm_rule::normalize_and_validate_rule_yaml(&required_string(payload, yaml_field)?)
            .map_err(ApiError::BadRequest)?;

    let rule_id = optional_string(payload, "id")
        .unwrap_or_else(|| format!("{storage_id_prefix}:{}", Uuid::new_v4()));
    let name = optional_string(payload, "name").unwrap_or_else(|| normalized.summary.id.clone());
    let language = optional_string(payload, "language")
        .unwrap_or_else(|| normalized.summary.primary_language().to_string());
    let severity =
        optional_string(payload, "severity").unwrap_or_else(|| normalized.summary.severity.clone());
    let description = optional_string(payload, "description")
        .or_else(|| default_description.map(ToString::to_string))
        .or_else(|| fallback_description.map(ToString::to_string));

    Ok(task_state::OpengrepRuleRecord {
        id: rule_id,
        name,
        language,
        severity,
        confidence: optional_string(payload, "confidence").or(Some("MEDIUM".to_string())),
        description,
        cwe: payload.get("cwe").and_then(string_array),
        source: optional_string(payload, "source").unwrap_or_else(|| default_source.to_string()),
        correct: payload
            .get("correct")
            .and_then(Value::as_bool)
            .or(default_correct)
            .unwrap_or(true),
        is_active: payload
            .get("is_active")
            .and_then(Value::as_bool)
            .unwrap_or(true),
        created_at: now_rfc3339(),
        pattern_yaml: normalized.pattern_yaml,
        patch: optional_string(payload, "patch"),
    })
}

async fn load_task_snapshot(state: &AppState) -> Result<task_state::TaskStateSnapshot, ApiError> {
    task_state::load_snapshot(state)
        .await
        .map_err(internal_error)
}

async fn save_task_snapshot(
    state: &AppState,
    snapshot: &task_state::TaskStateSnapshot,
) -> Result<(), ApiError> {
    task_state::save_snapshot(state, snapshot)
        .await
        .map_err(internal_error)
}

fn required_string(payload: &Value, key: &str) -> Result<String, ApiError> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
        .ok_or_else(|| ApiError::BadRequest(format!("missing required field: {key}")))
}

fn optional_string(payload: &Value, key: &str) -> Option<String> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn optional_bool(payload: &Value, key: &str) -> Option<bool> {
    payload.get(key).and_then(Value::as_bool)
}

fn string_array(value: &Value) -> Option<Vec<String>> {
    value.as_array().map(|items| {
        items
            .iter()
            .filter_map(|item| item.as_str().map(ToString::to_string))
            .collect::<Vec<_>>()
    })
}

fn strict_string_array(value: &Value) -> Option<Vec<String>> {
    let items = value.as_array()?;
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        out.push(item.as_str()?.to_string());
    }
    Some(out)
}

fn required_bool(payload: &Value, key: &str) -> Result<bool, ApiError> {
    payload
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| ApiError::BadRequest(format!("{key} must be a boolean")))
}

fn contains_keyword(text: &str, keyword: Option<&str>) -> bool {
    match keyword.map(str::trim).filter(|value| !value.is_empty()) {
        Some(keyword) => text
            .to_ascii_lowercase()
            .contains(&keyword.to_ascii_lowercase()),
        None => true,
    }
}

fn file_stem(path: &str) -> String {
    path.rsplit('/')
        .next()
        .unwrap_or(path)
        .trim_end_matches(".yaml")
        .trim_end_matches(".yml")
        .trim_end_matches(".json")
        .trim_end_matches(".xml")
        .trim_end_matches(".toml")
        .to_string()
}

fn extract_highest_rule_severity(content: &str) -> Option<String> {
    let mut highest = None::<&'static str>;
    for line in content.lines() {
        let trimmed = line.trim();
        let Some(value) = trimmed.strip_prefix("severity:") else {
            continue;
        };
        let normalized = value
            .trim()
            .trim_matches('"')
            .trim_matches('\'')
            .to_uppercase();
        let candidate = match normalized.as_str() {
            "ERROR" => Some("ERROR"),
            "WARNING" => Some("WARNING"),
            "INFO" => Some("INFO"),
            _ => None,
        };
        let Some(candidate) = candidate else {
            continue;
        };
        highest = match (highest, candidate) {
            (Some("ERROR"), _) | (_, "ERROR") => Some("ERROR"),
            (Some("WARNING"), _) | (_, "WARNING") => Some("WARNING"),
            _ => Some("INFO"),
        };
        if highest == Some("ERROR") {
            break;
        }
    }
    highest.map(str::to_string)
}

fn merge_json_object(target: &mut Value, patch: &Value) {
    let Some(target_obj) = target.as_object_mut() else {
        return;
    };
    let Some(patch_obj) = patch.as_object() else {
        return;
    };
    for (key, value) in patch_obj {
        target_obj.insert(key.clone(), value.clone());
    }
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

async fn ai_analysis(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;

    if record.findings.is_empty() {
        return Err(ApiError::BadRequest(
            "当前扫描暂无发现，无需 AI 研判".to_string(),
        ));
    }

    let stored_config = system_config::load_current(&state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::BadRequest("请先配置智能审计 LLM".to_string()))?;
    let selected = crate::routes::llm_config_set::selected_enabled_runtime(
        &stored_config.llm_config_json,
        &stored_config.other_config_json,
        state.config.as_ref(),
    )
    .map_err(|error| ApiError::BadRequest(error.message))?;

    type RuleSummary = (usize, BTreeMap<String, usize>, Vec<String>);
    let mut rule_summary: BTreeMap<String, RuleSummary> = BTreeMap::new();
    for finding in &record.findings {
        let rule = finding
            .payload
            .get("rule_name")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        let severity = finding
            .payload
            .get("severity")
            .and_then(Value::as_str)
            .unwrap_or("UNKNOWN");
        let file = finding
            .payload
            .get("file_path")
            .and_then(Value::as_str)
            .unwrap_or("");
        let line = finding
            .payload
            .get("line")
            .and_then(Value::as_i64)
            .unwrap_or(0);

        let entry = rule_summary
            .entry(rule.to_string())
            .or_insert_with(|| (0, BTreeMap::new(), Vec::new()));
        entry.0 += 1;
        *entry.1.entry(severity.to_string()).or_insert(0) += 1;
        if entry.2.len() < 3 {
            entry.2.push(format!("{file}:{line}"));
        }
    }

    let mut prompt_lines = vec![
        "你是一位安全扫描规则分析专家。请根据以下静态扫描结果，分析当前扫描规则的问题点，并给出优化建议。".to_string(),
        String::new(),
        format!("## 扫描结果摘要（共 {} 条发现，{} 条规则命中）", record.findings.len(), rule_summary.len()),
        String::new(),
    ];
    for (rule, (count, severities, samples)) in &rule_summary {
        let severity_str: Vec<String> = severities
            .iter()
            .map(|(sev, cnt)| format!("{sev}:{cnt}"))
            .collect();
        prompt_lines.push(format!(
            "- **{rule}**: 命中 {count} 次, 严重度分布: [{}], 示例位置: {}",
            severity_str.join(", "),
            samples.join(", ")
        ));
    }
    prompt_lines.extend([
        String::new(),
        "## 请分析以下方面：".to_string(),
        "1. 规则误报率分析：哪些规则可能存在高误报率".to_string(),
        "2. 规则覆盖度分析：是否存在重叠或遗漏".to_string(),
        "3. 规则优化建议：具体的优化方向和步骤".to_string(),
        "4. 优先级建议：哪些规则应该优先优化".to_string(),
    ]);
    let prompt = prompt_lines.join("\n");

    let runtime = &selected.runtime;
    let headers =
        crate::llm::runtime_headers(runtime).map_err(|error| ApiError::Internal(error.message))?;
    let (url, body) = match runtime.provider.as_str() {
        "openai_compatible" => {
            let url = format!(
                "{}/chat/completions",
                runtime.base_url.trim_end_matches('/')
            );
            let body = json!({
                "model": runtime.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": runtime.llm_max_tokens,
                "temperature": runtime.llm_temperature,
                "stream": false
            });
            (url, body)
        }
        "anthropic_compatible" => {
            let url = format!("{}/messages", runtime.base_url.trim_end_matches('/'));
            let body = json!({
                "model": runtime.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": runtime.llm_max_tokens
            });
            (url, body)
        }
        _ => {
            return Err(ApiError::Internal("不支持的 LLM 协议".to_string()));
        }
    };

    let response = state
        .http_client
        .post(&url)
        .headers(headers)
        .json(&body)
        .send()
        .await
        .map_err(|error| ApiError::Internal(format!("LLM 请求失败：{error}")))?;

    let status = response.status();
    let response_json: Value = response
        .json()
        .await
        .map_err(|error| ApiError::Internal(format!("LLM 响应解析失败：{error}")))?;

    if !status.is_success() {
        let error_msg = response_json
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("unknown error");
        return Err(ApiError::Internal(format!(
            "LLM 调用失败 ({status}): {error_msg}"
        )));
    }

    let analysis = match runtime.provider.as_str() {
        "openai_compatible" => response_json
            .pointer("/choices/0/message/content")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        "anthropic_compatible" => response_json
            .get("content")
            .and_then(Value::as_array)
            .and_then(|items| {
                items
                    .iter()
                    .find_map(|item| item.get("text").and_then(Value::as_str))
            })
            .unwrap_or("")
            .to_string(),
        _ => String::new(),
    };

    let tokens_used = response_json
        .pointer("/usage/total_tokens")
        .and_then(Value::as_i64)
        .unwrap_or(0);

    Ok(Json(json!({
        "analysis": analysis,
        "model": runtime.model,
        "tokens_used": tokens_used,
    })))
}

async fn call_llm_json(
    state: &AppState,
    system_prompt: &str,
    user_prompt: &str,
) -> Result<(String, String), ApiError> {
    let stored_config = system_config::load_current(state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::BadRequest("请先配置智能审计 LLM".to_string()))?;
    let selected = crate::routes::llm_config_set::selected_enabled_runtime(
        &stored_config.llm_config_json,
        &stored_config.other_config_json,
        state.config.as_ref(),
    )
    .map_err(|error| ApiError::BadRequest(error.message))?;

    let runtime = &selected.runtime;
    let headers =
        crate::llm::runtime_headers(runtime).map_err(|error| ApiError::Internal(error.message))?;
    let (url, body) = match runtime.provider.as_str() {
        "openai_compatible" => {
            let url = format!(
                "{}/chat/completions",
                runtime.base_url.trim_end_matches('/')
            );
            let body = json!({
                "model": runtime.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": runtime.llm_max_tokens,
                "temperature": runtime.llm_temperature,
                "stream": false
            });
            (url, body)
        }
        "anthropic_compatible" => {
            let url = format!("{}/messages", runtime.base_url.trim_end_matches('/'));
            let body = json!({
                "model": runtime.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": runtime.llm_max_tokens
            });
            (url, body)
        }
        _ => return Err(ApiError::Internal("不支持的 LLM 协议".to_string())),
    };

    let response = state
        .http_client
        .post(&url)
        .headers(headers)
        .json(&body)
        .send()
        .await
        .map_err(|error| ApiError::Internal(format!("LLM 请求失败：{error}")))?;
    let status = response.status();
    let response_json: Value = response
        .json()
        .await
        .map_err(|error| ApiError::Internal(format!("LLM 响应解析失败：{error}")))?;

    if !status.is_success() {
        let error_msg = response_json
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("unknown error");
        return Err(ApiError::Internal(format!(
            "LLM 调用失败 ({status}): {error_msg}"
        )));
    }

    let content = match runtime.provider.as_str() {
        "openai_compatible" => response_json
            .pointer("/choices/0/message/content")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        "anthropic_compatible" => response_json
            .get("content")
            .and_then(Value::as_array)
            .and_then(|items| {
                items
                    .iter()
                    .find_map(|item| item.get("text").and_then(Value::as_str))
            })
            .unwrap_or("")
            .to_string(),
        _ => String::new(),
    };

    Ok((content, runtime.model.clone()))
}

#[derive(Serialize)]
struct EnrichedRuleFinding {
    rule_name: String,
    severity: String,
    hit_count: usize,
    description: String,
    cwe: Vec<String>,
    pattern_yaml: String,
    code_examples: Vec<CodeExample>,
}

#[derive(Serialize)]
struct CodeExample {
    file_path: String,
    start_line: i64,
    code_snippet: String,
}

fn extract_top_rules(
    findings: &[task_state::StaticFindingRecord],
    opengrep_rules: &BTreeMap<String, task_state::OpengrepRuleRecord>,
    top_n: usize,
    max_examples: usize,
) -> Vec<EnrichedRuleFinding> {
    let mut grouped: BTreeMap<String, Vec<&task_state::StaticFindingRecord>> = BTreeMap::new();
    for finding in findings {
        let rule = finding
            .payload
            .get("rule_name")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        grouped.entry(rule.to_string()).or_default().push(finding);
    }

    let mut sorted: Vec<_> = grouped.into_iter().collect();
    sorted.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
    sorted.truncate(top_n);

    sorted
        .into_iter()
        .map(|(rule_name, findings_for_rule)| {
            let rule_record = opengrep_rules.get(&rule_name);
            let severity = findings_for_rule
                .first()
                .and_then(|f| f.payload.get("severity").and_then(Value::as_str))
                .unwrap_or("UNKNOWN")
                .to_string();
            let description = rule_record
                .and_then(|r| r.description.as_deref())
                .unwrap_or("")
                .to_string();
            let cwe = rule_record.and_then(|r| r.cwe.clone()).unwrap_or_default();
            let pattern_yaml = rule_record
                .map(|r| r.pattern_yaml.clone())
                .unwrap_or_default();

            let code_examples: Vec<CodeExample> = findings_for_rule
                .iter()
                .take(max_examples)
                .map(|f| CodeExample {
                    file_path: f
                        .payload
                        .get("file_path")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    start_line: f
                        .payload
                        .get("start_line")
                        .and_then(Value::as_i64)
                        .unwrap_or(0),
                    code_snippet: f
                        .payload
                        .get("code_snippet")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                })
                .collect();

            EnrichedRuleFinding {
                rule_name,
                severity,
                hit_count: findings_for_rule.len(),
                description,
                cwe,
                pattern_yaml,
                code_examples,
            }
        })
        .collect()
}

async fn ai_analyze_code(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;
    if record.findings.is_empty() {
        return Err(ApiError::BadRequest(
            "当前扫描暂无发现，无需分析".to_string(),
        ));
    }

    let enriched = extract_top_rules(&record.findings, &snapshot.opengrep_rules, 5, 3);
    let data_json = serde_json::to_string_pretty(&enriched).unwrap_or_default();

    let system_prompt = "你是一位安全代码分析专家。请分析以下静态扫描命中的代码片段，对每条规则的每个代码示例做路径分析和代码功能总结。请严格以 JSON 格式返回结果。";
    let user_prompt = format!(
        "以下是按规则分组的 Top 5 命中规则及其代码片段：\n\n{data_json}\n\n\
        请对每条规则的每个代码片段进行分析：\n\
        1. 分析代码所属文件路径的模块/功能归属\n\
        2. 分析代码片段本身的功能和上下文含义\n\
        3. 给出该代码片段的简短总结\n\n\
        请严格按以下 JSON 格式返回：\n\
        ```json\n\
        {{\"rules\": [{{\n\
          \"ruleName\": \"规则ID\",\n\
          \"findings\": [{{\n\
            \"filePath\": \"文件路径\",\n\
            \"codeSummary\": \"代码功能总结\"\n\
          }}]\n\
        }}]}}\n\
        ```"
    );

    let (content, model) = call_llm_json(&state, system_prompt, &user_prompt).await?;
    Ok(Json(json!({
        "step": 1,
        "stepName": "代码分析",
        "result": content,
        "model": model,
    })))
}

async fn ai_evaluate_rules(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Json(input): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;
    if record.findings.is_empty() {
        return Err(ApiError::BadRequest(
            "当前扫描暂无发现，无需分析".to_string(),
        ));
    }

    let step1_result = input
        .get("step1Result")
        .and_then(Value::as_str)
        .unwrap_or("");
    let enriched = extract_top_rules(&record.findings, &snapshot.opengrep_rules, 5, 3);

    let mut rule_context = String::new();
    for rule in &enriched {
        rule_context.push_str(&format!(
            "\n### 规则: {}\n- 严重度: {}\n- 命中次数: {}\n- 说明: {}\n- CWE: {}\n- 规则模式:\n```yaml\n{}\n```\n",
            rule.rule_name, rule.severity, rule.hit_count,
            rule.description, rule.cwe.join(", "), rule.pattern_yaml
        ));
    }

    let system_prompt = "你是一位安全扫描规则评估专家。请结合代码分析结果和规则定义，评估每条规则的合理性。请严格以 JSON 格式返回结果。";
    let user_prompt = format!(
        "## 第一步代码分析结果：\n{step1_result}\n\n\
        ## 规则详情：\n{rule_context}\n\n\
        请对每条规则进行评估：\n\
        1. 结合代码分析，判断规则命中是否合理\n\
        2. 分析规则是否存在误报倾向\n\
        3. 评估规则设计的不合理之处\n\n\
        请严格按以下 JSON 格式返回：\n\
        ```json\n\
        {{\"rules\": [{{\n\
          \"ruleName\": \"规则ID\",\n\
          \"severity\": \"严重度\",\n\
          \"hitCount\": 0,\n\
          \"problem\": \"规则存在的问题描述\",\n\
          \"reasonAnalysis\": \"合理性分析\"\n\
        }}]}}\n\
        ```"
    );

    let (content, model) = call_llm_json(&state, system_prompt, &user_prompt).await?;
    Ok(Json(json!({
        "step": 2,
        "stepName": "规则评估",
        "result": content,
        "model": model,
    })))
}

async fn ai_suggest_fixes(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Json(input): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;
    if record.findings.is_empty() {
        return Err(ApiError::BadRequest(
            "当前扫描暂无发现，无需分析".to_string(),
        ));
    }

    let step1_result = input
        .get("step1Result")
        .and_then(Value::as_str)
        .unwrap_or("");
    let step2_result = input
        .get("step2Result")
        .and_then(Value::as_str)
        .unwrap_or("");
    let enriched = extract_top_rules(&record.findings, &snapshot.opengrep_rules, 5, 3);

    let mut code_examples_json = String::new();
    for rule in &enriched {
        for ex in &rule.code_examples {
            code_examples_json.push_str(&format!(
                "- 规则 `{}` 在 `{}:{}`: ```{}```\n",
                rule.rule_name, ex.file_path, ex.start_line, ex.code_snippet
            ));
        }
    }

    let system_prompt = "你是一位安全扫描规则优化专家。请基于代码分析和规则评估结果，给出每条规则的修复建议和优先级。请严格以 JSON 格式返回结果。";
    let user_prompt = format!(
        "## 第一步代码分析结果：\n{step1_result}\n\n\
        ## 第二步规则评估结果：\n{step2_result}\n\n\
        ## 命中代码示例：\n{code_examples_json}\n\n\
        请对每条规则给出修复建议：\n\
        1. 结合代码分析和规则评估，给出具体的修复方向\n\
        2. 评估修复优先级（high/medium/low）\n\
        3. 给出代码层面的修改建议\n\n\
        请严格按以下 JSON 格式返回：\n\
        ```json\n\
        {{\"rules\": [{{\n\
          \"ruleName\": \"规则ID\",\n\
          \"severity\": \"严重度\",\n\
          \"hitCount\": 0,\n\
          \"problem\": \"问题描述\",\n\
          \"codeExamples\": [{{\"file\": \"文件路径\", \"code\": \"代码片段\"}}],\n\
          \"suggestion\": \"修复建议\",\n\
          \"priority\": \"high|medium|low\"\n\
        }}]}}\n\
        ```"
    );

    let (content, model) = call_llm_json(&state, system_prompt, &user_prompt).await?;
    Ok(Json(json!({
        "step": 3,
        "stepName": "修复建议",
        "result": content,
        "model": model,
    })))
}

async fn ai_analysis_start(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    {
        let snapshot = load_task_snapshot(&state).await?;
        let record = snapshot
            .static_tasks
            .get(&task_id)
            .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;

        if record.status != "completed" {
            return Err(ApiError::BadRequest(
                "仅已完成的扫描任务可触发 AI 分析".to_string(),
            ));
        }
        if record.findings.is_empty() {
            return Err(ApiError::BadRequest(
                "当前扫描暂无发现，无需 AI 分析".to_string(),
            ));
        }
        if record.ai_analysis_status.as_deref() == Some("analyzing") {
            return Err(ApiError::BadRequest("AI 分析任务正在执行中".to_string()));
        }
    }

    let now = now_rfc3339();
    {
        let _guard = state.file_store_lock.lock().await;
        let mut snapshot = task_state::load_snapshot_unlocked(&state)
            .await
            .map_err(internal_error)?;
        if let Some(record) = snapshot.static_tasks.get_mut(&task_id) {
            record.ai_analysis_status = Some("analyzing".to_string());
            record.ai_analysis_step = Some(1);
            record.ai_analysis_step_name = Some("代码分析".to_string());
            record.ai_analysis_result = None;
            record.ai_analysis_error = None;
            record.ai_analysis_model = None;
            record.ai_analysis_started_at = Some(now.clone());
            record.ai_analysis_completed_at = None;
        }
        task_state::save_snapshot_unlocked(&state, &snapshot)
            .await
            .map_err(internal_error)?;
    }

    let bg_state = state.clone();
    let bg_task_id = task_id.clone();
    tokio::spawn(async move {
        run_ai_analysis_background(bg_state, bg_task_id).await;
    });

    Ok(Json(
        json!({ "message": "AI 分析任务已启动", "task_id": task_id }),
    ))
}

async fn run_ai_analysis_background(state: AppState, task_id: String) {
    let update_ai_state = |state: &AppState, task_id: &str, step: i32, step_name: &str| {
        let state = state.clone();
        let task_id = task_id.to_string();
        let step_name = step_name.to_string();
        async move {
            let _guard = state.file_store_lock.lock().await;
            let mut snapshot = match task_state::load_snapshot_unlocked(&state).await {
                Ok(s) => s,
                Err(_) => return,
            };
            if let Some(record) = snapshot.static_tasks.get_mut(&task_id) {
                record.ai_analysis_step = Some(step);
                record.ai_analysis_step_name = Some(step_name);
            }
            let _ = task_state::save_snapshot_unlocked(&state, &snapshot).await;
        }
    };

    let result: Result<(Value, String), String> = async {
        // Step 1: Code analysis
        let snapshot = task_state::load_snapshot(&state).await.map_err(|e| e.to_string())?;
        let record = snapshot.static_tasks.get(&task_id)
            .ok_or_else(|| format!("task not found: {task_id}"))?;
        let enriched = extract_top_rules(&record.findings, &snapshot.opengrep_rules, 5, 3);
        let data_json = serde_json::to_string_pretty(&enriched).unwrap_or_default();

        let step1_system = "你是一位安全代码分析专家。请分析以下静态扫描命中的代码片段，对每条规则的每个代码示例做路径分析和代码功能总结。请严格以 JSON 格式返回结果。";
        let step1_user = format!(
            "以下是按规则分组的 Top 5 命中规则及其代码片段：\n\n{data_json}\n\n\
            请对每条规则的每个代码片段进行分析：\n\
            1. 分析代码所属文件路径的模块/功能归属\n\
            2. 分析代码片段本身的功能和上下文含义\n\
            3. 给出该代码片段的简短总结\n\n\
            请严格按以下 JSON 格式返回：\n\
            ```json\n\
            {{\"rules\": [{{\n\
              \"ruleName\": \"规则ID\",\n\
              \"findings\": [{{\n\
                \"filePath\": \"文件路径\",\n\
                \"codeSummary\": \"代码功能总结\"\n\
              }}]\n\
            }}]}}\n\
            ```"
        );
        let (step1_text, _model) = call_llm_json(&state, step1_system, &step1_user).await
            .map_err(|e| format!("Step 1 失败: {e}"))?;

        // Step 2: Rule evaluation
        update_ai_state(&state, &task_id, 2, "规则评估").await;

        let mut rule_context = String::new();
        for rule in &enriched {
            rule_context.push_str(&format!(
                "\n### 规则: {}\n- 严重度: {}\n- 命中次数: {}\n- 说明: {}\n- CWE: {}\n- 规则模式:\n```yaml\n{}\n```\n",
                rule.rule_name, rule.severity, rule.hit_count,
                rule.description, rule.cwe.join(", "), rule.pattern_yaml
            ));
        }

        let step2_system = "你是一位安全扫描规则评估专家。请结合代码分析结果和规则定义，评估每条规则的合理性。请严格以 JSON 格式返回结果。";
        let step2_user = format!(
            "## 第一步代码分析结果：\n{step1_text}\n\n\
            ## 规则详情：\n{rule_context}\n\n\
            请对每条规则进行评估：\n\
            1. 结合代码分析，判断规则命中是否合理\n\
            2. 分析规则是否存在误报倾向\n\
            3. 评估规则设计的不合理之处\n\n\
            请严格按以下 JSON 格式返回：\n\
            ```json\n\
            {{\"rules\": [{{\n\
              \"ruleName\": \"规则ID\",\n\
              \"severity\": \"严重度\",\n\
              \"hitCount\": 0,\n\
              \"problem\": \"规则存在的问题描述\",\n\
              \"reasonAnalysis\": \"合理性分析\"\n\
            }}]}}\n\
            ```"
        );
        let (step2_text, _model) = call_llm_json(&state, step2_system, &step2_user).await
            .map_err(|e| format!("Step 2 失败: {e}"))?;

        // Step 3: Fix suggestions
        update_ai_state(&state, &task_id, 3, "修复建议").await;

        let mut code_examples_json = String::new();
        for rule in &enriched {
            for ex in &rule.code_examples {
                code_examples_json.push_str(&format!(
                    "- 规则 `{}` 在 `{}:{}`: ```{}```\n",
                    rule.rule_name, ex.file_path, ex.start_line, ex.code_snippet
                ));
            }
        }

        let step3_system = "你是一位安全扫描规则优化专家。请基于代码分析和规则评估结果，给出每条规则的修复建议和优先级。请严格以 JSON 格式返回结果。";
        let step3_user = format!(
            "## 第一步代码分析结果：\n{step1_text}\n\n\
            ## 第二步规则评估结果：\n{step2_text}\n\n\
            ## 命中代码示例：\n{code_examples_json}\n\n\
            请对每条规则给出修复建议：\n\
            1. 结合代码分析和规则评估，给出具体的修复方向\n\
            2. 评估修复优先级（high/medium/low）\n\
            3. 给出代码层面的修改建议\n\n\
            请严格按以下 JSON 格式返回：\n\
            ```json\n\
            {{\"rules\": [{{\n\
              \"ruleName\": \"规则ID\",\n\
              \"severity\": \"严重度\",\n\
              \"hitCount\": 0,\n\
              \"problem\": \"问题描述\",\n\
              \"codeExamples\": [{{\"file\": \"文件路径\", \"code\": \"代码片段\"}}],\n\
              \"suggestion\": \"修复建议\",\n\
              \"priority\": \"high|medium|low\"\n\
            }}]}}\n\
            ```"
        );
        let (step3_text, model) = call_llm_json(&state, step3_system, &step3_user).await
            .map_err(|e| format!("Step 3 失败: {e}"))?;

        let parsed: Value = {
            let json_match = step3_text.find("```json")
                .and_then(|start| {
                    let content_start = start + 7;
                    step3_text[content_start..].find("```").map(|end| &step3_text[content_start..content_start + end])
                })
                .or_else(|| {
                    let trimmed = step3_text.trim();
                    if trimmed.starts_with('{') { Some(trimmed) } else { None }
                });
            json_match.and_then(|s| serde_json::from_str(s).ok())
        }
        .unwrap_or_else(|| json!({ "rules": [], "raw": step3_text }));

        Ok((parsed, model))
    }.await;

    let now = now_rfc3339();
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = match task_state::load_snapshot_unlocked(&state).await {
        Ok(s) => s,
        Err(_) => return,
    };
    if let Some(record) = snapshot.static_tasks.get_mut(&task_id) {
        match result {
            Ok((parsed, model)) => {
                record.ai_analysis_status = Some("completed".to_string());
                record.ai_analysis_step = Some(3);
                record.ai_analysis_step_name = Some("修复建议".to_string());
                record.ai_analysis_result = Some(parsed);
                record.ai_analysis_model = Some(model);
                record.ai_analysis_error = None;
                record.ai_analysis_completed_at = Some(now);
            }
            Err(error_msg) => {
                record.ai_analysis_status = Some("failed".to_string());
                record.ai_analysis_error = Some(error_msg);
                record.ai_analysis_completed_at = Some(now);
            }
        }
    }
    let _ = task_state::save_snapshot_unlocked(&state, &snapshot).await;
}

async fn ai_analysis_status(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .ok_or_else(|| ApiError::NotFound(format!("static task not found: {task_id}")))?;

    let status = record
        .ai_analysis_status
        .as_deref()
        .unwrap_or("not_started");
    let mut response = json!({
        "status": status,
        "current_step": record.ai_analysis_step,
        "step_name": record.ai_analysis_step_name,
        "model": record.ai_analysis_model,
        "started_at": record.ai_analysis_started_at,
        "completed_at": record.ai_analysis_completed_at,
    });

    if status == "completed" {
        if let Some(result) = &record.ai_analysis_result {
            response["result"] = result.clone();
        }
    }
    if status == "failed" {
        response["error"] = json!(record.ai_analysis_error);
    }

    Ok(Json(response))
}

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(error.to_string())
}

#[cfg(test)]
mod tests {
    use crate::config::AppConfig;
    use crate::db::task_state;
    use crate::runtime::runner::ContainerRuntime;

    use super::{
        build_joern_runner_spec, build_opengrep_a3s_box_runner_spec, build_opengrep_mount_plan,
        build_opengrep_podman_fallback_runner_spec, build_opengrep_runner_spec,
        extract_highest_rule_severity, extract_opengrep_task_options, format_opengrep_runner_error,
        prepare_opengrep_runner_inputs, prune_static_scan_non_source_paths,
        read_opengrep_results_text, static_task_value, validate_opengrep_runner_deployment_config,
        OpengrepResourceScheduler, OpengrepRunnerPaths, OpengrepRunnerResources,
        OpengrepSandboxKind,
    };
    use serde_json::json;
    use std::{
        fs,
        path::Path,
        sync::{mpsc, LazyLock, Mutex},
        time::Duration,
    };

    static TEST_ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

    fn static_task_record_with_findings(
        findings: Vec<task_state::StaticFindingRecord>,
    ) -> task_state::StaticTaskRecord {
        task_state::StaticTaskRecord {
            id: "task-1".to_string(),
            engine: "opengrep".to_string(),
            project_id: "project-1".to_string(),
            project_name: Some("Project 1".to_string()),
            name: "static scan".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            total_findings: findings.len() as i64,
            scan_duration_ms: 42,
            files_scanned: 1,
            created_at: "2026-04-27T01:42:09Z".to_string(),
            extra: json!({
                "error_count": 9,
                "warning_count": 8,
            }),
            findings,
            ..Default::default()
        }
    }

    fn write_fixture_file(root: &Path, relative: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("fixture parent")).expect("create parent");
        fs::write(path, "fixture").expect("write fixture");
    }

    #[test]
    fn opengrep_static_scan_source_prune_removes_non_source_inputs() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let root = temp_dir.path();

        for path in [
            "src/main.c",
            "lib/service.py",
            "tests/test_api.py",
            "src/parser_fuzz.cc",
            ".env",
            ".github/workflows/ci.yml",
            "config/app.yaml",
            "settings.toml",
            "package.json",
        ] {
            write_fixture_file(root, path);
        }

        let removed = prune_static_scan_non_source_paths(root).expect("prune OpenGrep scan source");

        assert_eq!(removed, 7);
        for kept in ["src/main.c", "lib/service.py"] {
            assert!(root.join(kept).exists(), "expected {kept} to remain");
        }
        for pruned in [
            "tests/test_api.py",
            "src/parser_fuzz.cc",
            ".env",
            ".github/workflows/ci.yml",
            "config/app.yaml",
            "settings.toml",
            "package.json",
        ] {
            assert!(
                !root.join(pruned).exists(),
                "expected {pruned} to be pruned"
            );
        }
    }

    #[test]
    fn extract_highest_rule_severity_prefers_error_over_warning_and_info() {
        let content = r#"
rules:
  - id: first-rule
    severity: WARNING
  - id: second-rule
    severity: INFO
  - id: third-rule
    severity: ERROR
"#;

        assert_eq!(
            extract_highest_rule_severity(content),
            Some("ERROR".to_string())
        );
    }

    #[test]
    fn extract_highest_rule_severity_handles_warning_only_assets() {
        let content = r#"
rules:
  - id: only-warning
    severity: WARNING
"#;

        assert_eq!(
            extract_highest_rule_severity(content),
            Some("WARNING".to_string())
        );
    }

    #[test]
    fn static_task_value_counts_only_visible_findings() {
        let record = static_task_record_with_findings(vec![
            task_state::StaticFindingRecord {
                id: "finding-1".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-1",
                    "severity": "ERROR",
                }),
            },
            task_state::StaticFindingRecord {
                id: "finding-hidden".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-hidden",
                    "severity": "INFO",
                }),
            },
        ]);

        let value = static_task_value(&record);

        assert_eq!(value["total_findings"], 1);
        assert_eq!(value["critical_count"], 0);
        assert_eq!(value["high_count"], 0);
        assert_eq!(value["medium_count"], 0);
        assert_eq!(value["low_count"], 1);
    }

    #[test]
    fn static_task_value_does_not_report_findings_without_detail_payloads() {
        let record = static_task_record_with_findings(Vec::new());

        let value = static_task_value(&record);

        assert_eq!(value["total_findings"], 0);
    }

    #[test]
    fn static_task_value_reports_visible_severity_buckets() {
        let record = static_task_record_with_findings(vec![
            task_state::StaticFindingRecord {
                id: "finding-critical".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-critical",
                    "severity": "CRITICAL",
                }),
            },
            task_state::StaticFindingRecord {
                id: "finding-high".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-high",
                    "severity": "HIGH",
                }),
            },
            task_state::StaticFindingRecord {
                id: "finding-error".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-error",
                    "severity": "ERROR",
                }),
            },
            task_state::StaticFindingRecord {
                id: "finding-hidden".to_string(),
                scan_task_id: "task-1".to_string(),
                status: "open".to_string(),
                payload: json!({
                    "id": "finding-hidden",
                    "severity": "INFO",
                }),
            },
        ]);

        let value = static_task_value(&record);

        assert_eq!(value["total_findings"], 3);
        assert_eq!(value["critical_count"], 0);
        assert_eq!(value["high_count"], 1);
        assert_eq!(value["medium_count"], 1);
        assert_eq!(value["low_count"], 1);
    }

    #[test]
    fn static_task_value_prefers_visible_findings_over_extra_summary_count() {
        let mut record = static_task_record_with_findings(vec![task_state::StaticFindingRecord {
            id: "finding-1".to_string(),
            scan_task_id: "task-1".to_string(),
            status: "open".to_string(),
            payload: json!({
                "id": "finding-1",
                "severity": "ERROR",
            }),
        }]);
        record.extra = json!({
            "total_findings": 9,
            "error_count": 9,
            "warning_count": 0,
        });

        let value = static_task_value(&record);

        assert_eq!(value["total_findings"], 1);
        assert_eq!(value["error_count"], 9);
    }

    #[test]
    fn builds_opengrep_runner_spec_with_stdout_capture_and_resource_limits() {
        let config = AppConfig::for_tests();

        let spec = build_opengrep_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
            OpengrepRunnerResources {
                jobs: 8,
                cpu_limit: 8.0,
                allocated_cores: 8,
                total_cores: 8,
            },
            OpengrepRunnerPaths {
                container_source_dir: "/scan/source",
                manifest_container_path: None,
                config_container_path: Some("/scan/opengrep-rules"),
                output_container_path: "/scan/output/results-001.json",
                summary_rel_path: "output/summary-001.json",
                summary_container_path: "/scan/output/summary-001.json",
                log_container_path: "/scan/output/log-001.txt",
                stdout_rel_path: "output/stdout-001.txt",
                stderr_rel_path: "output/stderr-001.txt",
            },
        );

        assert_eq!(spec.scanner_type, "opengrep");
        assert_eq!(
            spec.capture_stdout_path.as_deref(),
            Some("output/stdout-001.txt")
        );
        assert_eq!(
            spec.capture_stderr_path.as_deref(),
            Some("output/stderr-001.txt")
        );
        assert_eq!(
            spec.completion_summary_path.as_deref(),
            Some("output/summary-001.json")
        );
        assert_eq!(spec.memory_limit_mb, Some(2048));
        assert_eq!(spec.memory_swap_limit_mb, Some(2048));
        assert_eq!(spec.cpu_limit, Some(8.0));
        assert_eq!(spec.pids_limit, Some(512));
        assert!(spec.network_disabled);
        assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
        assert!(
            spec.mount_plan.is_none(),
            "Podman default must keep the named scan workspace volume path"
        );
        assert_eq!(spec.timeout_seconds, 0);
        assert_eq!(
            spec.command,
            crate::scan::opengrep::build_scan_command(&crate::scan::opengrep::ScanCommandArgs {
                manifest_path: None,
                config_dir: Some("/scan/opengrep-rules"),
                target_dir: "/scan/source",
                output_path: "/scan/output/results-001.json",
                summary_path: "/scan/output/summary-001.json",
                log_path: "/scan/output/log-001.txt",
                jobs: 8,
                max_memory_mb: 2048,
            })
        );
    }

    #[test]
    fn opengrep_runner_runtime_can_select_podman() {
        let mut config = AppConfig::for_tests();
        config.opengrep_runner_runtime = "podman".to_string();
        config.opengrep_runner_cpu_limit_explicit = false;
        config.opengrep_runner_cpu_limit = 0.0;

        let spec = build_opengrep_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
            OpengrepRunnerResources {
                jobs: 2,
                cpu_limit: 2.0,
                allocated_cores: 2,
                total_cores: 2,
            },
            OpengrepRunnerPaths {
                container_source_dir: "/scan/source",
                manifest_container_path: None,
                config_container_path: Some("/tmp/opengrep-runtime/opengrep-rules"),
                output_container_path: "/tmp/opengrep-runtime/output/results.json",
                summary_rel_path: "output/summary.json",
                summary_container_path: "/tmp/opengrep-runtime/output/summary.json",
                log_container_path: "/tmp/opengrep-runtime/output/log.txt",
                stdout_rel_path: "output/stdout.txt",
                stderr_rel_path: "output/stderr.txt",
            },
        );

        assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
        assert!(spec.network_disabled);
        assert!(
            spec.cpu_limit.is_none(),
            "default rootless Podman path must not require the cpu cgroup controller"
        );
        let mount_plan = spec.mount_plan.expect("mount plan");
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| { mount.container_path == "/scan/source" && mount.read_only }));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| { mount.container_path == "/scan/output" && !mount.read_only }));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| { mount.container_path == "/scan/opengrep-rules" && mount.read_only }));
    }

    #[test]
    fn opengrep_runner_podman_honors_explicit_cpu_limit_opt_in() {
        let mut config = AppConfig::for_tests();
        config.opengrep_runner_runtime = "podman".to_string();
        config.opengrep_runner_cpu_limit_explicit = true;
        config.opengrep_runner_cpu_limit = 2.5;

        let spec = build_opengrep_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
            OpengrepRunnerResources {
                jobs: 2,
                cpu_limit: 2.5,
                allocated_cores: 3,
                total_cores: 8,
            },
            OpengrepRunnerPaths {
                container_source_dir: "/scan/source",
                manifest_container_path: None,
                config_container_path: Some("/scan/opengrep-rules"),
                output_container_path: "/scan/output/results.json",
                summary_rel_path: "output/summary.json",
                summary_container_path: "/scan/output/summary.json",
                log_container_path: "/scan/output/log.txt",
                stdout_rel_path: "output/stdout.txt",
                stderr_rel_path: "output/stderr.txt",
            },
        );

        assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
        assert_eq!(spec.cpu_limit, Some(2.5));
    }

    #[test]
    fn joern_runner_spec_uses_runner_spec_with_stable_outputs_and_resources() {
        let mut config = AppConfig::for_tests();
        config.scanner_joern_image = "local/joern:test".to_string();
        config.joern_scan_timeout_seconds = 123;
        config.joern_runner_memory_limit_mb = 8192;
        config.joern_runner_cpu_limit = 2.5;
        config.joern_runner_pids_limit = 2048;
        config.joern_network_disabled = true;
        config.joern_stdout_limit_bytes = 23456;
        config.joern_stderr_limit_bytes = 34567;

        let temp_dir = tempfile::tempdir().expect("temp dir");
        let workspace_dir = temp_dir.path();
        let source_dir = workspace_dir.join("source");
        let query_dir = workspace_dir.join("joern-queries");
        let output_dir = workspace_dir.join("output");
        let spec =
            build_joern_runner_spec(&config, workspace_dir, &source_dir, &query_dir, &output_dir);

        assert_eq!(spec.scanner_type, "joern");
        assert_eq!(spec.image, "local/joern:test");
        assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
        assert_eq!(
            spec.command,
            vec!["/bin/sh", "/scan/workspace/argus-joern-wrapper.sh"]
        );
        assert_eq!(spec.timeout_seconds, 123);
        assert_eq!(
            spec.capture_stdout_path.as_deref(),
            Some("output/stdout.log")
        );
        assert_eq!(
            spec.capture_stderr_path.as_deref(),
            Some("output/stderr.log")
        );
        assert_eq!(spec.stdout_limit_bytes, Some(23456));
        assert_eq!(spec.stderr_limit_bytes, Some(34567));
        assert_eq!(
            spec.completion_summary_path.as_deref(),
            Some("output/summary.json")
        );
        assert_eq!(spec.memory_limit_mb, Some(8192));
        assert_eq!(spec.memory_swap_limit_mb, Some(8192));
        assert_eq!(spec.cpu_limit, Some(2.5));
        assert_eq!(spec.pids_limit, Some(2048));
        assert!(spec.network_disabled);
        assert_eq!(spec.env["JOERN_SOURCE_DIR"], "/scan/source");
        assert_eq!(spec.env["JOERN_OUTPUT_DIR"], "/scan/output");
        assert_eq!(spec.env["JOERN_QUERY_DIR"], "/scan/joern-queries");
        let mount_plan = spec.mount_plan.expect("joern mount plan");
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/workspace" && !mount.read_only));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/source" && mount.read_only));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/joern-queries" && mount.read_only));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/output" && !mount.read_only));
    }

    #[test]
    fn opengrep_a3s_fallback_builder_pins_podman_runtime_and_mounts() {
        let mut config = AppConfig::for_tests();
        config.opengrep_runner_runtime = "docker".to_string();

        let spec = build_opengrep_podman_fallback_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
            OpengrepRunnerResources {
                jobs: 2,
                cpu_limit: 2.0,
                allocated_cores: 2,
                total_cores: 2,
            },
            OpengrepRunnerPaths {
                container_source_dir: "/scan/source",
                manifest_container_path: None,
                config_container_path: Some("/scan/opengrep-rules"),
                output_container_path: "/scan/output/results.json",
                summary_rel_path: "output/summary.json",
                summary_container_path: "/scan/output/summary.json",
                log_container_path: "/scan/output/log.txt",
                stdout_rel_path: "output/stdout.txt",
                stderr_rel_path: "output/stderr.txt",
            },
        )
        .expect("A3S Podman fallback spec");

        assert_eq!(spec.container_runtime, ContainerRuntime::Podman);
        assert!(spec.network_disabled);
        let mount_plan = spec.mount_plan.expect("Podman fallback mount plan");
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/source" && mount.read_only));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/opengrep-rules" && mount.read_only));
        assert!(mount_plan
            .mounts
            .iter()
            .any(|mount| mount.container_path == "/scan/output" && !mount.read_only));
    }

    #[test]
    fn text_excerpt_chars_truncates_without_splitting_utf8() {
        let text = format!("{}终", "a".repeat(1024));

        let excerpt = super::text_excerpt_chars(&text, 1024);

        assert_eq!(excerpt, "a".repeat(1024) + "[truncated]");
    }

    #[test]
    fn text_excerpt_chars_handles_workspace_listing_limit() {
        let listing = format!("{}终", "a".repeat(4096));

        let excerpt = super::text_excerpt_chars(&listing, 4096);

        assert_eq!(excerpt, "a".repeat(4096) + "[truncated]");
    }

    #[test]
    fn opengrep_runner_podman_deployment_rejects_docker_socket_host() {
        let _guard = TEST_ENV_LOCK.lock().expect("env lock");
        let mut config = AppConfig::for_tests();
        config.opengrep_runner_runtime = "podman".to_string();
        let previous = std::env::var("CONTAINER_HOST").ok();
        std::env::set_var("CONTAINER_HOST", "unix:///var/run/docker.sock");

        let result = validate_opengrep_runner_deployment_config(&config);

        if let Some(previous) = previous {
            std::env::set_var("CONTAINER_HOST", previous);
        } else {
            std::env::remove_var("CONTAINER_HOST");
        }
        assert!(result
            .err()
            .is_some_and(|error| error.to_string().contains("must not use a Docker socket")));
    }

    #[test]
    fn opengrep_a3s_podman_fallback_builder_rejects_docker_socket_host() {
        let _guard = TEST_ENV_LOCK.lock().expect("env lock");
        let mut config = AppConfig::for_tests();
        config.opengrep_runner_runtime = "docker".to_string();
        let previous = std::env::var("CONTAINER_HOST").ok();
        std::env::set_var("CONTAINER_HOST", "unix:///var/run/docker.sock");

        let result = build_opengrep_podman_fallback_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
            OpengrepRunnerResources {
                jobs: 2,
                cpu_limit: 2.0,
                allocated_cores: 2,
                total_cores: 2,
            },
            OpengrepRunnerPaths {
                container_source_dir: "/scan/source",
                manifest_container_path: None,
                config_container_path: Some("/scan/opengrep-rules"),
                output_container_path: "/scan/output/results.json",
                summary_rel_path: "output/summary.json",
                summary_container_path: "/scan/output/summary.json",
                log_container_path: "/scan/output/log.txt",
                stdout_rel_path: "output/stdout.txt",
                stderr_rel_path: "output/stderr.txt",
            },
        );

        if let Some(previous) = previous {
            std::env::set_var("CONTAINER_HOST", previous);
        } else {
            std::env::remove_var("CONTAINER_HOST");
        }
        assert!(result
            .err()
            .is_some_and(|error| error.to_string().contains("must not use a Docker socket")));
    }

    #[test]
    fn build_opengrep_mount_plan_splits_readonly_source_and_writable_output() {
        let plan = build_opengrep_mount_plan(
            Path::new("/tmp/workspace"),
            Path::new("/tmp/workspace/source"),
            Path::new("/tmp/workspace/output"),
        );

        assert!(plan.mounts.iter().any(|mount| {
            mount.host_path == "/tmp/workspace/source"
                && mount.container_path == "/scan/source"
                && mount.read_only
        }));
        assert!(plan.mounts.iter().any(|mount| {
            mount.host_path == "/tmp/workspace/output"
                && mount.container_path == "/scan/output"
                && !mount.read_only
        }));
        assert!(plan.mounts.iter().any(|mount| {
            mount.host_path == "/tmp/workspace/opengrep-rules"
                && mount.container_path == "/scan/opengrep-rules"
                && mount.read_only
        }));
    }

    #[tokio::test]
    async fn opengrep_runner_inputs_preserve_image_rule_manifest_paths_for_oci() {
        let state = crate::state::AppState::from_config(AppConfig::for_tests())
            .await
            .expect("test state");
        let workspace =
            std::env::temp_dir().join(format!("opengrep-runner-inputs-{}", uuid::Uuid::new_v4()));
        let inputs = prepare_opengrep_runner_inputs(
            &state,
            &workspace,
            &["rules_opengrep/python/sqlalchemy-sql-injection.yaml".to_string()],
            &["Python".to_string()],
        )
        .await
        .expect("runner inputs")
        .expect("rules should exist");

        assert_eq!(
            inputs.image_rule_manifest_paths,
            vec!["rules_opengrep/python/sqlalchemy-sql-injection.yaml".to_string()]
        );
        assert_eq!(inputs.user_rule_count, 0);
        assert!(
            inputs
                .workspace_rules_dir
                .expect("workspace rules")
                .join("internal/python/sqlalchemy-sql-injection.yaml")
                .exists(),
            "Docker path still materializes selected image rules"
        );
        let _ = tokio::fs::remove_dir_all(workspace).await;
    }

    #[test]
    fn opengrep_task_options_default_to_dockerfile_container_and_accept_a3s_box() {
        let default_options = extract_opengrep_task_options(&json!({}));
        assert_eq!(
            default_options.sandbox,
            OpengrepSandboxKind::DockerfileContainer
        );

        let a3s_box_options = extract_opengrep_task_options(&json!({
            "opengrep_sandbox": "a3s_box",
        }));
        assert_eq!(a3s_box_options.sandbox, OpengrepSandboxKind::A3sBox);
    }

    #[test]
    fn opengrep_task_options_tolerate_legacy_sandbox_key_and_unknown_values() {
        let legacy_options = extract_opengrep_task_options(&json!({
            "sandbox": "dockerfile_container",
        }));
        assert_eq!(
            legacy_options.sandbox,
            OpengrepSandboxKind::DockerfileContainer
        );

        let unknown_options = extract_opengrep_task_options(&json!({
            "opengrep_sandbox": "surprise",
        }));
        assert_eq!(
            unknown_options.sandbox,
            OpengrepSandboxKind::DockerfileContainer
        );
    }

    #[test]
    fn opengrep_resource_scheduler_allocates_half_of_remaining_cores() {
        let scheduler = OpengrepResourceScheduler::new(8);

        let first = scheduler.acquire_for_project("project-a", None);
        assert_eq!(first.allocated_cores, 4);
        assert_eq!(first.total_cores, 8);

        let second = scheduler.acquire_for_project("project-b", None);
        assert_eq!(second.allocated_cores, 2);
        assert_eq!(second.total_cores, 8);
    }

    #[test]
    fn opengrep_resource_scheduler_queues_when_less_than_two_cores_would_remain() {
        let scheduler = OpengrepResourceScheduler::new(8);
        let first = scheduler.acquire_for_project("project-a", None);
        let second = scheduler.acquire_for_project("project-b", None);

        let (sender, receiver) = mpsc::channel();
        let queued_scheduler = scheduler.clone();
        let queued = std::thread::spawn(move || {
            let permit = queued_scheduler.acquire_for_project("project-c", None);
            sender
                .send(permit.allocated_cores)
                .expect("send queued allocation");
            permit
        });

        assert!(
            receiver.recv_timeout(Duration::from_millis(100)).is_err(),
            "third launch should queue while only 2 cores remain"
        );

        drop(second);
        assert_eq!(
            receiver
                .recv_timeout(Duration::from_secs(1))
                .expect("queued launch should start after resources are released"),
            2
        );

        drop(first);
        drop(queued.join().expect("queued scheduler thread"));
    }

    #[test]
    fn opengrep_resource_scheduler_queues_same_project_scans() {
        let scheduler = OpengrepResourceScheduler::new(8);
        let first = scheduler.acquire_for_project("project-a", None);

        let (sender, receiver) = mpsc::channel();
        let queued_scheduler = scheduler.clone();
        let queued = std::thread::spawn(move || {
            let permit = queued_scheduler.acquire_for_project("project-a", None);
            sender
                .send(permit.allocated_cores)
                .expect("send queued allocation");
            permit
        });

        assert!(
            receiver.recv_timeout(Duration::from_millis(100)).is_err(),
            "same-project opengrep scan should wait for the active project container"
        );

        drop(first);
        assert_eq!(
            receiver
                .recv_timeout(Duration::from_secs(1))
                .expect("same-project launch should start after project slot is released"),
            4
        );

        drop(queued.join().expect("queued scheduler thread"));
    }

    #[test]
    fn opengrep_resource_scheduler_allows_different_project_scans() {
        let scheduler = OpengrepResourceScheduler::new(8);
        let first = scheduler.acquire_for_project("project-a", None);
        let second = scheduler.acquire_for_project("project-b", None);

        assert_eq!(first.allocated_cores, 4);
        assert_eq!(second.allocated_cores, 2);
    }

    #[test]
    fn opengrep_resource_scheduler_allows_first_scan_on_small_hosts() {
        let scheduler = OpengrepResourceScheduler::new(2);
        let permit = scheduler.acquire_for_project("project-a", None);

        assert_eq!(permit.allocated_cores, 1);
        assert_eq!(permit.total_cores, 2);
    }

    #[test]
    fn opengrep_runner_resources_default_to_dynamic_allocation() {
        let mut config = AppConfig::for_tests();
        config.opengrep_scan_jobs = 0;
        config.opengrep_scan_jobs_explicit = false;
        config.opengrep_runner_cpu_limit = 0.0;
        config.opengrep_runner_cpu_limit_explicit = false;

        let scheduler = OpengrepResourceScheduler::new(8);
        let permit = scheduler
            .acquire_for_project("project-a", super::requested_opengrep_cpu_cores(&config));
        let resources = super::resolve_opengrep_runner_resources(&config, &permit);

        assert_eq!(resources.jobs, 4);
        assert_eq!(resources.cpu_limit, 4.0);
        assert_eq!(resources.allocated_cores, 4);
    }

    #[test]
    fn opengrep_runner_resources_preserve_explicit_overrides() {
        let mut config = AppConfig::for_tests();
        config.opengrep_scan_jobs = 6;
        config.opengrep_scan_jobs_explicit = true;
        config.opengrep_runner_cpu_limit = 3.5;
        config.opengrep_runner_cpu_limit_explicit = true;

        let scheduler = OpengrepResourceScheduler::new(8);
        let permit = scheduler
            .acquire_for_project("project-a", super::requested_opengrep_cpu_cores(&config));
        let resources = super::resolve_opengrep_runner_resources(&config, &permit);

        assert_eq!(resources.jobs, 6);
        assert_eq!(resources.cpu_limit, 3.5);
        assert_eq!(resources.allocated_cores, 4);
    }

    #[test]
    fn opengrep_a3s_box_runner_spec_uses_absolute_workspace_paths() {
        let config = AppConfig::for_tests();
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let workspace_dir = temp_dir.path();
        let resources = OpengrepRunnerResources {
            jobs: 3,
            cpu_limit: 2.0,
            allocated_cores: 2,
            total_cores: 8,
        };

        let spec = build_opengrep_a3s_box_runner_spec(
            &config,
            "argus/opengrep-runner:test".to_string(),
            workspace_dir,
            resources,
            Some("task-123"),
            OpengrepRunnerPaths {
                container_source_dir: "/tmp/workspace/source",
                manifest_container_path: Some("/tmp/workspace/image-rules.manifest"),
                config_container_path: Some("/tmp/workspace/opengrep-rules"),
                output_container_path: "/tmp/workspace/output/results.json",
                summary_rel_path: "output/summary.json",
                summary_container_path: "/tmp/workspace/output/summary.json",
                log_container_path: "/tmp/workspace/output/opengrep.log",
                stdout_rel_path: "output/stdout.txt",
                stderr_rel_path: "output/stderr.txt",
            },
        );

        assert_eq!(spec.scanner_type, "opengrep");
        assert_eq!(spec.image, "argus/opengrep-runner:test");
        assert_eq!(spec.expected_exit_codes, vec![0, 1]);
        assert_eq!(
            spec.capture_stdout_path.as_deref(),
            Some("output/stdout.txt")
        );
        assert_eq!(
            spec.capture_stderr_path.as_deref(),
            Some("output/stderr.txt")
        );
        assert!(spec.command.contains(&"--target".to_string()));
        assert!(spec.command.contains(&"/tmp/workspace/source".to_string()));
        assert!(spec.command.contains(&"--config".to_string()));
        assert!(spec.command.contains(&"--manifest".to_string()));
        assert!(spec
            .command
            .contains(&"/tmp/workspace/image-rules.manifest".to_string()));
        assert!(spec
            .command
            .contains(&"/tmp/workspace/opengrep-rules".to_string()));
        assert!(spec
            .command
            .contains(&"/tmp/workspace/output/results.json".to_string()));
        assert_eq!(
            spec.memory_limit_mb,
            Some(config.opengrep_runner_memory_limit_mb)
        );
        assert_eq!(spec.cpu_limit, Some(2.0));
        assert_eq!(spec.pids_limit, None);
        assert!(spec.network_disabled);
        assert_eq!(spec.task_id.as_deref(), Some("task-123"));
    }

    #[tokio::test]
    async fn read_opengrep_results_text_errors_when_result_file_is_missing() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let missing_path = temp_dir.path().join("missing-results.json");

        let error = read_opengrep_results_text(&missing_path, 1024 * 1024)
            .await
            .expect_err("missing results should error");

        assert!(error.contains("missing opengrep results output"), "{error}");
    }

    #[tokio::test]
    async fn read_opengrep_results_text_prefers_output_file_contents() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let results_path = temp_dir.path().join("results.json");
        tokio::fs::write(&results_path, "{\"results\":[{\"check_id\":\"demo\"}]}")
            .await
            .expect("write results");

        let text = read_opengrep_results_text(&results_path, 1024 * 1024)
            .await
            .expect("results file should be read");

        assert!(text.contains("\"check_id\":\"demo\""), "{text}");
    }

    #[tokio::test]
    async fn read_opengrep_results_text_rejects_oversize() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let results_path = temp_dir.path().join("results.json");
        tokio::fs::write(&results_path, vec![0u8; 1024])
            .await
            .expect("write oversize file");

        let error = read_opengrep_results_text(&results_path, 512)
            .await
            .expect_err("oversize file should error");

        assert!(
            error.contains("exceeds OPENGREP_RESULTS_JSON_LIMIT_BYTES"),
            "{error}"
        );
    }

    #[tokio::test]
    async fn format_opengrep_runner_error_includes_scanner_log_excerpt() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let log_path = temp_dir.path().join("opengrep.log");
        tokio::fs::write(
            &log_path,
            "SIGPIPE signal intercepted\nException: Common.UnixExit(-141)\n",
        )
        .await
        .expect("write log");

        let error = format_opengrep_runner_error(
            &crate::runtime::runner::RunnerResult {
                success: false,
                container_id: Some("container-xyz".to_string()),
                exit_code: 0,
                stdout_path: None,
                stderr_path: None,
                error: Some("scanner completion summary was not observed".to_string()),
            },
            Some(&log_path),
        )
        .await;

        assert!(
            error.contains("completion summary was not observed"),
            "{error}"
        );
        assert!(error.contains("SIGPIPE signal intercepted"), "{error}");
        assert!(error.contains("Common.UnixExit(-141)"), "{error}");
    }

    mod gate_tests {
        use crate::routes::static_tasks::{
            cpp_project_threshold, cpp_project_threshold_from, is_cpp_project, ProjectGateFailure,
        };
        use crate::state::StoredProject;
        use std::sync::{LazyLock, Mutex};

        static ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

        struct EnvGuard {
            previous: Option<String>,
        }
        impl EnvGuard {
            fn set(value: &str) -> Self {
                let previous = std::env::var("ARGUS_CPP_PROJECT_THRESHOLD").ok();
                std::env::set_var("ARGUS_CPP_PROJECT_THRESHOLD", value);
                Self { previous }
            }
            fn unset() -> Self {
                let previous = std::env::var("ARGUS_CPP_PROJECT_THRESHOLD").ok();
                std::env::remove_var("ARGUS_CPP_PROJECT_THRESHOLD");
                Self { previous }
            }
        }
        impl Drop for EnvGuard {
            fn drop(&mut self) {
                if let Some(v) = &self.previous {
                    std::env::set_var("ARGUS_CPP_PROJECT_THRESHOLD", v);
                } else {
                    std::env::remove_var("ARGUS_CPP_PROJECT_THRESHOLD");
                }
            }
        }

        fn project(
            info_status: &str,
            programming_languages_json: &str,
            language_info: &str,
        ) -> StoredProject {
            StoredProject {
                id: "p1".into(),
                name: "p".into(),
                description: String::new(),
                source_type: "upload".into(),
                repository_type: String::new(),
                default_branch: String::new(),
                programming_languages_json: programming_languages_json.into(),
                is_active: true,
                created_at: "2026-05-28T00:00:00Z".into(),
                updated_at: "2026-05-28T00:00:00Z".into(),
                language_info: language_info.into(),
                info_status: info_status.into(),
                archive: None,
            }
        }

        #[test]
        fn cpp_project_threshold_from_none() {
            assert_eq!(cpp_project_threshold_from(None), 0.5);
        }
        #[test]
        fn cpp_project_threshold_from_empty() {
            assert_eq!(cpp_project_threshold_from(Some("")), 0.5);
        }
        #[test]
        fn cpp_project_threshold_from_whitespace() {
            assert_eq!(cpp_project_threshold_from(Some("   ")), 0.5);
        }
        #[test]
        fn cpp_project_threshold_from_valid_07() {
            assert_eq!(cpp_project_threshold_from(Some("0.7")), 0.7);
        }
        #[test]
        fn cpp_project_threshold_from_zero() {
            assert_eq!(cpp_project_threshold_from(Some("0.0")), 0.0);
        }
        #[test]
        fn cpp_project_threshold_from_one() {
            assert_eq!(cpp_project_threshold_from(Some("1.0")), 1.0);
        }
        #[test]
        fn cpp_project_threshold_from_garbage() {
            assert_eq!(cpp_project_threshold_from(Some("abc")), 0.5);
        }
        #[test]
        fn cpp_project_threshold_from_negative() {
            assert_eq!(cpp_project_threshold_from(Some("-0.1")), 0.5);
        }
        #[test]
        fn cpp_project_threshold_from_too_large() {
            assert_eq!(cpp_project_threshold_from(Some("1.5")), 0.5);
        }
        #[test]
        fn cpp_project_threshold_env_unset_default() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            assert_eq!(cpp_project_threshold(), 0.5);
        }

        #[test]
        fn is_cpp_project_pending_status() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project("pending", "[\"C\"]", "{\"languages\":{\"C\":{\"proportion\":0.9}}}");
            assert_eq!(
                is_cpp_project(&p),
                Err(ProjectGateFailure::LanguageDetectionPending)
            );
        }
        #[test]
        fn is_cpp_project_empty_programming_languages() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project("completed", "[]", "{\"languages\":{\"C\":{\"proportion\":0.9}}}");
            assert_eq!(
                is_cpp_project(&p),
                Err(ProjectGateFailure::LanguageDetectionPending)
            );
        }
        #[test]
        fn is_cpp_project_empty_language_info_object() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project("completed", "[\"C\"]", "{}");
            assert_eq!(
                is_cpp_project(&p),
                Err(ProjectGateFailure::LanguageDetectionPending)
            );
        }
        #[test]
        fn is_cpp_project_c_majority_passes_default_threshold() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project(
                "completed",
                "[\"C\",\"Python\"]",
                "{\"languages\":{\"C\":{\"proportion\":0.6},\"Python\":{\"proportion\":0.4}}}",
            );
            assert_eq!(is_cpp_project(&p), Ok(()));
        }
        #[test]
        fn is_cpp_project_below_threshold_fails() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project(
                "completed",
                "[\"Python\",\"C\",\"C++\"]",
                "{\"languages\":{\"C\":{\"proportion\":0.2},\"C++\":{\"proportion\":0.1},\"Python\":{\"proportion\":0.7}}}",
            );
            assert_eq!(is_cpp_project(&p), Err(ProjectGateFailure::NotCppProject));
        }
        #[test]
        fn is_cpp_project_c_plus_cpp_sum_passes() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::unset();
            let p = project(
                "completed",
                "[\"C\",\"C++\",\"Rust\"]",
                "{\"languages\":{\"C\":{\"proportion\":0.3},\"C++\":{\"proportion\":0.3},\"Rust\":{\"proportion\":0.4}}}",
            );
            assert_eq!(is_cpp_project(&p), Ok(()));
        }
        #[test]
        fn is_cpp_project_env_threshold_07_fails_at_06() {
            let _lock = ENV_LOCK.lock().unwrap();
            let _g = EnvGuard::set("0.7");
            let p = project(
                "completed",
                "[\"C\"]",
                "{\"languages\":{\"C\":{\"proportion\":0.6},\"C++\":{\"proportion\":0.0}}}",
            );
            assert_eq!(is_cpp_project(&p), Err(ProjectGateFailure::NotCppProject));
        }
    }
}
