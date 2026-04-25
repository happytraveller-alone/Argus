use std::collections::BTreeMap;
use std::io::{Cursor, Read as IoRead};
use std::path::PathBuf;

use axum::{
    extract::{Multipart, Path as AxumPath, Query, State},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;
use zip::ZipArchive;

use crate::{
    db::{projects, task_state},
    error::ApiError,
    llm_rule,
    runtime::runner::{self, RunnerSpec},
    scan::opengrep,
    state::AppState,
};

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
        .route(
            "/tasks",
            get(list_opengrep_tasks).post(create_opengrep_task),
        )
        .route(
            "/tasks/{task_id}",
            get(get_opengrep_task).delete(delete_opengrep_task),
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

async fn create_opengrep_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
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

    let record = task_state::StaticTaskRecord {
        id: task_id.clone(),
        engine: "opengrep".to_string(),
        project_id: project_id.clone(),
        name: optional_string(&payload, "name").unwrap_or_else(|| "opengrep-task".to_string()),
        status: "running".to_string(),
        target_path: target_path.clone(),
        total_findings: 0,
        scan_duration_ms: 0,
        files_scanned: 0,
        error_message: None,
        created_at: now.clone(),
        updated_at: Some(now.clone()),
        extra: json!({
            "error_count": 0,
            "warning_count": 0,
            "high_confidence_count": 0,
            "lines_scanned": 0,
        }),
        progress: task_state::StaticTaskProgressRecord {
            progress: 0.0,
            current_stage: Some("initializing".to_string()),
            message: Some("preparing opengrep scan".to_string()),
            started_at: Some(now.clone()),
            updated_at: Some(now.clone()),
            logs: vec![task_state::StaticTaskProgressLogRecord {
                timestamp: now,
                stage: "initializing".to_string(),
                message: "opengrep scan task created".to_string(),
                progress: 0.0,
                level: "info".to_string(),
            }],
        },
        findings: Vec::new(),
    };

    let _guard = state.file_store_lock.lock().await;
    let project = projects::get_project_while_locked(&state, &project_id)
        .await
        .map_err(internal_error)?;
    if project.is_none() {
        return Err(ApiError::NotFound(format!(
            "project not found: {project_id}"
        )));
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
        run_opengrep_scan(bg_state, bg_task_id, project_id, target_path, rule_ids).await;
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

async fn get_opengrep_progress(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
    Query(query): Query<ProgressQuery>,
) -> Result<Json<Value>, ApiError> {
    let record = find_static_task(&state, "opengrep", &task_id).await?;
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
    let task = find_static_task(&state, "opengrep", &task_id).await?;
    let finding = get_static_finding_value(&state, "opengrep", &task_id, &finding_id).await?;

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

    let zip_path = state
        .config
        .zip_storage_path
        .join(format!("{}.zip", task.project_id));

    let file_path_owned = file_path.to_string();
    let lines_result = tokio::task::spawn_blocking(move || {
        read_file_lines_from_zip(&zip_path, &file_path_owned, range_start, range_end)
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

async fn run_opengrep_scan_inner(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    rule_ids: &[String],
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let started_at = std::time::Instant::now();

    update_scan_progress(state, task_id, 5.0, "preparing", "locating project archive").await;

    let zip_path = state
        .config
        .zip_storage_path
        .join(format!("{project_id}.zip"));
    if !zip_path.exists() {
        return Err(format!("project archive not found: {}", zip_path.display()).into());
    }

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

    let zip_bytes = tokio::fs::read(&zip_path).await?;
    let source_dir_clone = source_dir.clone();
    let files_extracted = tokio::task::spawn_blocking(
        move || -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
            let reader = Cursor::new(zip_bytes);
            let mut archive = ZipArchive::new(reader)?;
            let mut count = 0usize;
            for i in 0..archive.len() {
                let mut entry = archive.by_index(i)?;
                if entry.is_dir() {
                    continue;
                }
                let name = entry.name().to_string();
                let target = source_dir_clone.join(&name);
                if let Some(parent) = target.parent() {
                    std::fs::create_dir_all(parent)?;
                }
                let mut buf = Vec::new();
                entry.read_to_end(&mut buf)?;
                std::fs::write(&target, &buf)?;
                count += 1;
            }
            Ok(count)
        },
    )
    .await??;

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

    update_scan_progress(state, task_id, 40.0, "scanning", "running opengrep scanner").await;

    let scanner_image = state.config.scanner_opengrep_image.clone();
    let container_source_dir = "/scan/source";

    let known_paths = crate::scan::path_utils::collect_zip_relative_paths(&zip_path).ok();
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
            let log_excerpt = read_text_excerpt(Some(&workspace_dir.join(&log_rel_path))).await;
            let _ = tokio::fs::remove_dir_all(&workspace_dir).await;
            let detail = log_excerpt.unwrap_or_else(|| "no log available".to_string());
            return Err(format!(
                "opengrep scan failed: scanner produced no valid results; log={detail}"
            )
            .into());
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

    let findings = opengrep::parse_scan_output(
        &json_text,
        task_id,
        source_dir.to_str(),
        known_paths.as_ref(),
    );

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
        record.files_scanned = files_extracted as i64;
        record.updated_at = Some(now.clone());
        record.extra = json!({
            "error_count": error_count,
            "warning_count": warning_count,
            "high_confidence_count": high_confidence_count,
            "lines_scanned": 0,
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
                        files_extracted
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

async fn read_opengrep_results_text(results_path: &std::path::Path) -> Result<String, String> {
    tokio::fs::read_to_string(results_path)
        .await
        .map_err(|results_error| {
            format!("missing opengrep results output: results_error={results_error}")
        })
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
            jobs: config.opengrep_scan_jobs,
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
        cpu_limit: Some(config.opengrep_runner_cpu_limit),
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
        .unwrap_or_else(|| PathBuf::from("/tmp/vulhunter/scans"))
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
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
        .map(|finding| finding.payload.clone())
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
        .map(|finding| finding.payload.clone())
        .ok_or_else(|| ApiError::NotFound(format!("{engine} finding not found: {finding_id}")))
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
        .filter(|asset| asset.source_kind == "internal_rule" || asset.source_kind == "patch_rule")
        .map(|asset| {
            let fallback_language = asset
                .asset_path
                .strip_prefix("rules_from_patches/")
                .and_then(|path| path.split('/').next())
                .unwrap_or("generic")
                .to_string();
            let language = fallback_language;
            let source = if asset.source_kind == "patch_rule" {
                "patch"
            } else {
                "internal"
            };
            task_state::OpengrepRuleRecord {
                id: asset.asset_path.clone(),
                name: file_stem(&asset.asset_path),
                language,
                severity: extract_highest_rule_severity(&asset.content)
                    .unwrap_or_else(|| "WARNING".to_string()),
                confidence: Some("MEDIUM".to_string()),
                description: Some("builtin opengrep rule served by rust backend".to_string()),
                cwe: None,
                source: source.to_string(),
                correct: true,
                is_active: true,
                created_at: "2026-01-01T00:00:00Z".to_string(),
                pattern_yaml: asset.content,
                patch: None,
            }
        })
        .collect())
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
    let mut value = json!({
        "id": record.id,
        "project_id": record.project_id,
        "name": record.name,
        "status": record.status,
        "target_path": record.target_path,
        "total_findings": record.total_findings,
        "scan_duration_ms": record.scan_duration_ms,
        "files_scanned": record.files_scanned,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    });
    merge_json_object(&mut value, &record.extra);
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

fn read_file_lines_from_zip(
    zip_path: &std::path::Path,
    file_path: &str,
    range_start: usize,
    range_end: usize,
) -> (Vec<(usize, String)>, usize) {
    let Ok(reader) = std::fs::File::open(zip_path) else {
        return (Vec::new(), 0);
    };
    let Ok(mut archive) = ZipArchive::new(reader) else {
        return (Vec::new(), 0);
    };

    let normalized_target = file_path.trim_start_matches('/').replace('\\', "/");
    let entry_name = (0..archive.len())
        .filter_map(|i| {
            let entry = archive.by_index(i).ok()?;
            if entry.is_dir() {
                return None;
            }
            let name = entry.name().to_string();
            let normalized = name.trim_start_matches('/').replace('\\', "/");
            if normalized == normalized_target
                || normalized.ends_with(&format!("/{normalized_target}"))
            {
                Some(name)
            } else {
                None
            }
        })
        .next();

    let Some(entry_name) = entry_name else {
        return (Vec::new(), 0);
    };

    let Ok(mut entry) = archive.by_name(&entry_name) else {
        return (Vec::new(), 0);
    };

    let mut content = String::new();
    if entry.read_to_string(&mut content).is_err() {
        return (Vec::new(), 0);
    }

    let all_lines: Vec<&str> = content.lines().collect();
    let total_lines = all_lines.len();
    let clamped_end = range_end.min(total_lines);
    let lines: Vec<(usize, String)> = all_lines
        .iter()
        .enumerate()
        .filter(|(i, _)| {
            let line_number = i + 1;
            line_number >= range_start && line_number <= clamped_end
        })
        .map(|(i, line)| (i + 1, line.to_string()))
        .collect();

    (lines, total_lines)
}

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(error.to_string())
}

#[cfg(test)]
mod tests {
    use crate::config::AppConfig;

    use super::{
        build_opengrep_runner_spec, extract_highest_rule_severity, format_opengrep_runner_error,
        read_opengrep_results_text, OpengrepRunnerPaths,
    };

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
    fn builds_opengrep_runner_spec_with_stdout_capture_and_resource_limits() {
        let config = AppConfig::for_tests();

        let spec = build_opengrep_runner_spec(
            &config,
            config.scanner_opengrep_image.clone(),
            std::path::Path::new("/tmp/opengrep-runtime"),
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
        assert_eq!(spec.cpu_limit, Some(4.0));
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
                jobs: 4,
                max_memory_mb: 1536,
            })
        );
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
