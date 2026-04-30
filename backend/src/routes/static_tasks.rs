use std::{
    collections::{BTreeMap, BTreeSet, HashSet},
    env,
    num::NonZeroUsize,
    path::{Path, PathBuf},
    sync::{Arc, Condvar, LazyLock, Mutex},
};

use axum::{
    extract::{Multipart, Path as AxumPath, Query, State},
    routing::{get, post},
    Json, Router,
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
    db::{projects, system_config, task_state},
    error::ApiError,
    llm_rule,
    runtime::runner::{self, RunnerSpec},
    scan::{codeql, opengrep, scope_filters},
    state::AppState,
};

static OPENGREP_RESOURCE_SCHEDULER: LazyLock<OpengrepResourceScheduler> =
    LazyLock::new(OpengrepResourceScheduler::from_environment);

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
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let engine = optional_string(&payload, "engine").unwrap_or_else(|| "opengrep".to_string());
    if engine.eq_ignore_ascii_case("codeql") {
        return create_static_task_for_engine(state, payload, "codeql").await;
    }
    create_static_task_for_engine(state, payload, "opengrep").await
}

async fn create_codeql_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    create_static_task_for_engine(state, payload, "codeql").await
}

async fn create_static_task_for_engine(
    state: AppState,
    payload: Value,
    engine: &str,
) -> Result<Json<Value>, ApiError> {
    let project_id = required_string(&payload, "project_id")?;

    let now = now_rfc3339();
    let task_id = Uuid::new_v4().to_string();
    let target_path = optional_string(&payload, "target_path").unwrap_or_else(|| ".".to_string());
    let rule_ids = payload
        .get("rule_ids")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    let mut record = task_state::StaticTaskRecord {
        id: task_id.clone(),
        engine: engine.to_string(),
        project_id: project_id.clone(),
        name: optional_string(&payload, "name").unwrap_or_else(|| format!("{engine}-task")),
        status: "running".to_string(),
        target_path: target_path.clone(),
        total_findings: 0,
        scan_duration_ms: 0,
        files_scanned: 0,
        error_message: None,
        created_at: now.clone(),
        updated_at: Some(now.clone()),
        extra: json!({
            "engine": engine,
            "error_count": 0,
            "warning_count": 0,
            "high_confidence_count": 0,
            "lines_scanned": 0,
            "first_version_complete": false,
        }),
        progress: task_state::StaticTaskProgressRecord {
            progress: 0.0,
            current_stage: Some("initializing".to_string()),
            message: Some(format!("preparing {engine} scan")),
            started_at: Some(now.clone()),
            updated_at: Some(now.clone()),
            logs: vec![task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: "initializing".to_string(),
                message: format!("{engine} scan task created"),
                progress: 0.0,
                level: "info".to_string(),
            }],
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

    let _guard = state.file_store_lock.lock().await;
    let project = projects::get_project_while_locked(&state, &project_id)
        .await
        .map_err(internal_error)?;
    let Some(project) = project else {
        return Err(ApiError::NotFound(format!(
            "project not found: {project_id}"
        )));
    };
    if let Some(extra) = record.extra.as_object_mut() {
        extra.insert(
            "project_name".to_string(),
            Value::String(project.name.clone()),
        );
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
    let engine_for_task = engine.to_string();
    tokio::spawn(async move {
        if engine_for_task == "codeql" {
            run_codeql_scan(bg_state, bg_task_id, project_id, target_path, rule_ids).await;
        } else {
            run_opengrep_scan(bg_state, bg_task_id, project_id, target_path, rule_ids).await;
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
    interrupt_static_task(&state, "opengrep", &task_id).await
}

async fn list_codeql_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "codeql", query).await
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
    interrupt_static_task(&state, "codeql", &task_id).await
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
) {
    let started_at = std::time::Instant::now();
    if let Err(error) = run_opengrep_scan_inner(&state, &task_id, &project_id, &rule_ids).await {
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
) {
    let started_at = std::time::Instant::now();
    if let Err(error) = run_codeql_scan_inner(&state, &task_id, &project_id, &target_path).await {
        let elapsed_ms = started_at.elapsed().as_millis() as i64;
        let _ = update_scan_task_failed(&state, &task_id, &error.to_string(), elapsed_ms).await;
    }
}

async fn run_codeql_scan_inner(
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
        "extracting",
        "locating project archive for CodeQL",
    )
    .await;
    let (archive_path, archive_name) = resolve_project_archive_input(state, project_id).await?;

    let workspace_root = scan_workspace_root();
    let workspace_dir = workspace_root
        .join("codeql-runtime")
        .join(Uuid::new_v4().to_string());
    let source_dir = workspace_dir.join("source");
    let output_dir = workspace_dir.join("output");
    let build_plan_dir = workspace_dir.join("build-plan");
    tokio::fs::create_dir_all(&source_dir).await?;
    tokio::fs::create_dir_all(&output_dir).await?;
    tokio::fs::create_dir_all(&build_plan_dir).await?;

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
    let known_paths = collect_relative_paths_from_directory(&source_dir)?;
    let files_scanned = known_paths.len();

    update_scan_progress(
        state,
        task_id,
        25.0,
        "preparing_queries",
        "materializing CodeQL query assets",
    )
    .await;
    let project_languages = match projects::get_project(state, project_id).await {
        Ok(Some(project)) => {
            serde_json::from_str::<Vec<String>>(&project.programming_languages_json)
                .unwrap_or_default()
        }
        _ => Vec::new(),
    };
    let codeql_languages = normalize_codeql_task_languages(&project_languages);
    let primary_language = codeql_languages
        .first()
        .cloned()
        .unwrap_or_else(|| "javascript-typescript".to_string());
    let Some(query_dir) =
        codeql::materialize_query_directory_for_languages(state, &workspace_dir, &codeql_languages)
            .await?
    else {
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Err("no CodeQL query assets available for scan".into());
    };

    let query_container_path = workspace_container_path(&workspace_dir, &query_dir)?;
    let sarif_rel_path = format!("output/results-{}.sarif", Uuid::new_v4());
    let summary_rel_path = format!("output/summary-{}.json", Uuid::new_v4());
    let events_rel_path = format!("output/events-{}.jsonl", Uuid::new_v4());
    let stdout_rel_path = format!("output/stdout-{}.txt", Uuid::new_v4());
    let stderr_rel_path = format!("output/stderr-{}.txt", Uuid::new_v4());
    let build_plan_rel_path = "build-plan/build-plan.json".to_string();

    let seed_plan = json!({
        "language": primary_language,
        "build_mode": default_codeql_build_mode(&primary_language),
        "commands": [],
        "working_directory": ".",
        "allow_network": state.config.codeql_allow_network_during_build,
        "max_inference_rounds": state.config.codeql_max_build_inference_rounds,
        "llm_allow_source_snippets": state.config.codeql_llm_allow_source_snippets,
        "status": "candidate"
    });
    tokio::fs::write(
        workspace_dir.join(&build_plan_rel_path),
        serde_json::to_vec_pretty(&seed_plan)?,
    )
    .await?;

    update_scan_progress(
        state,
        task_id,
        40.0,
        "database_create",
        "running CodeQL database create/analyze runner",
    )
    .await;
    let spec = build_codeql_runner_spec(
        &state.config,
        &workspace_dir,
        CodeqlRunnerPaths {
            container_source_dir: "/scan/source",
            query_container_path: &query_container_path,
            database_container_path: "/scan/output/codeql-db",
            sarif_container_path: &format!("/scan/{sarif_rel_path}"),
            summary_rel_path: &summary_rel_path,
            summary_container_path: &format!("/scan/{summary_rel_path}"),
            events_container_path: &format!("/scan/{events_rel_path}"),
            build_plan_container_path: &format!("/scan/{build_plan_rel_path}"),
            stdout_rel_path: &stdout_rel_path,
            stderr_rel_path: &stderr_rel_path,
            language: &primary_language,
        },
    );

    let runner_result = tokio::task::spawn_blocking(move || runner::execute(spec)).await?;
    record_codeql_events(state, task_id, &workspace_dir.join(&events_rel_path)).await;
    if !runner_result.success {
        let error_msg =
            format_codeql_runner_error(&runner_result, Some(&workspace_dir.join(&events_rel_path)))
                .await;
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Err(format!("CodeQL scan failed: {error_msg}").into());
    }

    update_scan_progress(
        state,
        task_id,
        75.0,
        "parsing_sarif",
        "parsing CodeQL SARIF results",
    )
    .await;
    let sarif_path = workspace_dir.join(&sarif_rel_path);
    let sarif_text = tokio::fs::read_to_string(&sarif_path)
        .await
        .map_err(|error| format!("missing CodeQL SARIF output: {error}"))?;
    let findings = codeql::parse_sarif_output(
        &sarif_text,
        task_id,
        source_dir.to_str(),
        Some(&known_paths),
    );

    update_scan_progress(state, task_id, 90.0, "finalizing", "saving CodeQL findings").await;
    let elapsed_ms = started_at.elapsed().as_millis() as i64;
    let now = now_rfc3339();
    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
        record.status = "completed".to_string();
        record.total_findings = findings.len() as i64;
        record.scan_duration_ms = elapsed_ms;
        record.files_scanned = files_scanned as i64;
        record.updated_at = Some(now.clone());
        record.extra = json!({
            "engine": "codeql",
            "language": primary_language,
            "languages": codeql_languages,
            "files_extracted": files_extracted,
            "lines_scanned": 0,
            "build_plan_source": "workspace_seed_pending_db_verification",
            "first_version_complete": false,
        });
        let mut logs = record.progress.logs.clone();
        logs.push(task_state::StaticTaskProgressLogRecord {
            timestamp: now.clone(),
            stage: "completed".to_string(),
            message: format!(
                "CodeQL scan completed: {} findings, {} files scanned",
                findings.len(),
                files_scanned
            ),
            progress: 100.0,
            level: "info".to_string(),
        });
        record.progress = task_state::StaticTaskProgressRecord {
            progress: 100.0,
            current_stage: Some("completed".to_string()),
            message: Some(format!(
                "CodeQL scan completed: {} findings in {}ms",
                findings.len(),
                elapsed_ms
            )),
            started_at: record.progress.started_at.clone(),
            updated_at: Some(now),
            logs,
        };
        record.findings = findings;
    }
    task_state::save_snapshot(state, &snapshot).await?;
    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
    Ok(())
}

async fn run_opengrep_scan_inner(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    rule_ids: &[String],
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
            prune_static_scan_test_and_fuzz_paths(&source_dir_for_prune)
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
            &format!("excluded {files_excluded} test/fuzz files from opengrep scan input"),
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

    let scanner_image = state.config.scanner_opengrep_image.clone();
    let container_source_dir = "/scan/source";

    let known_paths = scan_input_paths;
    let config_container_path = rule_inputs
        .workspace_rules_dir
        .as_ref()
        .map(|path| workspace_container_path(&workspace_dir, path))
        .transpose()?;
    let output_rel_path = format!("output/results-{}.json", Uuid::new_v4());
    let summary_rel_path = format!("output/summary-{}.json", Uuid::new_v4());
    let log_rel_path = format!("output/log-{}.txt", Uuid::new_v4());
    let stdout_rel_path = format!("output/stdout-{}.txt", Uuid::new_v4());
    let stderr_rel_path = format!("output/stderr-{}.txt", Uuid::new_v4());
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
        let error_msg =
            format_opengrep_runner_error(&runner_result, Some(&workspace_dir.join(&log_rel_path)))
                .await;
        let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
        return Err(format!("opengrep scan failed: {error_msg}").into());
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
    let json_text = read_opengrep_results_text(&results_path)
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
            "error_count": error_count,
            "warning_count": warning_count,
            "high_confidence_count": high_confidence_count,
            "lines_scanned": 0,
            "files_extracted": files_extracted,
            "files_excluded": files_excluded,
        });
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
        };
        record.findings = findings;
    }

    let _ = task_state::save_snapshot(state, &snapshot).await;
    let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
    Ok(())
}

struct CodeqlRunnerPaths<'a> {
    container_source_dir: &'a str,
    query_container_path: &'a str,
    database_container_path: &'a str,
    sarif_container_path: &'a str,
    summary_rel_path: &'a str,
    summary_container_path: &'a str,
    events_container_path: &'a str,
    build_plan_container_path: &'a str,
    stdout_rel_path: &'a str,
    stderr_rel_path: &'a str,
    language: &'a str,
}

fn build_codeql_runner_spec(
    config: &crate::config::AppConfig,
    workspace_dir: &std::path::Path,
    paths: CodeqlRunnerPaths<'_>,
) -> RunnerSpec {
    let cpu_limit = if config.codeql_runner_cpu_limit > 0.0 {
        Some(config.codeql_runner_cpu_limit)
    } else {
        None
    };
    RunnerSpec {
        scanner_type: "codeql".to_string(),
        image: config.scanner_codeql_image.clone(),
        workspace_dir: workspace_dir.display().to_string(),
        command: codeql::build_scan_command(&codeql::ScanCommandArgs {
            source_dir: paths.container_source_dir,
            queries_dir: paths.query_container_path,
            database_dir: paths.database_container_path,
            sarif_path: paths.sarif_container_path,
            summary_path: paths.summary_container_path,
            events_path: paths.events_container_path,
            build_plan_path: Some(paths.build_plan_container_path),
            language: paths.language,
            threads: config.codeql_threads,
            ram_mb: config.codeql_ram_mb,
            allow_network: config.codeql_allow_network_during_build,
        }),
        timeout_seconds: config.codeql_scan_timeout_seconds,
        env: BTreeMap::new(),
        expected_exit_codes: vec![0],
        artifact_paths: Vec::new(),
        capture_stdout_path: Some(paths.stdout_rel_path.to_string()),
        capture_stderr_path: Some(paths.stderr_rel_path.to_string()),
        completion_summary_path: Some(paths.summary_rel_path.to_string()),
        workspace_root_override: None,
        memory_limit_mb: Some(config.codeql_runner_memory_limit_mb),
        memory_swap_limit_mb: Some(config.codeql_runner_memory_limit_mb),
        cpu_limit,
        pids_limit: Some(1024),
    }
}

fn normalize_codeql_task_languages(project_languages: &[String]) -> Vec<String> {
    let mut languages = project_languages
        .iter()
        .map(|language| codeql::normalize_language(language))
        .filter(|language| {
            matches!(
                language.as_str(),
                "javascript-typescript" | "python" | "java" | "cpp" | "go"
            )
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    if languages.is_empty() {
        languages.push("javascript-typescript".to_string());
    }
    languages
}

fn default_codeql_build_mode(language: &str) -> &'static str {
    match codeql::normalize_language(language).as_str() {
        "javascript-typescript" | "python" => "none",
        _ => "autobuild",
    }
}

async fn record_codeql_events(state: &AppState, task_id: &str, events_path: &std::path::Path) {
    let Ok(events_text) = tokio::fs::read_to_string(events_path).await else {
        return;
    };
    for line in events_text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .take(200)
    {
        let event =
            serde_json::from_str::<Value>(line).unwrap_or_else(|_| json!({ "message": line }));
        let stage = event
            .get("stage")
            .and_then(Value::as_str)
            .unwrap_or("codeql_event");
        let message = event
            .get("message")
            .and_then(Value::as_str)
            .or_else(|| event.get("event").and_then(Value::as_str))
            .unwrap_or("CodeQL runner event");
        update_scan_progress(state, task_id, 55.0, stage, message).await;
    }
}

async fn format_codeql_runner_error(
    result: &runner::RunnerResult,
    events_path: Option<&std::path::Path>,
) -> String {
    let mut parts = vec![result
        .error
        .clone()
        .unwrap_or_else(|| format!("CodeQL runner exited with code {}", result.exit_code))];
    if let Some(stdout_excerpt) = read_runner_output_excerpt(result.stdout_path.as_deref()).await {
        parts.push(format!("stdout={stdout_excerpt}"));
    }
    if let Some(stderr_excerpt) = read_runner_output_excerpt(result.stderr_path.as_deref()).await {
        parts.push(format!("stderr={stderr_excerpt}"));
    }
    if let Some(events_excerpt) = read_text_excerpt(events_path).await {
        parts.push(format!("events={events_excerpt}"));
    }
    parts.join("; ")
}

async fn read_opengrep_results_text(results_path: &std::path::Path) -> Result<String, String> {
    tokio::fs::read_to_string(results_path)
        .await
        .map_err(|results_error| {
            format!("missing opengrep results output: results_error={results_error}")
        })
}

fn prune_static_scan_test_and_fuzz_paths(
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
        if scope_filters::is_static_scan_test_or_fuzz_path(&relative) {
            std::fs::remove_file(&file_path)?;
            removed += 1;
        }
    }

    Ok(removed)
}

struct OpengrepRunnerPaths<'a> {
    container_source_dir: &'a str,
    config_container_path: Option<&'a str>,
    output_container_path: &'a str,
    summary_rel_path: &'a str,
    summary_container_path: &'a str,
    log_container_path: &'a str,
    stdout_rel_path: &'a str,
    stderr_rel_path: &'a str,
}

fn build_opengrep_runner_spec(
    config: &crate::config::AppConfig,
    image: String,
    workspace_dir: &std::path::Path,
    resources: OpengrepRunnerResources,
    paths: OpengrepRunnerPaths<'_>,
) -> RunnerSpec {
    RunnerSpec {
        scanner_type: "opengrep".to_string(),
        image,
        workspace_dir: workspace_dir.display().to_string(),
        command: opengrep::build_scan_command(&opengrep::ScanCommandArgs {
            manifest_path: None,
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
        completion_summary_path: Some(paths.summary_rel_path.to_string()),
        workspace_root_override: None,
        memory_limit_mb: Some(config.opengrep_runner_memory_limit_mb),
        memory_swap_limit_mb: Some(config.opengrep_runner_memory_limit_mb),
        cpu_limit: Some(resources.cpu_limit),
        pids_limit: Some(config.opengrep_runner_pids_limit),
    }
}

#[derive(Clone, Debug)]
struct OpengrepRunnerInputs {
    workspace_rules_dir: Option<PathBuf>,
}

async fn prepare_opengrep_runner_inputs(
    state: &AppState,
    workspace_dir: &std::path::Path,
    rule_ids: &[String],
    project_languages: &[String],
) -> Result<Option<OpengrepRunnerInputs>, Box<dyn std::error::Error + Send + Sync>> {
    let image_rule_assets = selected_image_rule_assets(state, rule_ids, project_languages).await?;
    let image_rule_count = image_rule_assets.len();
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

async fn update_scan_task_failed(
    state: &AppState,
    task_id: &str,
    error_message: &str,
    elapsed_ms: i64,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let now = now_rfc3339();
    let mut snapshot = task_state::load_snapshot(state).await?;
    if let Some(record) = snapshot.static_tasks.get_mut(task_id) {
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
    Ok(Json(
        items
            .into_iter()
            .skip(query.skip.unwrap_or(0))
            .take(query.limit.unwrap_or(1_000))
            .map(|record| static_task_value(&record))
            .collect(),
    ))
}

async fn get_static_task(
    state: &AppState,
    engine: &str,
    task_id: &str,
) -> Result<Json<Value>, ApiError> {
    let record = find_static_task(state, engine, task_id).await?;
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
    merge_json_object(&mut value, &record.extra);
    merge_json_object(
        &mut value,
        &json!({
        "id": record.id,
        "engine": record.engine,
        "project_id": record.project_id,
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

    let mut rule_summary: BTreeMap<String, (usize, BTreeMap<String, usize>, Vec<String>)> =
        BTreeMap::new();
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
        "kimi_compatible" | "pi_compatible" => {
            return Err(ApiError::Internal(
                "kimi/pi 协议仅支持 CLI 模式，不支持通过 HTTP 静态任务路径调用。".to_string(),
            ));
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
        "kimi_compatible" | "pi_compatible" => {
            return Err(ApiError::Internal(
                "kimi/pi 协议仅支持 CLI 模式，不支持通过 HTTP 静态任务路径调用。".to_string(),
            ));
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

        let parsed: Value = (|| {
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
        })()
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

    use super::{
        build_opengrep_runner_spec, extract_highest_rule_severity, format_opengrep_runner_error,
        read_opengrep_results_text, static_task_value, OpengrepResourceScheduler,
        OpengrepRunnerPaths, OpengrepRunnerResources,
    };
    use serde_json::json;
    use std::{sync::mpsc, time::Duration};

    fn static_task_record_with_findings(
        findings: Vec<task_state::StaticFindingRecord>,
    ) -> task_state::StaticTaskRecord {
        task_state::StaticTaskRecord {
            id: "task-1".to_string(),
            engine: "opengrep".to_string(),
            project_id: "project-1".to_string(),
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

    #[tokio::test]
    async fn read_opengrep_results_text_errors_when_result_file_is_missing() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let missing_path = temp_dir.path().join("missing-results.json");

        let error = read_opengrep_results_text(&missing_path)
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

        let text = read_opengrep_results_text(&results_path)
            .await
            .expect("results file should be read");

        assert!(text.contains("\"check_id\":\"demo\""), "{text}");
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
}
