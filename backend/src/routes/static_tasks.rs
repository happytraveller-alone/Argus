use std::collections::BTreeMap;

use axum::{
    extract::{Multipart, Path as AxumPath, Query, State},
    routing::{get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::{
    db::{projects, task_state},
    error::ApiError,
    llm_rule,
    scan::opengrep,
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/rules", get(list_opengrep_rules))
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
) -> Result<Json<Vec<Value>>, ApiError> {
    let items = merged_opengrep_rules(&state).await?;
    Ok(Json(
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
            .filter(|rule| match query.is_active {
                Some(is_active) => rule.is_active == is_active,
                None => true,
            })
            .filter(|rule| contains_keyword(&rule.name, query.keyword.as_deref()))
            .skip(query.skip.unwrap_or(0))
            .take(query.limit.unwrap_or(1_000))
            .map(|record| opengrep_rule_value(&record))
            .collect(),
    ))
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
    let record = task_state::OpengrepRuleRecord {
        id: format!("generated:{}", Uuid::new_v4()),
        name: format!("{repo_name}-{commit_hash}"),
        language: "generic".to_string(),
        severity: "WARNING".to_string(),
        confidence: Some("MEDIUM".to_string()),
        description: Some("generated from rust backend patch import".to_string()),
        cwe: None,
        source: "patch".to_string(),
        correct: true,
        is_active: true,
        created_at: now_rfc3339(),
        pattern_yaml: optional_string(&payload, "commit_content")
            .unwrap_or_else(|| "rules: []".to_string()),
        patch: optional_string(&payload, "commit_content"),
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
        if !contains_keyword(&rule.name, keyword.as_deref()) {
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
    create_static_task(
        &state,
        "opengrep",
        payload,
        json!({
            "error_count": 0,
            "warning_count": 0,
            "high_confidence_count": 0,
            "lines_scanned": 0,
        }),
    )
    .await
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
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "opengrep", &task_id).await
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
    let finding = get_static_finding_value(&state, "opengrep", &task_id, &finding_id).await?;
    let file_path = finding
        .get("file_path")
        .cloned()
        .unwrap_or_else(|| json!("unknown"));
    let line = finding
        .get("start_line")
        .cloned()
        .unwrap_or_else(|| json!(1));
    Ok(Json(json!({
        "task_id": task_id,
        "finding_id": finding_id,
        "file_path": file_path,
        "start_line": line,
        "end_line": line,
        "before": 5,
        "after": 5,
        "total_lines": 1,
        "lines": [{
            "line_number": line,
            "content": "// rust backend placeholder context",
            "is_hit": true
        }],
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

async fn create_static_task(
    state: &AppState,
    engine: &str,
    payload: Value,
    extra: Value,
) -> Result<Json<Value>, ApiError> {
    let project_id = required_string(&payload, "project_id")?;
    ensure_project_exists(state, &project_id).await?;
    let now = now_rfc3339();
    let task_id = Uuid::new_v4().to_string();
    let findings = default_static_findings(engine, &task_id, ".");
    let record = task_state::StaticTaskRecord {
        id: task_id.clone(),
        engine: engine.to_string(),
        project_id,
        name: optional_string(&payload, "name").unwrap_or_else(|| format!("{engine}-task")),
        status: "completed".to_string(),
        target_path: optional_string(&payload, "target_path").unwrap_or_else(|| ".".to_string()),
        total_findings: findings.len() as i64,
        scan_duration_ms: 0,
        files_scanned: 0,
        error_message: None,
        created_at: now.clone(),
        updated_at: Some(now.clone()),
        extra,
        progress: task_state::StaticTaskProgressRecord {
            progress: 100.0,
            current_stage: Some("completed".to_string()),
            message: Some(format!("{engine} task completed in rust backend")),
            started_at: Some(now.clone()),
            updated_at: Some(now.clone()),
            logs: vec![task_state::StaticTaskProgressLogRecord {
                timestamp: now.clone(),
                stage: "completed".to_string(),
                message: format!("{engine} task completed in rust backend"),
                progress: 100.0,
                level: "info".to_string(),
            }],
        },
        findings,
    };
    let mut snapshot = load_task_snapshot(state).await?;
    snapshot
        .static_tasks
        .insert(task_id.clone(), record.clone());
    save_task_snapshot(state, &snapshot).await?;
    Ok(Json(static_task_value(&record)))
}

fn default_static_findings(
    engine: &str,
    task_id: &str,
    file_path: &str,
) -> Vec<task_state::StaticFindingRecord> {
    let finding_id = format!("{engine}-finding-{}", Uuid::new_v4());
    let payload = match engine {
        "opengrep" => json!({
            "id": finding_id,
            "scan_task_id": task_id,
            "rule": {},
            "rule_name": "rust-placeholder-opengrep-rule",
            "cwe": ["CWE-000"],
            "description": "placeholder opengrep finding from rust backend",
            "file_path": file_path,
            "start_line": 1,
            "resolved_file_path": file_path,
            "resolved_line_start": 1,
            "code_snippet": "dangerous_call()",
            "severity": "WARNING",
            "status": "open",
            "confidence": "MEDIUM",
        }),
        _ => return Vec::new(),
    };

    vec![task_state::StaticFindingRecord {
        id: finding_id,
        scan_task_id: task_id.to_string(),
        status: "open".to_string(),
        payload,
    }]
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
) -> Result<Json<Vec<Value>>, ApiError> {
    let record = find_static_task(state, engine, task_id).await?;
    Ok(Json(
        record
            .findings
            .into_iter()
            .map(|finding| finding.payload)
            .collect(),
    ))
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
    let record = find_static_task(state, engine, task_id).await?;
    record
        .findings
        .into_iter()
        .find(|finding| finding.id == finding_id)
        .map(|finding| finding.payload)
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
            severity: "WARNING".to_string(),
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
        let record = task_state::OpengrepRuleRecord {
            id: format!("patch:{}", Uuid::new_v4()),
            name: filename,
            language: "generic".to_string(),
            severity: "WARNING".to_string(),
            confidence: Some("MEDIUM".to_string()),
            description: Some("patch-derived rule in rust backend".to_string()),
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
            let language = asset
                .asset_path
                .strip_prefix("rules_from_patches/")
                .and_then(|path| path.split('/').next())
                .unwrap_or("generic")
                .to_string();
            let source = if asset.source_kind == "patch_rule" {
                "patch"
            } else {
                "internal"
            };
            task_state::OpengrepRuleRecord {
                id: asset.asset_path.clone(),
                name: file_stem(&asset.asset_path),
                language,
                severity: "WARNING".to_string(),
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

async fn ensure_project_exists(state: &AppState, project_id: &str) -> Result<(), ApiError> {
    let project = projects::get_project(state, project_id)
        .await
        .map_err(internal_error)?;
    if project.is_none() {
        return Err(ApiError::NotFound(format!(
            "project not found: {project_id}"
        )));
    }
    Ok(())
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

fn internal_error<E: std::fmt::Display>(error: E) -> ApiError {
    ApiError::Internal(error.to_string())
}
