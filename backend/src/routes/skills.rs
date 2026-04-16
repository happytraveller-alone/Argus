use std::{
    collections::BTreeMap,
    env,
    io::ErrorKind,
    path::{Path, PathBuf},
};

use axum::{
    body::Body,
    extract::{Path as AxumPath, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::Response,
    routing::{get, post, put},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::Row;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use tokio::fs;
use uuid::Uuid;

use crate::{db::prompt_skills as prompt_skills_db, error::ApiError, state::AppState};

const PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY: &str = "promptSkillBuiltinState";
const PROMPT_SKILL_SCOPE_GLOBAL: &str = "global";
const PROMPT_SKILL_SCOPE_AGENT_SPECIFIC: &str = "agent_specific";
const PROMPT_SKILL_RUNTIME_SOURCE: &str = "rust_prompt_effective_snapshot";
const PROMPT_SKILL_AGENT_KEYS: &[&str] = &[
    "recon",
    "business_logic_recon",
    "analysis",
    "business_logic_analysis",
    "verification",
];
const SKILL_FALLBACK_CATALOG: &[(&str, &str, &str)] = &[(
    "scan-core-fallback",
    "Scan Core Fallback",
    "Rust migration fallback skill entry.",
)];
const PROMPT_SKILLS_FILE_NAME: &str = "rust-prompt-skills.json";
const BUILTIN_PROMPT_STATE_FILE_NAME: &str = "rust-builtin-prompt-skill-state.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PromptSkillRecord {
    id: String,
    name: String,
    content: String,
    scope: String,
    agent_key: Option<String>,
    is_active: bool,
    created_at: String,
    updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct SkillCatalogResponse {
    enabled: bool,
    total: usize,
    limit: usize,
    offset: usize,
    supported_agent_keys: Vec<String>,
    items: Vec<SkillCatalogItem>,
    error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct SkillCatalogItem {
    skill_id: String,
    tool_type: String,
    tool_id: String,
    name: String,
    namespace: String,
    summary: String,
    category: String,
    capabilities: Vec<String>,
    entrypoint: String,
    aliases: Vec<String>,
    has_scripts: bool,
    has_bin: bool,
    has_assets: bool,
    status_label: String,
    is_enabled: bool,
    is_available: bool,
    resource_kind_label: String,
    detail_supported: bool,
    agent_key: Option<String>,
    agent_label: Option<String>,
    scope: Option<String>,
    display_name: Option<String>,
    content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    source: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    selection_label: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    runtime_ready: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    load_mode: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct PromptSkillListResponse {
    enabled: bool,
    total: usize,
    limit: usize,
    offset: usize,
    supported_agent_keys: Vec<String>,
    builtin_items: Vec<BuiltinPromptSkillItem>,
    items: Vec<PromptSkillRecord>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct BuiltinPromptSkillItem {
    agent_key: String,
    content: String,
    is_active: bool,
    agent_label: Option<String>,
    display_name: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct SkillResourceDetailResponse {
    tool_type: String,
    tool_id: String,
    name: String,
    summary: String,
    status_label: String,
    is_enabled: bool,
    is_available: bool,
    resource_kind_label: String,
    detail_supported: bool,
    namespace: String,
    entrypoint: Option<String>,
    agent_key: Option<String>,
    scope: Option<String>,
    content: Option<String>,
    is_builtin: Option<bool>,
    can_toggle: Option<bool>,
    can_edit: Option<bool>,
    can_delete: Option<bool>,
    scan_core_detail: Option<SkillDetailResponse>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct SkillDetailResponse {
    enabled: bool,
    skill_id: String,
    name: String,
    namespace: String,
    summary: String,
    category: String,
    goal: String,
    task_list: Vec<String>,
    input_checklist: Vec<String>,
    example_input: String,
    pitfalls: Vec<String>,
    sample_prompts: Vec<String>,
    entrypoint: String,
    mirror_dir: String,
    source_root: String,
    source_dir: String,
    source_skill_md: String,
    aliases: Vec<String>,
    has_scripts: bool,
    has_bin: bool,
    has_assets: bool,
    files_count: usize,
    workflow_content: Option<String>,
    workflow_truncated: Option<bool>,
    workflow_error: Option<String>,
    test_supported: bool,
    test_mode: String,
    test_reason: Option<String>,
    default_test_project_name: String,
    tool_test_preset: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    display_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    source: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    agent_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    runtime_ready: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    load_mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    effective_content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    prompt_sources: Option<Vec<PromptSourceDetail>>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct PromptSourceDetail {
    source: String,
    name: Option<String>,
    scope: Option<String>,
    content: String,
}

#[derive(Debug, Clone)]
struct PromptEffectiveSkill {
    skill_id: String,
    name: String,
    display_name: String,
    summary: String,
    selection_label: String,
    runtime_ready: bool,
    reason: String,
    effective_content: String,
    prompt_sources: Vec<PromptSourceDetail>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct PromptSkillRuntimeSnapshot {
    source: String,
    requested: bool,
    enabled: bool,
    reason: String,
    agent_keys: Vec<String>,
    effective_by_agent: BTreeMap<String, PromptEffectiveRuntimeEntry>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
struct PromptEffectiveRuntimeEntry {
    runtime_ready: bool,
    reason: String,
    effective_content: String,
    prompt_sources: Vec<PromptSourceDetail>,
}

#[derive(Debug, Clone, Deserialize)]
struct SkillCatalogQuery {
    q: Option<String>,
    namespace: Option<String>,
    limit: Option<usize>,
    offset: Option<usize>,
    resource_mode: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct PromptSkillQuery {
    scope: Option<String>,
    agent_key: Option<String>,
    is_active: Option<bool>,
    limit: Option<usize>,
    offset: Option<usize>,
}

#[derive(Debug, Clone, Deserialize)]
struct PromptSkillCreateRequest {
    name: String,
    content: String,
    scope: String,
    agent_key: Option<String>,
    is_active: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
struct PromptSkillUpdateRequest {
    name: Option<String>,
    content: Option<String>,
    scope: Option<String>,
    agent_key: Option<String>,
    is_active: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
struct PromptSkillBuiltinUpdateRequest {
    is_active: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct SkillTestRequest {
    prompt: String,
    max_iterations: Option<u32>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/catalog", get(get_skill_catalog))
        .route(
            "/prompt-skills",
            get(list_prompt_skills).post(create_prompt_skill),
        )
        .route(
            "/prompt-skills/builtin/{agent_key}",
            put(update_builtin_prompt_skill),
        )
        .route(
            "/prompt-skills/{prompt_skill_id}",
            put(update_prompt_skill).delete(delete_prompt_skill),
        )
        .route("/{skill_id}", get(get_skill_detail))
        .route(
            "/resources/{tool_type}/{tool_id}",
            get(get_skill_resource_detail),
        )
        .route("/{skill_id}/test", post(run_skill_test))
        .route("/{skill_id}/tool-test", post(run_structured_tool_test))
}

async fn get_skill_catalog(
    State(state): State<AppState>,
    Query(query): Query<SkillCatalogQuery>,
) -> Result<Json<SkillCatalogResponse>, ApiError> {
    let mut items = scan_core_catalog_items()?;
    if query.resource_mode.as_deref() == Some("external_tools") {
        let prompt_payload = prompt_skill_payload(&state, None).await?;
        items.extend(
            prompt_payload
                .builtin_items
                .iter()
                .cloned()
                .map(skill_catalog_from_builtin),
        );
        items.extend(
            prompt_payload
                .items
                .iter()
                .cloned()
                .map(skill_catalog_from_custom_prompt),
        );
    } else {
        let prompt_skills = load_prompt_skills(&state).await?;
        let builtin_state = load_builtin_prompt_state(&state).await?;
        items.extend(prompt_effective_catalog_items(
            &prompt_skills,
            &builtin_state,
        )?);
    }

    let keyword = query.q.unwrap_or_default().trim().to_lowercase();
    let namespace_filter = query.namespace.unwrap_or_default().trim().to_lowercase();
    let filtered: Vec<SkillCatalogItem> = items
        .into_iter()
        .filter(|item| {
            let namespace_ok =
                namespace_filter.is_empty() || item.namespace.to_lowercase() == namespace_filter;
            let keyword_ok = keyword.is_empty()
                || format!("{} {} {}", item.name, item.summary, item.tool_id)
                    .to_lowercase()
                    .contains(&keyword);
            namespace_ok && keyword_ok
        })
        .collect();

    let total = filtered.len();
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(200);
    let paged: Vec<SkillCatalogItem> = filtered.into_iter().skip(offset).take(limit).collect();

    Ok(Json(SkillCatalogResponse {
        enabled: true,
        total,
        limit,
        offset,
        supported_agent_keys: prompt_agent_keys(),
        items: paged,
        error: None,
    }))
}

async fn list_prompt_skills(
    State(state): State<AppState>,
    Query(query): Query<PromptSkillQuery>,
) -> Result<Json<PromptSkillListResponse>, ApiError> {
    let payload = prompt_skill_payload(&state, Some(query)).await?;
    Ok(Json(payload))
}

async fn create_prompt_skill(
    State(state): State<AppState>,
    Json(request): Json<PromptSkillCreateRequest>,
) -> Result<Json<PromptSkillRecord>, ApiError> {
    let scope = normalize_scope(&request.scope, request.agent_key.as_deref())?;
    let now = now_rfc3339();
    let record = PromptSkillRecord {
        id: Uuid::new_v4().to_string(),
        name: request.name.trim().to_string(),
        content: request.content.trim().to_string(),
        scope: scope.0,
        agent_key: scope.1,
        is_active: request.is_active.unwrap_or(true),
        created_at: now.clone(),
        updated_at: Some(now),
    };
    if state.db_pool.is_some() {
        prompt_skills_db::create_prompt_skill(&state, &record.clone().into())
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    } else {
        save_prompt_skill(&state, record.clone()).await?;
    }
    Ok(Json(record))
}

async fn update_prompt_skill(
    State(state): State<AppState>,
    AxumPath(prompt_skill_id): AxumPath<String>,
    Json(request): Json<PromptSkillUpdateRequest>,
) -> Result<Json<PromptSkillRecord>, ApiError> {
    let existing = if state.db_pool.is_some() {
        prompt_skills_db::load_prompt_skill(&state, &prompt_skill_id)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?
            .map(Into::into)
            .ok_or_else(|| ApiError::NotFound("prompt skill not found".to_string()))?
    } else {
        let items = load_prompt_skills(&state).await?;
        items
            .into_iter()
            .find(|item| item.id == prompt_skill_id)
            .ok_or_else(|| ApiError::NotFound("prompt skill not found".to_string()))?
    };
    let next_scope = normalize_scope(
        request.scope.as_deref().unwrap_or(&existing.scope),
        request
            .agent_key
            .as_deref()
            .or(existing.agent_key.as_deref()),
    )?;
    let mut updated = existing.clone();
    if let Some(name) = request.name.as_ref() {
        updated.name = name.trim().to_string();
    }
    if let Some(content) = request.content.as_ref() {
        updated.content = content.trim().to_string();
    }
    if let Some(is_active) = request.is_active {
        updated.is_active = is_active;
    }
    updated.scope = next_scope.0;
    updated.agent_key = next_scope.1;
    updated.updated_at = Some(now_rfc3339());
    if state.db_pool.is_some() {
        prompt_skills_db::update_prompt_skill(&state, &updated.clone().into())
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?
            .ok_or_else(|| ApiError::NotFound("prompt skill not found".to_string()))?;
    } else {
        let mut items = load_prompt_skills(&state).await?;
        let index = items
            .iter()
            .position(|item| item.id == prompt_skill_id)
            .ok_or_else(|| ApiError::NotFound("prompt skill not found".to_string()))?;
        items[index] = updated.clone();
        store_prompt_skills(&state, &items).await?;
        sync_prompt_skills_mirror(&state, &items).await?;
    }
    Ok(Json(updated))
}

async fn delete_prompt_skill(
    State(state): State<AppState>,
    AxumPath(prompt_skill_id): AxumPath<String>,
) -> Result<Json<Value>, ApiError> {
    if state.db_pool.is_some() {
        let deleted = prompt_skills_db::delete_prompt_skill(&state, &prompt_skill_id)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        if !deleted {
            return Err(ApiError::NotFound("prompt skill not found".to_string()));
        }
    } else {
        let mut items = load_prompt_skills(&state).await?;
        let before = items.len();
        items.retain(|item| item.id != prompt_skill_id);
        if items.len() == before {
            return Err(ApiError::NotFound("prompt skill not found".to_string()));
        }
        store_prompt_skills(&state, &items).await?;
        sync_prompt_skills_mirror(&state, &items).await?;
    }
    Ok(Json(json!({ "deleted": true })))
}

async fn update_builtin_prompt_skill(
    State(state): State<AppState>,
    AxumPath(agent_key): AxumPath<String>,
    Json(request): Json<PromptSkillBuiltinUpdateRequest>,
) -> Result<Json<BuiltinPromptSkillItem>, ApiError> {
    ensure_valid_agent_key(&agent_key)?;
    if state.db_pool.is_some() {
        prompt_skills_db::set_builtin_prompt_state(
            &state,
            &agent_key,
            request.is_active,
            PROMPT_SKILL_AGENT_KEYS,
        )
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    } else {
        let mut builtin_state = load_builtin_prompt_state(&state).await?;
        builtin_state.insert(agent_key.clone(), request.is_active);
        store_builtin_prompt_state(&state, &builtin_state).await?;
        sync_builtin_prompt_state_mirror(&state, &builtin_state).await?;
    }
    Ok(Json(BuiltinPromptSkillItem {
        agent_key: agent_key.clone(),
        content: builtin_prompt_templates()
            .get(agent_key.as_str())
            .cloned()
            .unwrap_or_default(),
        is_active: request.is_active,
        agent_label: Some(agent_label(&agent_key).to_string()),
        display_name: Some(format!("Builtin Prompt · {}", agent_label(&agent_key))),
    }))
}

async fn get_skill_detail(
    State(state): State<AppState>,
    AxumPath(skill_id): AxumPath<String>,
) -> Result<Json<SkillDetailResponse>, ApiError> {
    let detail = if let Some(agent_key) = parse_prompt_effective_skill_id(&skill_id) {
        let prompt_skills = load_prompt_skills(&state).await?;
        let builtin_state = load_builtin_prompt_state(&state).await?;
        prompt_effective_skill_detail(agent_key, &prompt_skills, &builtin_state)?
    } else {
        scan_core_skill_detail(&skill_id)?
    };
    Ok(Json(detail))
}

async fn get_skill_resource_detail(
    State(state): State<AppState>,
    AxumPath((tool_type, tool_id)): AxumPath<(String, String)>,
) -> Result<Json<SkillResourceDetailResponse>, ApiError> {
    match tool_type.as_str() {
        "skill" => {
            let detail = scan_core_skill_detail(&tool_id)?;
            Ok(Json(SkillResourceDetailResponse {
                tool_type,
                tool_id: tool_id.clone(),
                name: detail.name.clone(),
                summary: detail.summary.clone(),
                status_label: "启用".to_string(),
                is_enabled: true,
                is_available: true,
                resource_kind_label: "Scan Core".to_string(),
                detail_supported: true,
                namespace: detail.namespace.clone(),
                entrypoint: Some(detail.entrypoint.clone()),
                agent_key: None,
                scope: None,
                content: None,
                is_builtin: Some(false),
                can_toggle: Some(false),
                can_edit: Some(false),
                can_delete: Some(false),
                scan_core_detail: Some(detail),
            }))
        }
        "prompt-builtin" => {
            ensure_valid_agent_key(&tool_id)?;
            let state_map = load_builtin_prompt_state(&state).await?;
            Ok(Json(SkillResourceDetailResponse {
                tool_type,
                tool_id: tool_id.clone(),
                name: format!("Builtin Prompt · {}", agent_label(&tool_id)),
                summary: builtin_prompt_templates()
                    .get(tool_id.as_str())
                    .cloned()
                    .unwrap_or_default(),
                status_label: if state_map.get(&tool_id).copied().unwrap_or(true) {
                    "启用".to_string()
                } else {
                    "停用".to_string()
                },
                is_enabled: state_map.get(&tool_id).copied().unwrap_or(true),
                is_available: true,
                resource_kind_label: "Builtin Prompt Skill".to_string(),
                detail_supported: true,
                namespace: "prompt-skill".to_string(),
                entrypoint: None,
                agent_key: Some(tool_id.clone()),
                scope: None,
                content: builtin_prompt_templates().get(tool_id.as_str()).cloned(),
                is_builtin: Some(true),
                can_toggle: Some(true),
                can_edit: Some(false),
                can_delete: Some(false),
                scan_core_detail: None,
            }))
        }
        "prompt-custom" => {
            let items = load_prompt_skills(&state).await?;
            let item = items
                .into_iter()
                .find(|item| item.id == tool_id)
                .ok_or_else(|| ApiError::NotFound("prompt skill not found".to_string()))?;
            Ok(Json(SkillResourceDetailResponse {
                tool_type,
                tool_id: item.id.clone(),
                name: item.name.clone(),
                summary: item.content.clone(),
                status_label: if item.is_active { "启用" } else { "停用" }.to_string(),
                is_enabled: item.is_active,
                is_available: true,
                resource_kind_label: "Custom Prompt Skill".to_string(),
                detail_supported: true,
                namespace: "prompt-skill".to_string(),
                entrypoint: None,
                agent_key: item.agent_key.clone(),
                scope: Some(item.scope.clone()),
                content: Some(item.content.clone()),
                is_builtin: Some(false),
                can_toggle: Some(true),
                can_edit: Some(true),
                can_delete: Some(true),
                scan_core_detail: None,
            }))
        }
        _ => Err(ApiError::NotFound("resource type not found".to_string())),
    }
}

async fn run_skill_test(
    AxumPath(skill_id): AxumPath<String>,
    Json(request): Json<SkillTestRequest>,
) -> Result<Response, ApiError> {
    let _ = scan_core_skill_detail(&skill_id)?;
    let result = json!({
        "skill_id": skill_id,
        "final_text": format!("Simulated skill test for prompt: {}", request.prompt),
        "project_name": "libplist",
        "test_mode": "single_skill_strict",
        "default_test_project_name": "libplist",
        "project_root": "/tmp/libplist",
        "tool_name": null,
        "target_function": null,
        "resolved_file_path": null,
        "resolved_line_start": null,
        "resolved_line_end": null,
        "runner_image": null,
        "input_payload": { "max_iterations": request.max_iterations.unwrap_or(4) },
        "cleanup": {
            "success": true,
            "temp_dir": "/tmp/libplist",
            "error": null
        }
    });
    Ok(sse_response(vec![
        json!({"type": "info", "message": "skill test started", "ts": now_ts()}),
        json!({"type": "result", "data": result, "ts": now_ts()}),
    ]))
}

async fn run_structured_tool_test(
    AxumPath(skill_id): AxumPath<String>,
    Json(payload): Json<Value>,
) -> Result<Response, ApiError> {
    let _ = scan_core_skill_detail(&skill_id)?;
    let result = json!({
        "skill_id": skill_id,
        "final_text": "Simulated structured tool test completed",
        "project_name": payload.get("project_name").and_then(Value::as_str).unwrap_or("libplist"),
        "test_mode": "structured_tool",
        "default_test_project_name": "libplist",
        "project_root": "/tmp/libplist",
        "tool_name": "structured_tool",
        "target_function": payload.get("function_name").and_then(Value::as_str),
        "resolved_file_path": payload.get("file_path").and_then(Value::as_str),
        "resolved_line_start": payload.get("line_start").and_then(Value::as_i64),
        "resolved_line_end": payload.get("line_end").and_then(Value::as_i64),
        "runner_image": null,
        "input_payload": payload,
        "cleanup": {
            "success": true,
            "temp_dir": "/tmp/libplist",
            "error": null
        }
    });
    Ok(sse_response(vec![
        json!({"type": "info", "message": "structured tool test started", "ts": now_ts()}),
        json!({"type": "result", "data": result, "ts": now_ts()}),
    ]))
}

fn sse_response(payloads: Vec<Value>) -> Response {
    let body = payloads
        .into_iter()
        .map(|payload| format!("data: {}\n\n", payload))
        .collect::<String>();
    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/event-stream"),
    );
    response
}

async fn prompt_skill_payload(
    state: &AppState,
    query: Option<PromptSkillQuery>,
) -> Result<PromptSkillListResponse, ApiError> {
    let items = load_prompt_skills(state).await?;
    let builtin_state = load_builtin_prompt_state(state).await?;
    let limit = query.as_ref().and_then(|item| item.limit).unwrap_or(500);
    let offset = query.as_ref().and_then(|item| item.offset).unwrap_or(0);
    let filtered_items: Vec<PromptSkillRecord> = items
        .into_iter()
        .filter(|item| {
            if let Some(query) = query.as_ref() {
                if let Some(scope) = query.scope.as_ref() {
                    if item.scope != *scope {
                        return false;
                    }
                }
                if let Some(agent_key) = query.agent_key.as_ref() {
                    if item.agent_key.as_deref() != Some(agent_key.as_str()) {
                        return false;
                    }
                }
                if let Some(is_active) = query.is_active {
                    if item.is_active != is_active {
                        return false;
                    }
                }
            }
            true
        })
        .collect();
    let total = filtered_items.len();
    let filtered_items: Vec<PromptSkillRecord> = filtered_items
        .into_iter()
        .skip(offset)
        .take(limit)
        .collect();

    let builtin_items = PROMPT_SKILL_AGENT_KEYS
        .iter()
        .map(|agent_key| BuiltinPromptSkillItem {
            agent_key: (*agent_key).to_string(),
            content: builtin_prompt_templates()
                .get(*agent_key)
                .cloned()
                .unwrap_or_default(),
            is_active: builtin_state.get(*agent_key).copied().unwrap_or(true),
            agent_label: Some(agent_label(agent_key).to_string()),
            display_name: Some(format!("Builtin Prompt · {}", agent_label(agent_key))),
        })
        .collect::<Vec<_>>();

    Ok(PromptSkillListResponse {
        enabled: true,
        total,
        limit,
        offset,
        supported_agent_keys: prompt_agent_keys(),
        builtin_items,
        items: filtered_items,
    })
}

async fn load_prompt_skills(state: &AppState) -> Result<Vec<PromptSkillRecord>, ApiError> {
    if let Some(pool) = &state.db_pool {
        let _ = pool;
        return prompt_skills_db::load_prompt_skills(state)
            .await
            .map(|items| items.into_iter().map(Into::into).collect())
            .map_err(|error| ApiError::Internal(error.to_string()));
    }

    let _guard = state.file_store_lock.lock().await;
    let path = prompt_skills_file_path(state);
    let raw = match fs::read_to_string(&path).await {
        Ok(raw) => raw,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(ApiError::Internal(error.to_string())),
    };
    serde_json::from_str(&raw).map_err(|error| ApiError::Internal(error.to_string()))
}

async fn save_prompt_skill(state: &AppState, record: PromptSkillRecord) -> Result<(), ApiError> {
    let mut items = load_prompt_skills(state).await?;
    items.push(record);
    store_prompt_skills(state, &items).await?;
    sync_prompt_skills_mirror(state, &items).await?;
    Ok(())
}

async fn store_prompt_skills(
    state: &AppState,
    items: &[PromptSkillRecord],
) -> Result<(), ApiError> {
    if state.db_pool.is_some() {
        return Ok(());
    }
    let _guard = state.file_store_lock.lock().await;
    let path = prompt_skills_file_path(state);
    ensure_file_storage_root(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    fs::write(
        &path,
        serde_json::to_vec(items).map_err(|error| ApiError::Internal(error.to_string()))?,
    )
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;
    Ok(())
}

async fn sync_prompt_skills_mirror(
    state: &AppState,
    items: &[PromptSkillRecord],
) -> Result<(), ApiError> {
    let Some(pool) = &state.db_pool else {
        return Ok(());
    };
    let bootstrap_user_id: Option<String> =
        sqlx::query_scalar("select id from users order by created_at asc limit 1")
            .fetch_optional(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    let Some(user_id) = bootstrap_user_id else {
        return Ok(());
    };
    sqlx::query("delete from prompt_skills where user_id = $1")
        .bind(&user_id)
        .execute(pool)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    for item in items {
        sqlx::query(
            r#"
            insert into prompt_skills (id, user_id, name, content, scope, agent_key, is_active)
            values ($1, $2, $3, $4, $5, $6, $7)
            "#,
        )
        .bind(&item.id)
        .bind(&user_id)
        .bind(&item.name)
        .bind(&item.content)
        .bind(&item.scope)
        .bind(&item.agent_key)
        .bind(item.is_active)
        .execute(pool)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    }
    Ok(())
}

async fn load_builtin_prompt_state(state: &AppState) -> Result<BTreeMap<String, bool>, ApiError> {
    if let Some(pool) = &state.db_pool {
        let _ = pool;
        return prompt_skills_db::load_builtin_prompt_state(state, PROMPT_SKILL_AGENT_KEYS)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()));
    }

    let _guard = state.file_store_lock.lock().await;
    let path = builtin_prompt_state_file_path(state);
    let raw = match fs::read_to_string(&path).await {
        Ok(raw) => raw,
        Err(error) if error.kind() == ErrorKind::NotFound => {
            return Ok(default_builtin_prompt_state())
        }
        Err(error) => return Err(ApiError::Internal(error.to_string())),
    };
    let parsed: BTreeMap<String, bool> =
        serde_json::from_str(&raw).map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut state_map = default_builtin_prompt_state();
    for (key, value) in parsed {
        state_map.insert(key, value);
    }
    Ok(state_map)
}

async fn store_builtin_prompt_state(
    state: &AppState,
    values: &BTreeMap<String, bool>,
) -> Result<(), ApiError> {
    if state.db_pool.is_some() {
        return Ok(());
    }
    let _guard = state.file_store_lock.lock().await;
    let path = builtin_prompt_state_file_path(state);
    ensure_file_storage_root(state)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    fs::write(
        &path,
        serde_json::to_vec(values).map_err(|error| ApiError::Internal(error.to_string()))?,
    )
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;
    Ok(())
}

async fn sync_builtin_prompt_state_mirror(
    state: &AppState,
    values: &BTreeMap<String, bool>,
) -> Result<(), ApiError> {
    let Some(pool) = &state.db_pool else {
        return Ok(());
    };
    let bootstrap_user_id: Option<String> =
        sqlx::query_scalar("select id from users order by created_at asc limit 1")
            .fetch_optional(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    let Some(user_id) = bootstrap_user_id else {
        return Ok(());
    };
    let row =
        sqlx::query("select id, llm_config, other_config from user_configs where user_id = $1")
            .bind(&user_id)
            .fetch_optional(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    let mut other_config = row
        .as_ref()
        .and_then(|row| row.try_get::<String, _>("other_config").ok())
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .unwrap_or_else(|| json!({}));
    if !other_config.is_object() {
        other_config = json!({});
    }
    other_config[PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY] = json!(values);
    let llm_config = row
        .as_ref()
        .and_then(|row| row.try_get::<String, _>("llm_config").ok())
        .unwrap_or_else(|| "{}".to_string());

    match row {
        Some(row) => {
            let config_id: String = row
                .try_get("id")
                .unwrap_or_else(|_| Uuid::new_v4().to_string());
            sqlx::query("update user_configs set other_config = $1, llm_config = $2, updated_at = now() where id = $3")
                .bind(other_config.to_string())
                .bind(llm_config)
                .bind(config_id)
                .execute(pool)
                .await
                .map_err(|error| ApiError::Internal(error.to_string()))?;
        }
        None => {
            sqlx::query(
                "insert into user_configs (id, user_id, llm_config, other_config) values ($1, $2, $3, $4)",
            )
            .bind(Uuid::new_v4().to_string())
            .bind(user_id)
            .bind("{}")
            .bind(other_config.to_string())
            .execute(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        }
    }
    Ok(())
}

fn scan_core_catalog_items() -> Result<Vec<SkillCatalogItem>, ApiError> {
    let discovered = discover_scan_core_skills();
    let items = if discovered.is_empty() {
        SKILL_FALLBACK_CATALOG
            .iter()
            .map(|(skill_id, name, summary)| SkillCatalogItem {
                skill_id: (*skill_id).to_string(),
                tool_type: "skill".to_string(),
                tool_id: (*skill_id).to_string(),
                name: (*name).to_string(),
                namespace: "scan-core".to_string(),
                summary: (*summary).to_string(),
                category: "fallback".to_string(),
                capabilities: vec![],
                entrypoint: "SKILL.md".to_string(),
                aliases: vec![],
                has_scripts: false,
                has_bin: false,
                has_assets: false,
                status_label: "启用".to_string(),
                is_enabled: true,
                is_available: true,
                resource_kind_label: "Scan Core".to_string(),
                detail_supported: true,
                agent_key: None,
                agent_label: None,
                scope: None,
                display_name: Some((*name).to_string()),
                content: None,
                kind: None,
                source: None,
                selection_label: None,
                runtime_ready: None,
                reason: None,
                load_mode: None,
            })
            .collect()
    } else {
        discovered
    };
    Ok(items)
}

fn discover_scan_core_skills() -> Vec<SkillCatalogItem> {
    let mut roots = Vec::new();
    if let Ok(codex_home) = env::var("CODEX_HOME") {
        roots.push(PathBuf::from(codex_home).join("skills"));
    }
    if let Ok(home) = env::var("HOME") {
        roots.push(PathBuf::from(home).join(".codex/skills"));
    }
    let mut items = Vec::new();
    for root in roots {
        let entries = match std::fs::read_dir(&root) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let skill_md = path.join("SKILL.md");
            if !skill_md.exists() {
                continue;
            }
            let skill_id = path
                .file_name()
                .and_then(|item| item.to_str())
                .unwrap_or("skill")
                .to_string();
            let raw = std::fs::read_to_string(&skill_md).unwrap_or_default();
            let summary = raw
                .lines()
                .find(|line| {
                    !line.trim().is_empty() && !line.starts_with("---") && !line.starts_with('#')
                })
                .map(str::trim)
                .unwrap_or("Local scan-core skill")
                .to_string();
            items.push(SkillCatalogItem {
                skill_id: skill_id.clone(),
                tool_type: "skill".to_string(),
                tool_id: skill_id.clone(),
                name: skill_id.clone(),
                namespace: "scan-core".to_string(),
                summary,
                category: "skill".to_string(),
                capabilities: vec![],
                entrypoint: skill_md.display().to_string(),
                aliases: vec![],
                has_scripts: path.join("scripts").exists(),
                has_bin: path.join("bin").exists(),
                has_assets: path.join("assets").exists(),
                status_label: "启用".to_string(),
                is_enabled: true,
                is_available: true,
                resource_kind_label: "Scan Core".to_string(),
                detail_supported: true,
                agent_key: None,
                agent_label: None,
                scope: None,
                display_name: Some(skill_id),
                content: None,
                kind: None,
                source: None,
                selection_label: None,
                runtime_ready: None,
                reason: None,
                load_mode: None,
            });
        }
        if !items.is_empty() {
            break;
        }
    }
    items
}

fn scan_core_skill_detail(skill_id: &str) -> Result<SkillDetailResponse, ApiError> {
    let catalog_item = scan_core_catalog_items()?
        .into_iter()
        .find(|item| item.skill_id == skill_id)
        .ok_or_else(|| ApiError::NotFound("skill not found".to_string()))?;
    let entrypoint = catalog_item.entrypoint.clone();
    let workflow_content = std::fs::read_to_string(&entrypoint).ok();
    Ok(SkillDetailResponse {
        enabled: true,
        skill_id: skill_id.to_string(),
        name: catalog_item.name.clone(),
        namespace: catalog_item.namespace.clone(),
        summary: catalog_item.summary.clone(),
        category: catalog_item.category.clone(),
        goal: "Rust-owned skill metadata surface".to_string(),
        task_list: vec!["Inspect skill".to_string(), "Run smoke test".to_string()],
        input_checklist: vec!["Provide a natural language prompt".to_string()],
        example_input: "scan the repo".to_string(),
        pitfalls: vec!["This is a migration-safe placeholder implementation.".to_string()],
        sample_prompts: vec!["run a smoke test".to_string()],
        entrypoint: entrypoint.clone(),
        mirror_dir: String::new(),
        source_root: String::new(),
        source_dir: Path::new(&entrypoint)
            .parent()
            .map(|path| path.display().to_string())
            .unwrap_or_default(),
        source_skill_md: entrypoint.clone(),
        aliases: vec![],
        has_scripts: false,
        has_bin: false,
        has_assets: false,
        files_count: usize::from(workflow_content.is_some()),
        workflow_content,
        workflow_truncated: Some(false),
        workflow_error: None,
        test_supported: true,
        test_mode: "single_skill_strict".to_string(),
        test_reason: None,
        default_test_project_name: "libplist".to_string(),
        tool_test_preset: Some(json!({
            "project_name": "libplist",
            "file_path": "src/main.c",
            "function_name": "main",
            "line_start": 1,
            "line_end": 1,
            "tool_input": {}
        })),
        display_name: None,
        kind: None,
        source: None,
        agent_key: None,
        runtime_ready: None,
        reason: None,
        load_mode: None,
        effective_content: None,
        prompt_sources: None,
    })
}

fn skill_catalog_from_builtin(item: BuiltinPromptSkillItem) -> SkillCatalogItem {
    SkillCatalogItem {
        skill_id: format!("builtin-{}", item.agent_key),
        tool_type: "prompt-builtin".to_string(),
        tool_id: item.agent_key.clone(),
        name: format!("Builtin Prompt · {}", agent_label(&item.agent_key)),
        namespace: "prompt-skill".to_string(),
        summary: item.content.clone(),
        category: "prompt".to_string(),
        capabilities: vec![],
        entrypoint: String::new(),
        aliases: vec![],
        has_scripts: false,
        has_bin: false,
        has_assets: false,
        status_label: if item.is_active { "启用" } else { "停用" }.to_string(),
        is_enabled: item.is_active,
        is_available: true,
        resource_kind_label: "Builtin Prompt Skill".to_string(),
        detail_supported: true,
        agent_key: Some(item.agent_key.clone()),
        agent_label: item.agent_label.clone(),
        scope: None,
        display_name: item.display_name.clone(),
        content: Some(item.content),
        kind: None,
        source: None,
        selection_label: None,
        runtime_ready: None,
        reason: None,
        load_mode: None,
    }
}

fn skill_catalog_from_custom_prompt(item: PromptSkillRecord) -> SkillCatalogItem {
    SkillCatalogItem {
        skill_id: item.id.clone(),
        tool_type: "prompt-custom".to_string(),
        tool_id: item.id.clone(),
        name: item.name.clone(),
        namespace: "prompt-skill".to_string(),
        summary: item.content.clone(),
        category: "prompt".to_string(),
        capabilities: vec![],
        entrypoint: String::new(),
        aliases: vec![],
        has_scripts: false,
        has_bin: false,
        has_assets: false,
        status_label: if item.is_active { "启用" } else { "停用" }.to_string(),
        is_enabled: item.is_active,
        is_available: true,
        resource_kind_label: "Custom Prompt Skill".to_string(),
        detail_supported: true,
        agent_key: item.agent_key.clone(),
        agent_label: item
            .agent_key
            .as_ref()
            .map(|value| agent_label(value).to_string()),
        scope: Some(item.scope.clone()),
        display_name: Some(item.name.clone()),
        content: Some(item.content.clone()),
        kind: None,
        source: None,
        selection_label: None,
        runtime_ready: None,
        reason: None,
        load_mode: None,
    }
}

fn prompt_effective_catalog_items(
    custom_prompt_skills: &[PromptSkillRecord],
    builtin_state: &BTreeMap<String, bool>,
) -> Result<Vec<SkillCatalogItem>, ApiError> {
    PROMPT_SKILL_AGENT_KEYS
        .iter()
        .map(|agent_key| {
            let effective =
                build_prompt_effective_skill(agent_key, custom_prompt_skills, builtin_state)?;
            Ok(SkillCatalogItem {
                skill_id: effective.skill_id.clone(),
                tool_type: String::new(),
                tool_id: String::new(),
                name: effective.name.clone(),
                namespace: "prompt".to_string(),
                summary: effective.summary.clone(),
                category: "prompt".to_string(),
                capabilities: vec![],
                entrypoint: String::new(),
                aliases: vec![],
                has_scripts: false,
                has_bin: false,
                has_assets: false,
                status_label: if effective.runtime_ready {
                    "就绪".to_string()
                } else {
                    "未就绪".to_string()
                },
                is_enabled: effective.runtime_ready,
                is_available: true,
                resource_kind_label: "Prompt Effective Skill".to_string(),
                detail_supported: true,
                agent_key: Some((*agent_key).to_string()),
                agent_label: Some(agent_label(agent_key).to_string()),
                scope: None,
                display_name: Some(effective.display_name.clone()),
                content: None,
                kind: Some("prompt".to_string()),
                source: Some("prompt_effective".to_string()),
                selection_label: Some(effective.selection_label.clone()),
                runtime_ready: Some(effective.runtime_ready),
                reason: Some(effective.reason.clone()),
                load_mode: Some("summary_only".to_string()),
            })
        })
        .collect()
}

fn prompt_effective_skill_detail(
    agent_key: &str,
    custom_prompt_skills: &[PromptSkillRecord],
    builtin_state: &BTreeMap<String, bool>,
) -> Result<SkillDetailResponse, ApiError> {
    let effective = build_prompt_effective_skill(agent_key, custom_prompt_skills, builtin_state)?;
    Ok(SkillDetailResponse {
        enabled: true,
        skill_id: effective.skill_id.clone(),
        name: effective.name.clone(),
        namespace: "prompt".to_string(),
        summary: effective.summary.clone(),
        category: "prompt".to_string(),
        goal: "Use the runtime-effective prompt for the selected agent.".to_string(),
        task_list: vec![
            "Review the effective prompt sources".to_string(),
            "Use the merged prompt during agent execution".to_string(),
        ],
        input_checklist: vec!["Select one supported prompt agent key".to_string()],
        example_input: format!("load {}", effective.skill_id),
        pitfalls: vec![
            "Inactive or empty custom prompt rows are ignored.".to_string(),
            "Builtin prompt state still mirrors into legacy user_configs.other_config.".to_string(),
        ],
        sample_prompts: vec![format!("show {}", effective.skill_id)],
        entrypoint: String::new(),
        mirror_dir: String::new(),
        source_root: String::new(),
        source_dir: String::new(),
        source_skill_md: String::new(),
        aliases: vec![],
        has_scripts: false,
        has_bin: false,
        has_assets: false,
        files_count: 0,
        workflow_content: None,
        workflow_truncated: Some(false),
        workflow_error: None,
        test_supported: false,
        test_mode: "prompt_effective".to_string(),
        test_reason: Some(
            "prompt-effective entries do not expose the scan-core SSE test contract".to_string(),
        ),
        default_test_project_name: "libplist".to_string(),
        tool_test_preset: None,
        display_name: Some(effective.display_name),
        kind: Some("prompt".to_string()),
        source: Some("prompt_effective".to_string()),
        agent_key: Some(agent_key.to_string()),
        runtime_ready: Some(effective.runtime_ready),
        reason: Some(effective.reason),
        load_mode: Some("full".to_string()),
        effective_content: Some(effective.effective_content),
        prompt_sources: Some(effective.prompt_sources),
    })
}

pub(crate) async fn prompt_skill_runtime_snapshot(
    state: &AppState,
    requested: bool,
) -> Result<Value, ApiError> {
    let agent_keys = prompt_agent_keys();
    if !requested {
        return serde_json::to_value(PromptSkillRuntimeSnapshot {
            source: PROMPT_SKILL_RUNTIME_SOURCE.to_string(),
            requested: false,
            enabled: false,
            reason: "disabled_by_request".to_string(),
            agent_keys,
            effective_by_agent: BTreeMap::new(),
        })
        .map_err(|error| ApiError::Internal(error.to_string()));
    }

    let custom_prompt_skills = load_prompt_skills(state).await?;
    let builtin_state = load_builtin_prompt_state(state).await?;
    let mut effective_by_agent = BTreeMap::new();
    let mut enabled = false;

    for agent_key in PROMPT_SKILL_AGENT_KEYS {
        let effective =
            build_prompt_effective_skill(agent_key, &custom_prompt_skills, &builtin_state)?;
        enabled |= effective.runtime_ready;
        effective_by_agent.insert(
            (*agent_key).to_string(),
            PromptEffectiveRuntimeEntry {
                runtime_ready: effective.runtime_ready,
                reason: effective.reason,
                effective_content: effective.effective_content,
                prompt_sources: effective.prompt_sources,
            },
        );
    }

    serde_json::to_value(PromptSkillRuntimeSnapshot {
        source: PROMPT_SKILL_RUNTIME_SOURCE.to_string(),
        requested: true,
        enabled,
        reason: if enabled {
            "active_prompt_snapshot".to_string()
        } else {
            "no_active_prompt_sources".to_string()
        },
        agent_keys,
        effective_by_agent,
    })
    .map_err(|error| ApiError::Internal(error.to_string()))
}

fn build_prompt_effective_skill(
    agent_key: &str,
    custom_prompt_skills: &[PromptSkillRecord],
    builtin_state: &BTreeMap<String, bool>,
) -> Result<PromptEffectiveSkill, ApiError> {
    ensure_valid_agent_key(agent_key)?;

    let builtin_templates = builtin_prompt_templates();
    let mut fragments = Vec::new();
    let mut prompt_sources = Vec::new();
    let mut reason_parts = Vec::new();

    if builtin_state.get(agent_key).copied().unwrap_or(true) {
        if let Some(content) = builtin_templates
            .get(agent_key)
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
        {
            fragments.push(content.to_string());
            prompt_sources.push(PromptSourceDetail {
                source: "builtin_template".to_string(),
                name: Some(format!("Builtin Prompt · {}", agent_label(agent_key))),
                scope: None,
                content: content.to_string(),
            });
            reason_parts.push("builtin_template".to_string());
        }
    }

    let ordered_prompt_skills = sorted_prompt_skills_for_merge(custom_prompt_skills);

    let global_sources: Vec<PromptSourceDetail> = ordered_prompt_skills
        .iter()
        .filter(|item| item.is_active)
        .filter_map(|item| build_custom_prompt_source(item, Some(agent_key)))
        .filter(|item| item.source == "global_custom")
        .collect();
    if !global_sources.is_empty() {
        fragments.push(join_prompt_source_content(&global_sources));
        prompt_sources.extend(global_sources);
        reason_parts.push("global_custom".to_string());
    }

    let agent_specific_sources: Vec<PromptSourceDetail> = ordered_prompt_skills
        .iter()
        .filter(|item| item.is_active)
        .filter_map(|item| build_custom_prompt_source(item, Some(agent_key)))
        .filter(|item| item.source == "agent_specific_custom")
        .collect();
    if !agent_specific_sources.is_empty() {
        fragments.push(join_prompt_source_content(&agent_specific_sources));
        prompt_sources.extend(agent_specific_sources);
        reason_parts.push("agent_specific_custom".to_string());
    }

    let effective_content = fragments
        .into_iter()
        .filter(|fragment| !fragment.trim().is_empty())
        .collect::<Vec<_>>()
        .join("\n\n");
    let runtime_ready = !effective_content.trim().is_empty();
    let reason = if runtime_ready {
        reason_parts.join("+")
    } else {
        "no_active_prompt_sources".to_string()
    };
    let display_name = format!("Effective Prompt · {}", agent_label(agent_key));
    let summary = if runtime_ready {
        format!(
            "Effective prompt summary for {} using {} active source(s).",
            agent_label(agent_key),
            prompt_sources.len()
        )
    } else {
        format!("No active prompt sources for {}.", agent_label(agent_key))
    };

    Ok(PromptEffectiveSkill {
        skill_id: format!("prompt-{agent_key}@effective"),
        name: format!("prompt-{agent_key}@effective"),
        display_name,
        summary,
        selection_label: format!("prompt:{agent_key}:effective"),
        runtime_ready,
        reason,
        effective_content,
        prompt_sources,
    })
}

fn sorted_prompt_skills_for_merge(
    custom_prompt_skills: &[PromptSkillRecord],
) -> Vec<&PromptSkillRecord> {
    let mut ordered = custom_prompt_skills.iter().collect::<Vec<_>>();
    ordered.sort_by(|left, right| {
        prompt_skill_created_at_sort_key(left)
            .cmp(&prompt_skill_created_at_sort_key(right))
            .then_with(|| left.created_at.cmp(&right.created_at))
            .then_with(|| left.id.cmp(&right.id))
    });
    ordered
}

fn prompt_skill_created_at_sort_key(item: &PromptSkillRecord) -> Option<i128> {
    OffsetDateTime::parse(&item.created_at, &Rfc3339)
        .ok()
        .map(|value| {
            i128::from(value.unix_timestamp()) * 1_000_000_000 + i128::from(value.nanosecond())
        })
}

fn build_custom_prompt_source(
    item: &PromptSkillRecord,
    target_agent_key: Option<&str>,
) -> Option<PromptSourceDetail> {
    let content = render_custom_prompt_content(item)?;
    match item.scope.as_str() {
        PROMPT_SKILL_SCOPE_GLOBAL => Some(PromptSourceDetail {
            source: "global_custom".to_string(),
            name: Some(item.name.clone()),
            scope: Some(item.scope.clone()),
            content,
        }),
        PROMPT_SKILL_SCOPE_AGENT_SPECIFIC => {
            if item.agent_key.as_deref() != target_agent_key {
                return None;
            }
            Some(PromptSourceDetail {
                source: "agent_specific_custom".to_string(),
                name: Some(item.name.clone()),
                scope: Some(item.scope.clone()),
                content,
            })
        }
        _ => None,
    }
}

fn render_custom_prompt_content(item: &PromptSkillRecord) -> Option<String> {
    let content = item.content.trim();
    if content.is_empty() {
        return None;
    }
    let name = item.name.trim();
    Some(if name.is_empty() {
        content.to_string()
    } else {
        format!("[{name}] {content}")
    })
}

fn join_prompt_source_content(items: &[PromptSourceDetail]) -> String {
    items
        .iter()
        .map(|item| item.content.as_str())
        .filter(|content| !content.trim().is_empty())
        .collect::<Vec<_>>()
        .join("\n")
}

fn parse_prompt_effective_skill_id(skill_id: &str) -> Option<&str> {
    let agent_key = skill_id
        .strip_prefix("prompt-")?
        .strip_suffix("@effective")?;
    if ensure_valid_agent_key(agent_key).is_ok() {
        Some(agent_key)
    } else {
        None
    }
}

fn prompt_agent_keys() -> Vec<String> {
    PROMPT_SKILL_AGENT_KEYS
        .iter()
        .map(|item| (*item).to_string())
        .collect()
}

fn builtin_prompt_templates() -> BTreeMap<String, String> {
    BTreeMap::from([
        (
            "recon".to_string(),
            "优先快速建立项目画像：先识别入口、认证边界、外部输入面，再按风险优先级推进目录扫描。所有风险点必须基于真实代码证据，并尽量附带触发条件。".to_string(),
        ),
        (
            "business_logic_recon".to_string(),
            "优先枚举业务对象与敏感动作，重点关注对象所有权、状态跃迁、金额计算、权限边界。若项目缺少业务入口，应尽早给出终止依据。".to_string(),
        ),
        (
            "analysis".to_string(),
            "围绕单风险点做证据闭环：先定位代码，再追踪输入到敏感操作的数据流与控制流，结论必须可复核并明确漏洞成立条件。".to_string(),
        ),
        (
            "business_logic_analysis".to_string(),
            "优先验证授权与状态机约束，必须检查全局补偿逻辑，避免将已补偿场景误报为漏洞。".to_string(),
        ),
        (
            "verification".to_string(),
            "验证阶段必须坚持可复现证据优先：先读取上下文，再最小化构造触发路径。".to_string(),
        ),
    ])
}

fn default_builtin_prompt_state() -> BTreeMap<String, bool> {
    BTreeMap::from_iter(
        PROMPT_SKILL_AGENT_KEYS
            .iter()
            .map(|item| ((*item).to_string(), true)),
    )
}

fn normalize_scope(
    scope: &str,
    agent_key: Option<&str>,
) -> Result<(String, Option<String>), ApiError> {
    let normalized = scope.trim().to_lowercase();
    match normalized.as_str() {
        PROMPT_SKILL_SCOPE_GLOBAL => Ok((normalized, None)),
        PROMPT_SKILL_SCOPE_AGENT_SPECIFIC => {
            let Some(agent_key) = agent_key.map(str::trim).filter(|value| !value.is_empty()) else {
                return Err(ApiError::BadRequest("agent_key is required".to_string()));
            };
            ensure_valid_agent_key(agent_key)?;
            Ok((normalized, Some(agent_key.to_string())))
        }
        _ => Err(ApiError::BadRequest(
            "invalid prompt skill scope".to_string(),
        )),
    }
}

fn ensure_valid_agent_key(agent_key: &str) -> Result<(), ApiError> {
    if PROMPT_SKILL_AGENT_KEYS
        .iter()
        .any(|value| *value == agent_key)
    {
        return Ok(());
    }
    Err(ApiError::BadRequest("invalid agent key".to_string()))
}

fn agent_label(agent_key: &str) -> &'static str {
    match agent_key {
        "recon" => "Recon Agent",
        "business_logic_recon" => "Business Logic Recon Agent",
        "analysis" => "Analysis Agent",
        "business_logic_analysis" => "Business Logic Analysis Agent",
        "verification" => "Verification Agent",
        _ => "Agent",
    }
}

fn prompt_skills_file_path(state: &AppState) -> PathBuf {
    state.config.zip_storage_path.join(PROMPT_SKILLS_FILE_NAME)
}

fn builtin_prompt_state_file_path(state: &AppState) -> PathBuf {
    state
        .config
        .zip_storage_path
        .join(BUILTIN_PROMPT_STATE_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<(), std::io::Error> {
    fs::create_dir_all(&state.config.zip_storage_path).await
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| OffsetDateTime::now_utc().unix_timestamp().to_string())
}

fn now_ts() -> i64 {
    OffsetDateTime::now_utc().unix_timestamp()
}

impl From<prompt_skills_db::StoredPromptSkillRecord> for PromptSkillRecord {
    fn from(value: prompt_skills_db::StoredPromptSkillRecord) -> Self {
        Self {
            id: value.id,
            name: value.name,
            content: value.content,
            scope: value.scope,
            agent_key: value.agent_key,
            is_active: value.is_active,
            created_at: value.created_at,
            updated_at: value.updated_at,
        }
    }
}

impl From<PromptSkillRecord> for prompt_skills_db::StoredPromptSkillRecord {
    fn from(value: PromptSkillRecord) -> Self {
        Self {
            id: value.id,
            name: value.name,
            content: value.content,
            scope: value.scope,
            agent_key: value.agent_key,
            is_active: value.is_active,
            created_at: value.created_at,
            updated_at: value.updated_at,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_prompt_effective_skill_sorts_custom_prompts_deterministically() {
        let custom_prompt_skills = vec![
            PromptSkillRecord {
                id: "agent-z".to_string(),
                name: "Agent Z".to_string(),
                content: "Agent-specific block.".to_string(),
                scope: PROMPT_SKILL_SCOPE_AGENT_SPECIFIC.to_string(),
                agent_key: Some("analysis".to_string()),
                is_active: true,
                created_at: "2026-04-15T00:00:03Z".to_string(),
                updated_at: None,
            },
            PromptSkillRecord {
                id: "global-b".to_string(),
                name: "Global B".to_string(),
                content: "Second global block.".to_string(),
                scope: PROMPT_SKILL_SCOPE_GLOBAL.to_string(),
                agent_key: None,
                is_active: true,
                created_at: "2026-04-15T00:00:02Z".to_string(),
                updated_at: None,
            },
            PromptSkillRecord {
                id: "global-earliest".to_string(),
                name: "Global Earliest".to_string(),
                content: "First global block.".to_string(),
                scope: PROMPT_SKILL_SCOPE_GLOBAL.to_string(),
                agent_key: None,
                is_active: true,
                created_at: "2026-04-15T00:00:01Z".to_string(),
                updated_at: None,
            },
            PromptSkillRecord {
                id: "global-a".to_string(),
                name: "Global A".to_string(),
                content: "Tie-break global block.".to_string(),
                scope: PROMPT_SKILL_SCOPE_GLOBAL.to_string(),
                agent_key: None,
                is_active: true,
                created_at: "2026-04-15T00:00:02Z".to_string(),
                updated_at: None,
            },
        ];

        let effective = build_prompt_effective_skill(
            "analysis",
            &custom_prompt_skills,
            &default_builtin_prompt_state(),
        )
        .expect("effective prompt should build");

        let effective_content = effective.effective_content;
        let builtin_index = effective_content
            .find("围绕单风险点做证据闭环")
            .expect("builtin prompt should be first");
        let global_earliest_index = effective_content
            .find("[Global Earliest] First global block.")
            .expect("earliest global prompt should be included");
        let global_a_index = effective_content
            .find("[Global A] Tie-break global block.")
            .expect("tied global prompt should use id tie-break");
        let global_b_index = effective_content
            .find("[Global B] Second global block.")
            .expect("later tied global prompt should follow id tie-break");
        let agent_index = effective_content
            .find("[Agent Z] Agent-specific block.")
            .expect("agent-specific prompt should be included");

        assert!(builtin_index < global_earliest_index);
        assert!(global_earliest_index < global_a_index);
        assert!(global_a_index < global_b_index);
        assert!(global_b_index < agent_index);

        let prompt_sources = effective.prompt_sources;
        assert_eq!(prompt_sources[1].name.as_deref(), Some("Global Earliest"));
        assert_eq!(prompt_sources[2].name.as_deref(), Some("Global A"));
        assert_eq!(prompt_sources[3].name.as_deref(), Some("Global B"));
        assert_eq!(prompt_sources[4].name.as_deref(), Some("Agent Z"));
    }
}
