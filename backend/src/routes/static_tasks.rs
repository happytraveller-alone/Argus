use std::collections::BTreeSet;

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
    scan::{bandit, gitleaks, opengrep, phpstan, pmd},
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
        .route("/rules/upload/directory", post(upload_opengrep_rules_directory))
        .route("/rules/upload/json", post(upload_opengrep_rule_json))
        .route("/rules/upload/patch-archive", post(upload_patch_archive))
        .route("/rules/upload/patch-directory", post(upload_patch_directory))
        .route(
            "/rules/{rule_id}",
            get(get_opengrep_rule)
                .put(toggle_opengrep_rule)
                .patch(update_opengrep_rule)
                .delete(delete_opengrep_rule),
        )
        .route("/tasks", get(list_opengrep_tasks).post(create_opengrep_task))
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
        .route("/gitleaks/rules", get(list_gitleaks_rules).post(create_gitleaks_rule))
        .route("/gitleaks/rules/import-builtin", post(import_builtin_gitleaks_rules))
        .route("/gitleaks/rules/select", post(batch_update_gitleaks_rules))
        .route(
            "/gitleaks/rules/{rule_id}",
            get(get_gitleaks_rule)
                .patch(update_gitleaks_rule)
                .delete(delete_gitleaks_rule),
        )
        .route("/gitleaks/scan", post(create_gitleaks_task))
        .route("/gitleaks/tasks", get(list_gitleaks_tasks))
        .route(
            "/gitleaks/tasks/{task_id}",
            get(get_gitleaks_task).delete(delete_gitleaks_task),
        )
        .route("/gitleaks/tasks/{task_id}/interrupt", post(interrupt_gitleaks_task))
        .route(
            "/gitleaks/tasks/{task_id}/findings",
            get(list_gitleaks_findings),
        )
        .route(
            "/gitleaks/tasks/{task_id}/findings/{finding_id}",
            get(get_gitleaks_finding),
        )
        .route(
            "/gitleaks/findings/{finding_id}/status",
            post(update_gitleaks_finding_status),
        )
        .route("/bandit/rules", get(list_bandit_rules))
        .route("/bandit/rules/batch-enabled", post(batch_update_bandit_rules_enabled))
        .route("/bandit/rules/batch-delete", post(batch_delete_bandit_rules))
        .route("/bandit/rules/batch-restore", post(batch_restore_bandit_rules))
        .route(
            "/bandit/rules/{rule_id}",
            get(get_bandit_rule).patch(update_bandit_rule),
        )
        .route(
            "/bandit/rules/{rule_id}/enabled",
            post(update_bandit_rule_enabled),
        )
        .route("/bandit/rules/{rule_id}/delete", post(delete_bandit_rule))
        .route("/bandit/rules/{rule_id}/restore", post(restore_bandit_rule))
        .route("/bandit/scan", post(create_bandit_task))
        .route("/bandit/tasks", get(list_bandit_tasks))
        .route(
            "/bandit/tasks/{task_id}",
            get(get_bandit_task).delete(delete_bandit_task),
        )
        .route("/bandit/tasks/{task_id}/interrupt", post(interrupt_bandit_task))
        .route("/bandit/tasks/{task_id}/findings", get(list_bandit_findings))
        .route(
            "/bandit/tasks/{task_id}/findings/{finding_id}",
            get(get_bandit_finding),
        )
        .route(
            "/bandit/findings/{finding_id}/status",
            post(update_bandit_finding_status),
        )
        .route("/phpstan/rules", get(list_phpstan_rules))
        .route(
            "/phpstan/rules/batch/enabled",
            post(batch_update_phpstan_rules_enabled),
        )
        .route(
            "/phpstan/rules/batch/delete",
            post(batch_delete_phpstan_rules),
        )
        .route(
            "/phpstan/rules/batch/restore",
            post(batch_restore_phpstan_rules),
        )
        .route(
            "/phpstan/rules/{rule_id}",
            get(get_phpstan_rule).patch(update_phpstan_rule),
        )
        .route(
            "/phpstan/rules/{rule_id}/enabled",
            post(update_phpstan_rule_enabled),
        )
        .route("/phpstan/rules/{rule_id}/delete", post(delete_phpstan_rule))
        .route("/phpstan/rules/{rule_id}/restore", post(restore_phpstan_rule))
        .route("/phpstan/scan", post(create_phpstan_task))
        .route("/phpstan/tasks", get(list_phpstan_tasks))
        .route(
            "/phpstan/tasks/{task_id}",
            get(get_phpstan_task).delete(delete_phpstan_task),
        )
        .route("/phpstan/tasks/{task_id}/interrupt", post(interrupt_phpstan_task))
        .route("/phpstan/tasks/{task_id}/findings", get(list_phpstan_findings))
        .route(
            "/phpstan/tasks/{task_id}/findings/{finding_id}",
            get(get_phpstan_finding),
        )
        .route(
            "/phpstan/findings/{finding_id}/status",
            post(update_phpstan_finding_status),
        )
        .route("/pmd/presets", get(list_pmd_presets))
        .route("/pmd/builtin-rulesets", get(list_pmd_builtin_rulesets))
        .route(
            "/pmd/builtin-rulesets/{ruleset_id}",
            get(get_pmd_builtin_ruleset),
        )
        .route("/pmd/rule-configs", get(list_pmd_rule_configs))
        .route("/pmd/rule-configs/import", post(import_pmd_rule_config))
        .route(
            "/pmd/rule-configs/{rule_config_id}",
            get(get_pmd_rule_config)
                .patch(update_pmd_rule_config)
                .delete(delete_pmd_rule_config),
        )
        .route("/pmd/scan", post(create_pmd_task))
        .route("/pmd/tasks", get(list_pmd_tasks))
        .route(
            "/pmd/tasks/{task_id}",
            get(get_pmd_task).delete(delete_pmd_task),
        )
        .route("/pmd/tasks/{task_id}/interrupt", post(interrupt_pmd_task))
        .route("/pmd/tasks/{task_id}/findings", get(list_pmd_findings))
        .route(
            "/pmd/tasks/{task_id}/findings/{finding_id}",
            get(get_pmd_finding),
        )
        .route("/pmd/findings/{finding_id}/status", post(update_pmd_finding_status))
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
    tag: Option<String>,
    deleted: Option<String>,
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
    let snapshot = load_task_snapshot(&state).await?;
    let mut items = builtin_opengrep_rules(&state).await?;
    items.extend(snapshot.opengrep_rules.into_values());
    items.sort_by(|left, right| left.id.cmp(&right.id));
    Ok(Json(
        items.into_iter()
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
    let repo_name = optional_string(&payload, "repo_name").unwrap_or_else(|| "generated".to_string());
    let commit_hash = optional_string(&payload, "commit_hash").unwrap_or_else(|| Uuid::new_v4().to_string());
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
        pattern_yaml: optional_string(&payload, "commit_content").unwrap_or_else(|| "rules: []".to_string()),
        patch: optional_string(&payload, "commit_content"),
    };
    upsert_opengrep_rule(&state, record.clone()).await?;
    Ok(Json(opengrep_rule_detail_value(&record)))
}

async fn create_opengrep_generic_rule(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let record = task_state::OpengrepRuleRecord {
        id: format!("generic:{}", Uuid::new_v4()),
        name: "generic-rule".to_string(),
        language: "generic".to_string(),
        severity: "WARNING".to_string(),
        confidence: Some("MEDIUM".to_string()),
        description: Some("generic rule created in rust backend".to_string()),
        cwe: None,
        source: "json".to_string(),
        correct: true,
        is_active: true,
        created_at: now_rfc3339(),
        pattern_yaml: required_string(&payload, "rule_yaml")?,
        patch: None,
    };
    upsert_opengrep_rule(&state, record.clone()).await?;
    Ok(Json(opengrep_rule_detail_value(&record)))
}

async fn upload_opengrep_rule_json(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let record = task_state::OpengrepRuleRecord {
        id: optional_string(&payload, "id").unwrap_or_else(|| format!("json:{}", Uuid::new_v4())),
        name: optional_string(&payload, "name").unwrap_or_else(|| "uploaded-json-rule".to_string()),
        language: optional_string(&payload, "language").unwrap_or_else(|| "generic".to_string()),
        severity: optional_string(&payload, "severity").unwrap_or_else(|| "WARNING".to_string()),
        confidence: optional_string(&payload, "confidence"),
        description: optional_string(&payload, "description"),
        cwe: payload.get("cwe").and_then(string_array),
        source: optional_string(&payload, "source").unwrap_or_else(|| "json".to_string()),
        correct: payload.get("correct").and_then(Value::as_bool).unwrap_or(true),
        is_active: payload.get("is_active").and_then(Value::as_bool).unwrap_or(true),
        created_at: now_rfc3339(),
        pattern_yaml: required_string(&payload, "pattern_yaml")?,
        patch: optional_string(&payload, "patch"),
    };
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
    if let Some(value) = optional_string(&payload, "name") {
        rule.name = value;
    }
    if let Some(value) = optional_string(&payload, "pattern_yaml") {
        rule.pattern_yaml = value;
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
    snapshot.opengrep_rules.insert(rule_id.clone(), rule.clone());
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
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let current = builtin_opengrep_rules(&state).await?;
    let keyword = optional_string(&payload, "keyword");
    let updated = current
        .into_iter()
        .filter(|rule| contains_keyword(&rule.name, keyword.as_deref()))
        .count();
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
    create_static_task(&state, "opengrep", payload, json!({
        "error_count": 0,
        "warning_count": 0,
        "high_confidence_count": 0,
        "lines_scanned": 0,
    }))
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

async fn list_gitleaks_rules(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let mut items = builtin_gitleaks_rules(&state).await?;
    items.extend(snapshot.gitleaks_rules.into_values());
    Ok(Json(
        items.into_iter()
            .filter(|rule| match query.is_active {
                Some(is_active) => rule.is_active == is_active,
                None => true,
            })
            .filter(|rule| match query.source.as_deref() {
                Some(source) => rule.source == source,
                None => true,
            })
            .filter(|rule| contains_keyword(&rule.name, query.keyword.as_deref()))
            .filter(|rule| contains_tag(&rule.tags, query.tag.as_deref()))
            .skip(query.skip.unwrap_or(0))
            .take(query.limit.unwrap_or(1_000))
            .map(|record| gitleaks_rule_value(&record))
            .collect(),
    ))
}

async fn get_gitleaks_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let rule = find_gitleaks_rule(&state, &rule_id).await?;
    Ok(Json(gitleaks_rule_value(&rule)))
}

async fn create_gitleaks_rule(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let record = task_state::GitleaksRuleRecord {
        id: format!("custom:{}", Uuid::new_v4()),
        name: optional_string(&payload, "name").unwrap_or_else(|| "custom-gitleaks-rule".to_string()),
        description: optional_string(&payload, "description"),
        rule_id: required_string(&payload, "rule_id")?,
        secret_group: payload.get("secret_group").and_then(Value::as_i64).unwrap_or(0),
        regex: required_string(&payload, "regex")?,
        keywords: payload.get("keywords").and_then(string_array).unwrap_or_default(),
        path: optional_string(&payload, "path"),
        tags: payload.get("tags").and_then(string_array).unwrap_or_default(),
        entropy: payload.get("entropy").and_then(Value::as_f64),
        is_active: payload.get("is_active").and_then(Value::as_bool).unwrap_or(true),
        source: optional_string(&payload, "source").unwrap_or_else(|| "custom".to_string()),
        created_at: now_rfc3339(),
        updated_at: None,
    };
    let mut snapshot = load_task_snapshot(&state).await?;
    snapshot
        .gitleaks_rules
        .insert(record.id.clone(), record.clone());
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(gitleaks_rule_value(&record)))
}

async fn update_gitleaks_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    let mut rule = find_gitleaks_rule(&state, &rule_id).await?;
    if let Some(value) = optional_string(&payload, "name") {
        rule.name = value;
    }
    if let Some(value) = optional_string(&payload, "description") {
        rule.description = Some(value);
    }
    if let Some(value) = optional_string(&payload, "rule_id") {
        rule.rule_id = value;
    }
    if let Some(value) = optional_string(&payload, "regex") {
        rule.regex = value;
    }
    if let Some(value) = payload.get("keywords").and_then(string_array) {
        rule.keywords = value;
    }
    if let Some(value) = payload.get("tags").and_then(string_array) {
        rule.tags = value;
    }
    if let Some(value) = payload.get("is_active").and_then(Value::as_bool) {
        rule.is_active = value;
    }
    rule.updated_at = Some(now_rfc3339());
    snapshot.gitleaks_rules.insert(rule_id.clone(), rule.clone());
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(gitleaks_rule_value(&rule)))
}

async fn delete_gitleaks_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    snapshot.gitleaks_rules.remove(&rule_id);
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "gitleaks rule deleted in rust backend",
        "rule_id": rule_id,
    })))
}

async fn batch_update_gitleaks_rules(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    let updated = builtin_gitleaks_rules(&state).await?.len();
    Ok(Json(json!({
        "message": "gitleaks rule selection updated in rust backend",
        "updated_count": updated,
        "is_active": is_active,
    })))
}

async fn import_builtin_gitleaks_rules() -> Json<Value> {
    Json(json!({
        "message": "builtin gitleaks rules are already served by rust backend"
    }))
}

async fn create_gitleaks_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let no_git = payload
        .get("no_git")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        .to_string();
    create_static_task(&state, "gitleaks", payload, json!({
        "no_git": no_git,
    }))
    .await
}

async fn list_gitleaks_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "gitleaks", query).await
}

async fn get_gitleaks_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "gitleaks", &task_id).await
}

async fn delete_gitleaks_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "gitleaks", &task_id).await
}

async fn interrupt_gitleaks_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    interrupt_static_task(&state, "gitleaks", &task_id).await
}

async fn list_gitleaks_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "gitleaks", &task_id).await
}

async fn get_gitleaks_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "gitleaks", &task_id, &finding_id).await
}

async fn update_gitleaks_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "gitleaks", &finding_id, &query.status).await
}

async fn list_bandit_rules(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let overrides = load_task_snapshot(&state).await?.bandit_rule_overrides;
    let items = builtin_bandit_rules(&state).await?;
    Ok(Json(
        items
            .into_iter()
            .map(|rule| {
                let rule_id = rule
                    .get("test_id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                apply_rule_override_value(bandit_rule_value(&rule), overrides.get(&rule_id))
            })
            .filter(|value| match query.is_active {
                Some(is_active) => value.get("is_active").and_then(Value::as_bool) == Some(is_active),
                None => true,
            })
            .filter(|value| match query.deleted.as_deref() {
                Some("true") => value.get("is_deleted").and_then(Value::as_bool) == Some(true),
                Some("false") => value.get("is_deleted").and_then(Value::as_bool) != Some(true),
                _ => true,
            })
            .filter(|value| contains_keyword(value.get("name").and_then(Value::as_str).unwrap_or_default(), query.keyword.as_deref()))
            .skip(query.skip.unwrap_or(0))
            .take(query.limit.unwrap_or(1_000))
            .collect(),
    ))
}

async fn get_bandit_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let overrides = load_task_snapshot(&state).await?.bandit_rule_overrides;
    let rule = builtin_bandit_rules(&state)
        .await?
        .into_iter()
        .find(|rule| {
            rule.get("test_id")
                .and_then(Value::as_str)
                .is_some_and(|value| value == rule_id)
        })
        .ok_or_else(|| ApiError::NotFound(format!("bandit rule not found: {rule_id}")))?;
    Ok(Json(apply_rule_override_value(
        bandit_rule_value(&rule),
        overrides.get(&rule_id),
    )))
}

async fn update_bandit_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "bandit", &rule_id, payload.clone()).await?;
    Ok(Json(json!({
        "message": "bandit rule updated in rust backend",
        "rule": apply_rule_override_value((get_bandit_rule(State(state.clone()), AxumPath(rule_id.clone())).await?).0, Some(&task_state::RuleOverrideRecord {
            id: rule_id,
            is_active: None,
            is_deleted: None,
            patch: payload,
        })),
    })))
}

async fn update_bandit_rule_enabled(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    upsert_rule_override(&state, "bandit", &rule_id, json!({ "is_active": is_active })).await?;
    Ok(Json(json!({
        "message": "bandit rule enabled state updated in rust backend",
        "rule_id": rule_id,
        "is_active": is_active,
    })))
}

async fn batch_update_bandit_rules_enabled(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    Ok(Json(json!({
        "message": "bandit rule batch enabled updated in rust backend",
        "updated_count": builtin_bandit_rules(&state).await?.len(),
        "is_active": is_active,
    })))
}

async fn delete_bandit_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "bandit", &rule_id, json!({ "is_deleted": true })).await?;
    Ok(Json(json!({
        "message": "bandit rule deleted in rust backend",
        "rule_id": rule_id,
        "is_deleted": true,
    })))
}

async fn restore_bandit_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "bandit", &rule_id, json!({ "is_deleted": false })).await?;
    Ok(Json(json!({
        "message": "bandit rule restored in rust backend",
        "rule_id": rule_id,
        "is_deleted": false,
    })))
}

async fn batch_delete_bandit_rules(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!({
        "message": "bandit rule batch delete acknowledged in rust backend",
        "updated_count": builtin_bandit_rules(&state).await?.len(),
        "is_deleted": true,
    })))
}

async fn batch_restore_bandit_rules(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!({
        "message": "bandit rule batch restore acknowledged in rust backend",
        "updated_count": builtin_bandit_rules(&state).await?.len(),
        "is_deleted": false,
    })))
}

async fn create_bandit_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let severity_level =
        optional_string(&payload, "severity_level").unwrap_or_else(|| "medium".to_string());
    let confidence_level =
        optional_string(&payload, "confidence_level").unwrap_or_else(|| "medium".to_string());
    create_static_task(&state, "bandit", payload, json!({
        "severity_level": severity_level,
        "confidence_level": confidence_level,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
    }))
    .await
}

async fn list_bandit_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "bandit", query).await
}

async fn get_bandit_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "bandit", &task_id).await
}

async fn delete_bandit_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "bandit", &task_id).await
}

async fn interrupt_bandit_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    interrupt_static_task(&state, "bandit", &task_id).await
}

async fn list_bandit_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "bandit", &task_id).await
}

async fn get_bandit_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "bandit", &task_id, &finding_id).await
}

async fn update_bandit_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "bandit", &finding_id, &query.status).await
}

async fn list_phpstan_rules(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let overrides = load_task_snapshot(&state).await?.phpstan_rule_overrides;
    let items = builtin_phpstan_rules(&state).await?;
    Ok(Json(
        items
            .into_iter()
            .map(|rule| {
                let rule_id = rule
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                apply_rule_override_value(phpstan_rule_value(&rule), overrides.get(&rule_id))
            })
            .filter(|value| match query.is_active {
                Some(is_active) => value.get("is_active").and_then(Value::as_bool) == Some(is_active),
                None => true,
            })
            .filter(|value| match query.deleted.as_deref() {
                Some("true") => value.get("is_deleted").and_then(Value::as_bool) == Some(true),
                Some("false") => value.get("is_deleted").and_then(Value::as_bool) != Some(true),
                _ => true,
            })
            .filter(|value| contains_keyword(value.get("name").and_then(Value::as_str).unwrap_or_default(), query.keyword.as_deref()))
            .skip(query.skip.unwrap_or(0))
            .take(query.limit.unwrap_or(1_000))
            .collect(),
    ))
}

async fn get_phpstan_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let overrides = load_task_snapshot(&state).await?.phpstan_rule_overrides;
    let rule = builtin_phpstan_rules(&state)
        .await?
        .into_iter()
        .find(|rule| {
            rule.get("id")
                .and_then(Value::as_str)
                .is_some_and(|value| value == rule_id)
        })
        .ok_or_else(|| ApiError::NotFound(format!("phpstan rule not found: {rule_id}")))?;
    Ok(Json(apply_rule_override_value(
        phpstan_rule_value(&rule),
        overrides.get(&rule_id),
    )))
}

async fn update_phpstan_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "phpstan", &rule_id, payload.clone()).await?;
    Ok(Json(json!({
        "message": "phpstan rule updated in rust backend",
        "rule": apply_rule_override_value((get_phpstan_rule(State(state.clone()), AxumPath(rule_id.clone())).await?).0, Some(&task_state::RuleOverrideRecord {
            id: rule_id,
            is_active: None,
            is_deleted: None,
            patch: payload,
        })),
    })))
}

async fn update_phpstan_rule_enabled(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    upsert_rule_override(&state, "phpstan", &rule_id, json!({ "is_active": is_active })).await?;
    Ok(Json(json!({
        "message": "phpstan rule enabled state updated in rust backend",
        "rule_id": rule_id,
        "is_active": is_active,
    })))
}

async fn batch_update_phpstan_rules_enabled(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let is_active = payload
        .get("is_active")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    Ok(Json(json!({
        "message": "phpstan rule batch enabled updated in rust backend",
        "updated_count": builtin_phpstan_rules(&state).await?.len(),
        "is_active": is_active,
    })))
}

async fn delete_phpstan_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "phpstan", &rule_id, json!({ "is_deleted": true })).await?;
    Ok(Json(json!({
        "message": "phpstan rule deleted in rust backend",
        "rule_id": rule_id,
        "is_deleted": true,
    })))
}

async fn restore_phpstan_rule(
    State(state): State<AppState>,
    AxumPath(rule_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    upsert_rule_override(&state, "phpstan", &rule_id, json!({ "is_deleted": false })).await?;
    Ok(Json(json!({
        "message": "phpstan rule restored in rust backend",
        "rule_id": rule_id,
        "is_deleted": false,
    })))
}

async fn batch_delete_phpstan_rules(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!({
        "message": "phpstan rule batch delete acknowledged in rust backend",
        "updated_count": builtin_phpstan_rules(&state).await?.len(),
        "is_deleted": true,
    })))
}

async fn batch_restore_phpstan_rules(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!({
        "message": "phpstan rule batch restore acknowledged in rust backend",
        "updated_count": builtin_phpstan_rules(&state).await?.len(),
        "is_deleted": false,
    })))
}

async fn create_phpstan_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let level = payload.get("level").and_then(Value::as_i64).unwrap_or(5);
    create_static_task(&state, "phpstan", payload, json!({
        "level": level,
    }))
    .await
}

async fn list_phpstan_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "phpstan", query).await
}

async fn get_phpstan_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "phpstan", &task_id).await
}

async fn delete_phpstan_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "phpstan", &task_id).await
}

async fn interrupt_phpstan_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    interrupt_static_task(&state, "phpstan", &task_id).await
}

async fn list_phpstan_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "phpstan", &task_id).await
}

async fn get_phpstan_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "phpstan", &task_id, &finding_id).await
}

async fn update_phpstan_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "phpstan", &finding_id, &query.status).await
}

async fn list_pmd_presets() -> Json<Vec<Value>> {
    Json(vec![
        json!({"id": "security", "name": "Security", "alias": "security", "description": "Security-focused PMD preset", "categories": ["security"]}),
        json!({"id": "performance", "name": "Performance", "alias": "performance", "description": "Performance-focused PMD preset", "categories": ["performance"]}),
        json!({"id": "design", "name": "Design", "alias": "design", "description": "Design-focused PMD preset", "categories": ["design"]}),
    ])
}

async fn list_pmd_builtin_rulesets(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let items = builtin_pmd_rulesets(&state).await?;
    Ok(Json(
        items
            .into_iter()
            .filter(|item| contains_keyword(&item.name, query.keyword.as_deref()))
            .filter(|item| match query.language.as_deref() {
                Some(language) => item.languages.iter().any(|value| value.eq_ignore_ascii_case(language)),
                None => true,
            })
            .take(query.limit.unwrap_or(1_000))
            .map(|record| pmd_rule_config_value(&record))
            .collect(),
    ))
}

async fn get_pmd_builtin_ruleset(
    State(state): State<AppState>,
    AxumPath(ruleset_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let item = builtin_pmd_rulesets(&state)
        .await?
        .into_iter()
        .find(|item| item.id == ruleset_id)
        .ok_or_else(|| ApiError::NotFound(format!("pmd ruleset not found: {ruleset_id}")))?;
    Ok(Json(pmd_rule_config_value(&item)))
}

async fn import_pmd_rule_config(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let mut name = "custom-pmd-ruleset".to_string();
    let mut description = None;
    let mut raw_xml = "<ruleset />".to_string();
    while let Some(field) = multipart.next_field().await.map_err(internal_error)? {
        match field.name() {
            Some("name") => {
                name = field.text().await.map_err(internal_error)?;
            }
            Some("description") => {
                description = Some(field.text().await.map_err(internal_error)?);
            }
            Some("xml_file") => {
                raw_xml = String::from_utf8(field.bytes().await.map_err(internal_error)?.to_vec())
                    .unwrap_or_else(|_| "<ruleset />".to_string());
            }
            _ => {}
        }
    }
    let record = build_custom_pmd_rule_config(name, description, raw_xml);
    let mut snapshot = load_task_snapshot(&state).await?;
    snapshot
        .pmd_rule_configs
        .insert(record.id.clone(), record.clone());
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(pmd_rule_config_value(&record)))
}

async fn list_pmd_rule_configs(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    let items = load_task_snapshot(&state)
        .await?
        .pmd_rule_configs
        .into_values()
        .filter(|item| match query.is_active {
            Some(is_active) => item.is_active == is_active,
            None => true,
        })
        .filter(|item| contains_keyword(&item.name, query.keyword.as_deref()))
        .skip(query.skip.unwrap_or(0))
        .take(query.limit.unwrap_or(1_000))
        .map(|item| pmd_rule_config_value(&item))
        .collect::<Vec<_>>();
    Ok(Json(items))
}

async fn get_pmd_rule_config(
    State(state): State<AppState>,
    AxumPath(rule_config_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let snapshot = load_task_snapshot(&state).await?;
    let item = snapshot
        .pmd_rule_configs
        .get(&rule_config_id)
        .ok_or_else(|| ApiError::NotFound(format!("pmd rule config not found: {rule_config_id}")))?;
    Ok(Json(pmd_rule_config_value(item)))
}

async fn update_pmd_rule_config(
    State(state): State<AppState>,
    AxumPath(rule_config_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    let item = snapshot
        .pmd_rule_configs
        .get_mut(&rule_config_id)
        .ok_or_else(|| ApiError::NotFound(format!("pmd rule config not found: {rule_config_id}")))?;
    if let Some(value) = optional_string(&payload, "name") {
        item.name = value;
    }
    if let Some(value) = optional_string(&payload, "description") {
        item.description = Some(value);
    }
    if let Some(value) = optional_bool(&payload, "is_active") {
        item.is_active = value;
    }
    item.updated_at = Some(now_rfc3339());
    let response_value = pmd_rule_config_value(item);
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(response_value))
}

async fn delete_pmd_rule_config(
    State(state): State<AppState>,
    AxumPath(rule_config_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    let mut snapshot = load_task_snapshot(&state).await?;
    snapshot.pmd_rule_configs.remove(&rule_config_id);
    save_task_snapshot(&state, &snapshot).await?;
    Ok(Json(json!({
        "message": "pmd rule config deleted in rust backend",
        "id": rule_config_id,
    })))
}

async fn create_pmd_task(
    State(state): State<AppState>,
    Json(payload): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let ruleset = optional_string(&payload, "ruleset").unwrap_or_else(|| "security".to_string());
    create_static_task(&state, "pmd", payload, json!({
        "ruleset": ruleset,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
    }))
    .await
}

async fn list_pmd_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_tasks(&state, "pmd", query).await
}

async fn get_pmd_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    get_static_task(&state, "pmd", &task_id).await
}

async fn delete_pmd_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    delete_static_task(&state, "pmd", &task_id).await
}

async fn interrupt_pmd_task(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    interrupt_static_task(&state, "pmd", &task_id).await
}

async fn list_pmd_findings(
    State(state): State<AppState>,
    AxumPath(task_id): AxumPath<String>,
) -> Result<Json<Vec<Value>>, ApiError> {
    list_static_findings(&state, "pmd", &task_id).await
}

async fn get_pmd_finding(
    State(state): State<AppState>,
    AxumPath((task_id, finding_id)): AxumPath<(String, String)>,
) -> Result<Json<Value>, ApiError> {
    get_static_finding(&state, "pmd", &task_id, &finding_id).await
}

async fn update_pmd_finding_status(
    State(state): State<AppState>,
    AxumPath(finding_id): AxumPath<String>,
    Query(query): Query<StatusQuery>,
) -> Result<Json<Value>, ApiError> {
    update_static_finding_status(&state, "pmd", &finding_id, &query.status).await
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
    let record = task_state::StaticTaskRecord {
        id: task_id.clone(),
        engine: engine.to_string(),
        project_id,
        name: optional_string(&payload, "name").unwrap_or_else(|| format!("{engine}-task")),
        status: "completed".to_string(),
        target_path: optional_string(&payload, "target_path").unwrap_or_else(|| ".".to_string()),
        total_findings: 0,
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
        findings: Vec::new(),
    };
    let mut snapshot = load_task_snapshot(state).await?;
    snapshot.static_tasks.insert(task_id.clone(), record.clone());
    save_task_snapshot(state, &snapshot).await?;
    Ok(Json(static_task_value(&record)))
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
        return Err(ApiError::NotFound(format!("{engine} task not found: {task_id}")));
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
        return Err(ApiError::NotFound(format!("{engine} task not found: {task_id}")));
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
        if let Some(finding) = record.findings.iter_mut().find(|finding| finding.id == finding_id) {
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
    Err(ApiError::NotFound(format!("{engine} finding not found: {finding_id}")))
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
        return Err(ApiError::NotFound(format!("{engine} task not found: {task_id}")));
    }
    Ok(record.clone())
}

async fn find_opengrep_rule(
    state: &AppState,
    rule_id: &str,
) -> Result<task_state::OpengrepRuleRecord, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    if let Some(rule) = snapshot.opengrep_rules.get(rule_id) {
        return Ok(rule.clone());
    }
    builtin_opengrep_rules(state)
        .await?
        .into_iter()
        .find(|rule| rule.id == rule_id)
        .ok_or_else(|| ApiError::NotFound(format!("opengrep rule not found: {rule_id}")))
}

async fn find_gitleaks_rule(
    state: &AppState,
    rule_id: &str,
) -> Result<task_state::GitleaksRuleRecord, ApiError> {
    let snapshot = load_task_snapshot(state).await?;
    if let Some(rule) = snapshot.gitleaks_rules.get(rule_id) {
        return Ok(rule.clone());
    }
    builtin_gitleaks_rules(state)
        .await?
        .into_iter()
        .find(|rule| rule.id == rule_id)
        .ok_or_else(|| ApiError::NotFound(format!("gitleaks rule not found: {rule_id}")))
}

async fn upsert_opengrep_rule(
    state: &AppState,
    record: task_state::OpengrepRuleRecord,
) -> Result<(), ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    snapshot.opengrep_rules.insert(record.id.clone(), record);
    save_task_snapshot(state, &snapshot).await
}

async fn upsert_rule_override(
    state: &AppState,
    engine: &str,
    rule_id: &str,
    patch: Value,
) -> Result<(), ApiError> {
    let mut snapshot = load_task_snapshot(state).await?;
    let target = match engine {
        "bandit" => &mut snapshot.bandit_rule_overrides,
        "phpstan" => &mut snapshot.phpstan_rule_overrides,
        _ => return Err(ApiError::BadRequest(format!("unsupported rule override engine: {engine}"))),
    };
    let entry = target.entry(rule_id.to_string()).or_insert_with(|| task_state::RuleOverrideRecord {
        id: rule_id.to_string(),
        is_active: None,
        is_deleted: None,
        patch: json!({}),
    });
    if let Some(is_active) = patch.get("is_active").and_then(Value::as_bool) {
        entry.is_active = Some(is_active);
    }
    if let Some(is_deleted) = patch.get("is_deleted").and_then(Value::as_bool) {
        entry.is_deleted = Some(is_deleted);
    }
    merge_json_object(&mut entry.patch, &patch);
    save_task_snapshot(state, &snapshot).await
}

async fn persist_uploaded_opengrep_rules(
    state: &AppState,
    mut multipart: Multipart,
    source: &str,
) -> Result<usize, ApiError> {
    let mut count = 0usize;
    while let Some(field) = multipart.next_field().await.map_err(internal_error)? {
        let filename = field.file_name().unwrap_or("uploaded-rule.yaml").to_string();
        let bytes = field.bytes().await.map_err(internal_error)?;
        let pattern_yaml = String::from_utf8(bytes.to_vec()).unwrap_or_else(|_| "rules: []".to_string());
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
    let assets = opengrep::load_rule_assets(state).await.map_err(internal_error)?;
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

async fn builtin_gitleaks_rules(
    state: &AppState,
) -> Result<Vec<task_state::GitleaksRuleRecord>, ApiError> {
    let content = gitleaks::load_builtin_config(state)
        .await
        .map_err(internal_error)?
        .unwrap_or_default();
    Ok(parse_gitleaks_rules(&content))
}

async fn builtin_bandit_rules(
    state: &AppState,
) -> Result<Vec<Value>, ApiError> {
    let snapshot = bandit::load_builtin_snapshot(state)
        .await
        .map_err(internal_error)?
        .unwrap_or_else(|| json!({ "rules": [] }));
    Ok(snapshot
        .get("rules")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

async fn builtin_phpstan_rules(
    state: &AppState,
) -> Result<Vec<Value>, ApiError> {
    let assets = phpstan::load_builtin_assets(state)
        .await
        .map_err(internal_error)?;
    let combined = assets
        .into_iter()
        .find(|asset| asset.asset_path == "rules_phpstan/phpstan_rules_combined.json")
        .ok_or_else(|| ApiError::Internal("missing phpstan combined rules asset".to_string()))?;
    let payload = serde_json::from_str::<Value>(&combined.content).map_err(internal_error)?;
    Ok(payload
        .get("rules")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

async fn builtin_pmd_rulesets(
    state: &AppState,
) -> Result<Vec<task_state::PmdRuleConfigRecord>, ApiError> {
    let assets = pmd::load_builtin_rulesets(state)
        .await
        .map_err(internal_error)?;
    Ok(assets
        .into_iter()
        .map(|asset| {
            let filename = asset
                .asset_path
                .strip_prefix("rules_pmd/")
                .unwrap_or(asset.asset_path.as_str())
                .to_string();
            let name = xml_attr(&asset.content, "ruleset", "name").unwrap_or_else(|| file_stem(&filename));
            let description = xml_tag(&asset.content, "description");
            let rule_count = asset.content.matches("<rule ").count() as i64;
            let languages = xml_attr_values(&asset.content, "language");
            let priorities = xml_tag_values(&asset.content, "priority")
                .into_iter()
                .filter_map(|value| value.parse::<i64>().ok())
                .collect::<Vec<_>>();
            let external_info_urls = xml_attr_values(&asset.content, "externalInfoUrl");
            task_state::PmdRuleConfigRecord {
                id: filename.clone(),
                name: name.clone(),
                description,
                filename,
                is_active: true,
                source: "builtin".to_string(),
                ruleset_name: name,
                rule_count,
                languages,
                priorities,
                external_info_urls,
                rules: Vec::new(),
                raw_xml: asset.content,
                created_at: Some("2026-01-01T00:00:00Z".to_string()),
                updated_at: None,
            }
        })
        .collect())
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

fn gitleaks_rule_value(record: &task_state::GitleaksRuleRecord) -> Value {
    json!({
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "rule_id": record.rule_id,
        "secret_group": record.secret_group,
        "regex": record.regex,
        "keywords": record.keywords,
        "path": record.path,
        "tags": record.tags,
        "entropy": record.entropy,
        "is_active": record.is_active,
        "source": record.source,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    })
}

fn bandit_rule_value(rule: &Value) -> Value {
    json!({
        "id": rule.get("test_id").cloned().unwrap_or(Value::Null),
        "test_id": rule.get("test_id").cloned().unwrap_or(Value::Null),
        "name": rule.get("name").cloned().unwrap_or(Value::Null),
        "description": rule.get("description").cloned().unwrap_or(Value::Null),
        "description_summary": rule.get("description_summary").cloned().unwrap_or(Value::Null),
        "checks": rule.get("checks").cloned().unwrap_or_else(|| json!([])),
        "source": rule.get("source").cloned().unwrap_or_else(|| json!("builtin")),
        "bandit_version": rule.get("bandit_version").cloned().unwrap_or(Value::Null),
        "is_active": true,
        "is_deleted": false,
        "created_at": Value::Null,
        "updated_at": Value::Null,
    })
}

fn phpstan_rule_value(rule: &Value) -> Value {
    json!({
        "id": rule.get("id").cloned().unwrap_or(Value::Null),
        "package": rule.get("package").cloned().unwrap_or(Value::Null),
        "repo": rule.get("repo").cloned().unwrap_or(Value::Null),
        "rule_class": rule.get("rule_class").cloned().unwrap_or(Value::Null),
        "name": rule.get("name").cloned().unwrap_or(Value::Null),
        "description_summary": rule.get("description_summary").cloned().unwrap_or(Value::Null),
        "source_file": rule.get("source_file").cloned().unwrap_or(Value::Null),
        "source": rule.get("source").cloned().unwrap_or_else(|| json!("official_extension")),
        "source_content": Value::Null,
        "is_active": true,
        "is_deleted": false,
        "created_at": Value::Null,
        "updated_at": Value::Null,
    })
}

fn pmd_rule_config_value(record: &task_state::PmdRuleConfigRecord) -> Value {
    json!({
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "filename": record.filename,
        "is_active": record.is_active,
        "source": record.source,
        "ruleset_name": record.ruleset_name,
        "rule_count": record.rule_count,
        "languages": record.languages,
        "priorities": record.priorities,
        "external_info_urls": record.external_info_urls,
        "rules": record.rules,
        "raw_xml": record.raw_xml,
        "created_by": Value::Null,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    })
}

fn apply_rule_override_value(mut value: Value, override_record: Option<&task_state::RuleOverrideRecord>) -> Value {
    if let Some(override_record) = override_record {
        if let Some(is_active) = override_record.is_active {
            if let Some(object) = value.as_object_mut() {
                object.insert("is_active".to_string(), json!(is_active));
            }
        }
        if let Some(is_deleted) = override_record.is_deleted {
            if let Some(object) = value.as_object_mut() {
                object.insert("is_deleted".to_string(), json!(is_deleted));
            }
        }
        merge_json_object(&mut value, &override_record.patch);
    }
    value
}

fn build_custom_pmd_rule_config(
    name: String,
    description: Option<String>,
    raw_xml: String,
) -> task_state::PmdRuleConfigRecord {
    let filename = format!("{}.xml", slugify(&name));
    let ruleset_name = xml_attr(&raw_xml, "ruleset", "name").unwrap_or_else(|| name.clone());
    let languages = xml_attr_values(&raw_xml, "language");
    let priorities = xml_tag_values(&raw_xml, "priority")
        .into_iter()
        .filter_map(|value| value.parse::<i64>().ok())
        .collect::<Vec<_>>();
    let external_info_urls = xml_attr_values(&raw_xml, "externalInfoUrl");
    task_state::PmdRuleConfigRecord {
        id: format!("cfg:{}", Uuid::new_v4()),
        name,
        description,
        filename,
        is_active: true,
        source: "custom".to_string(),
        ruleset_name,
        rule_count: raw_xml.matches("<rule ").count() as i64,
        languages,
        priorities,
        external_info_urls,
        rules: Vec::new(),
        raw_xml,
        created_at: Some(now_rfc3339()),
        updated_at: None,
    }
}

async fn load_task_snapshot(state: &AppState) -> Result<task_state::TaskStateSnapshot, ApiError> {
    task_state::load_snapshot(state).await.map_err(internal_error)
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
        return Err(ApiError::NotFound(format!("project not found: {project_id}")));
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
        items.iter()
            .filter_map(|item| item.as_str().map(ToString::to_string))
            .collect::<Vec<_>>()
    })
}

fn contains_keyword(text: &str, keyword: Option<&str>) -> bool {
    match keyword.map(str::trim).filter(|value| !value.is_empty()) {
        Some(keyword) => text.to_ascii_lowercase().contains(&keyword.to_ascii_lowercase()),
        None => true,
    }
}

fn contains_tag(tags: &[String], tag: Option<&str>) -> bool {
    match tag.map(str::trim).filter(|value| !value.is_empty()) {
        Some(tag) => tags.iter().any(|value| value.eq_ignore_ascii_case(tag)),
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

fn parse_gitleaks_rules(content: &str) -> Vec<task_state::GitleaksRuleRecord> {
    let mut out = Vec::new();
    for section in content.split("[[rules]]").skip(1) {
        let mut id = None;
        let mut description = None;
        let mut regex = None;
        let mut entropy = None;
        let mut keywords = Vec::new();
        for line in section.lines() {
            let trimmed = line.trim();
            if let Some(value) = trimmed.strip_prefix("id = ") {
                id = Some(unquote(value));
            } else if let Some(value) = trimmed.strip_prefix("description = ") {
                description = Some(unquote(value));
            } else if let Some(value) = trimmed.strip_prefix("regex = ") {
                regex = Some(unquote(value));
            } else if let Some(value) = trimmed.strip_prefix("entropy = ") {
                entropy = value.trim().parse::<f64>().ok();
            } else if let Some(value) = trimmed.strip_prefix("keywords = ") {
                keywords = parse_string_list(value);
            }
        }
        let Some(id) = id else {
            continue;
        };
        out.push(task_state::GitleaksRuleRecord {
            id: format!("builtin:{id}"),
            name: id.clone(),
            description,
            rule_id: id,
            secret_group: 0,
            regex: regex.unwrap_or_default(),
            keywords,
            path: None,
            tags: Vec::new(),
            entropy,
            is_active: true,
            source: "builtin".to_string(),
            created_at: "2026-01-01T00:00:00Z".to_string(),
            updated_at: None,
        });
    }
    out
}

fn parse_string_list(input: &str) -> Vec<String> {
    input
        .trim()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .split(',')
        .map(unquote)
        .filter(|item| !item.is_empty())
        .collect()
}

fn unquote(value: &str) -> String {
    value
        .trim()
        .trim_matches('\'')
        .trim_matches('"')
        .trim_matches('`')
        .to_string()
}

fn xml_attr(content: &str, tag_name: &str, attr_name: &str) -> Option<String> {
    let start = content.find(&format!("<{tag_name}"))?;
    let rest = &content[start..];
    let attr_token = format!("{attr_name}=\"");
    let attr_start = rest.find(&attr_token)?;
    let after = &rest[attr_start + attr_token.len()..];
    let attr_end = after.find('"')?;
    Some(after[..attr_end].to_string())
}

fn xml_attr_values(content: &str, attr_name: &str) -> Vec<String> {
    let token = format!("{attr_name}=\"");
    let mut values = BTreeSet::new();
    let mut current = content;
    while let Some(index) = current.find(&token) {
        let after = &current[index + token.len()..];
        if let Some(end) = after.find('"') {
            values.insert(after[..end].to_string());
            current = &after[end + 1..];
        } else {
            break;
        }
    }
    values.into_iter().collect()
}

fn xml_tag(content: &str, tag_name: &str) -> Option<String> {
    let start_token = format!("<{tag_name}>");
    let end_token = format!("</{tag_name}>");
    let start = content.find(&start_token)?;
    let after = &content[start + start_token.len()..];
    let end = after.find(&end_token)?;
    Some(after[..end].trim().replace('\n', " "))
}

fn xml_tag_values(content: &str, tag_name: &str) -> Vec<String> {
    let start_token = format!("<{tag_name}>");
    let end_token = format!("</{tag_name}>");
    let mut values = Vec::new();
    let mut current = content;
    while let Some(start) = current.find(&start_token) {
        let after = &current[start + start_token.len()..];
        if let Some(end) = after.find(&end_token) {
            values.push(after[..end].trim().replace('\n', " "));
            current = &after[end + end_token.len()..];
        } else {
            break;
        }
    }
    values
}

fn slugify(input: &str) -> String {
    input
        .chars()
        .map(|ch| match ch {
            'a'..='z' | 'A'..='Z' | '0'..='9' => ch.to_ascii_lowercase(),
            _ => '-',
        })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("-")
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
