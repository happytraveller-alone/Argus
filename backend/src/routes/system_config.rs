use std::{collections::BTreeMap, env, time::Duration};

use axum::{
    body::Bytes,
    extract::State,
    http::HeaderMap,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::{
    config::AppConfig,
    core::encryption::encrypt_sensitive_fields,
    db::system_config,
    error::ApiError,
    llm::{
        build_runtime_config, compute_llm_fingerprint, is_supported_protocol_provider,
        normalize_base_url, normalize_provider_id, parse_custom_headers, provider_api_key_field,
        provider_catalog, provider_catalog_entry_or_fallback, recommend_tokens,
        sanitize_llm_config_for_save, test_llm_generation, LlmGateError,
        ProviderCatalogItem as LlmProviderItem,
    },
    routes::llm_config_set,
    runtime::cubesandbox::config::CubeSandboxConfig,
    state::{AppState, StoredSystemConfig},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemConfigPayload {
    pub llm_config: Value,
    pub other_config: Value,
    #[serde(default)]
    pub llm_test_metadata: Value,
}

const IMPORT_TOKEN_ENV: &str = "ARGUS_RESET_IMPORT_TOKEN";
const IMPORT_TOKEN_HEADER: &str = "x-argus-reset-import-token";
const REDACTED_SECRET_PLACEHOLDER: &str = llm_config_set::REDACTED_SECRET_PLACEHOLDER;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportEnvResponse {
    pub success: bool,
    pub message: String,
    pub provider: Option<String>,
    pub model: Option<String>,
    pub base_url: Option<String>,
    pub has_saved_api_key: bool,
    pub secret_source: String,
    pub reason_code: Option<String>,
    pub stage: Option<String>,
    pub metadata: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmQuickConfigSnapshot {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub api_key: String,
    pub has_saved_api_key: bool,
    pub secret_source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentPreflightPayload {
    pub ok: bool,
    pub stage: Option<String>,
    pub message: String,
    pub reason_code: Option<String>,
    pub missing_fields: Option<Vec<String>>,
    pub effective_config: LlmQuickConfigSnapshot,
    pub saved_config: Option<LlmQuickConfigSnapshot>,
    pub metadata: Option<Value>,
    pub llm_test_metadata: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmTestRequest {
    pub row_id: Option<String>,
    pub provider: String,
    pub api_key: Option<String>,
    pub model: Option<String>,
    pub base_url: Option<String>,
    pub custom_headers: Option<String>,
    pub secret_source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmTestResponse {
    pub success: bool,
    pub message: String,
    pub model: Option<String>,
    pub response: Option<String>,
    pub metadata: Option<Value>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmBatchTestRowOutcome {
    pub row_id: String,
    pub priority: i64,
    pub status: String,
    pub reason_code: Option<String>,
    pub message: String,
    pub checked_at: Option<String>,
    pub model: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmBatchTestResponse {
    pub success: bool,
    pub message: String,
    pub reason_code: String,
    pub rows: Vec<LlmBatchTestRowOutcome>,
    pub attempted_row_ids: Vec<String>,
    pub skipped_row_ids: Vec<String>,
    pub missing_field_row_ids: Vec<String>,
    pub failed_row_ids: Vec<String>,
    pub passed_row_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FetchModelsRequest {
    pub row_id: Option<String>,
    #[serde(default)]
    pub provider: String,
    #[serde(default)]
    pub api_key: String,
    pub base_url: Option<String>,
    pub custom_headers: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FetchModelsResponse {
    pub success: bool,
    pub message: String,
    pub provider: String,
    pub resolved_provider: String,
    pub models: Vec<String>,
    pub default_model: String,
    pub source: String,
    pub base_url_used: Option<String>,
    pub model_metadata: BTreeMap<String, Value>,
    pub token_recommendation_source: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmProviderCatalogResponse {
    providers: Vec<LlmProviderItem>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/defaults", get(get_defaults))
        .route(
            "/",
            get(get_current).put(put_current).delete(delete_current),
        )
        .route("/llm-providers", get(get_llm_providers))
        .route("/test-llm", post(test_llm))
        .route("/test-llm/batch", post(test_llm_batch))
        .route("/import-env", post(import_env))
        .route("/fetch-llm-models", post(fetch_llm_models))
        .route("/agent-preflight", post(agent_preflight))
}

pub async fn get_defaults(State(state): State<AppState>) -> Json<SystemConfigPayload> {
    Json(public_payload(
        default_config(state.config.as_ref()),
        state.config.as_ref(),
    ))
}

pub async fn get_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    Ok(Json(public_payload(
        merge_with_defaults(state.config.as_ref(), stored),
        state.config.as_ref(),
    )))
}

pub async fn put_current(
    State(state): State<AppState>,
    Json(payload): Json<SystemConfigPayload>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let defaults = default_config(state.config.as_ref());
    let existing = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let next_llm = llm_config_set::normalize_for_save(
        &payload.llm_config,
        existing.as_ref().map(|stored| &stored.llm_config_json),
        state.config.as_ref(),
    )
    .map_err(llm_gate_bad_request)?;
    let next_other = merge_json(&defaults.other_config, &payload.other_config);
    let stored = system_config::save_current(&state, next_llm, next_other, json!({}))
        .await
        .map_err(internal_error)?;

    let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
    sync_python_user_config_mirror(&state, Some(&merged)).await?;
    Ok(Json(public_payload(merged, state.config.as_ref())))
}

pub async fn delete_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    system_config::clear_current(&state)
        .await
        .map_err(internal_error)?;
    sync_python_user_config_mirror(&state, None).await?;
    Ok(Json(public_payload(
        default_config(state.config.as_ref()),
        state.config.as_ref(),
    )))
}

async fn get_llm_providers() -> Json<LlmProviderCatalogResponse> {
    Json(LlmProviderCatalogResponse {
        providers: provider_catalog(),
    })
}

pub async fn test_llm(
    State(state): State<AppState>,
    Json(request): Json<LlmTestRequest>,
) -> Result<Json<LlmTestResponse>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::BadRequest("请先保存 LLM 配置，再执行连接测试。".to_string()))?;
    let (envelope, _) =
        llm_config_set::normalize_envelope(&stored.llm_config_json, state.config.as_ref());
    let rows = envelope
        .get("rows")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let provider = normalize_provider_for_route(&request.provider);
    let model = request.model.clone().unwrap_or_default().trim().to_string();
    let base_url = normalize_base_url(&request.base_url.clone().unwrap_or_default());
    let request_custom_headers_value = request
        .custom_headers
        .as_ref()
        .map(|headers| Value::String(headers.clone()));
    let request_custom_headers = parse_custom_headers(request_custom_headers_value.as_ref())
        .map_err(ApiError::BadRequest)?;

    let selected_row = rows.into_iter().find(|row| {
        if let Some(row_id) = request.row_id.as_deref() {
            if read_string(row, "id").as_deref() != Some(row_id) {
                return false;
            }
        }
        let row_config = llm_config_set::row_to_legacy_config(row);
        let row_headers =
            parse_custom_headers(row_config.get("llmCustomHeaders")).unwrap_or_default();
        read_string(&row_config, "llmProvider").unwrap_or_default() == provider
            && read_string(&row_config, "llmModel").unwrap_or_default() == model
            && normalize_base_url(&read_string(&row_config, "llmBaseUrl").unwrap_or_default())
                == base_url
            && row_headers == request_custom_headers
    });
    let Some(row) = selected_row else {
        return Ok(Json(LlmTestResponse {
            success: false,
            message: "当前测试请求与已保存 LLM 配置行不一致，请先保存后再测试。".to_string(),
            model: None,
            response: None,
            metadata: None,
        }));
    };
    let mut row_config = llm_config_set::row_to_legacy_config(&row);
    let api_key = resolve_test_api_key(&request, &row_config)?;
    if api_key != read_string(&row_config, "llmApiKey").unwrap_or_default() {
        if let Some(map) = row_config.as_object_mut() {
            map.insert("llmApiKey".to_string(), Value::String(api_key));
        }
    }
    let runtime = match build_runtime_config(&row_config, &stored.other_config_json) {
        Ok(runtime) => runtime,
        Err(error) => {
            return Ok(Json(LlmTestResponse {
                success: false,
                message: error.message,
                model: None,
                response: None,
                metadata: None,
            }))
        }
    };
    let row_id = read_string(&row, "id").unwrap_or_default();
    match test_llm_generation(&state.http_client, &runtime).await {
        Ok(outcome) => {
            let metadata = outcome.metadata();
            let mut next_envelope = llm_config_set::mark_row_preflight(
                &envelope,
                &row_id,
                "passed",
                None,
                Some("连接校验通过"),
                Some(&outcome.fingerprint),
            );
            next_envelope = llm_config_set::set_latest_preflight_run(
                &next_envelope,
                vec![row_id.clone()],
                Some(row_id),
                Some(outcome.fingerprint.clone()),
            );
            let stored = system_config::save_current(
                &state,
                next_envelope,
                stored.other_config_json,
                metadata.clone(),
            )
            .await
            .map_err(internal_error)?;
            let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
            sync_python_user_config_mirror(&state, Some(&merged)).await?;
            Ok(Json(LlmTestResponse {
                success: true,
                message: "连接校验通过".to_string(),
                model: Some(outcome.model),
                response: None,
                metadata: Some(metadata),
            }))
        }
        Err(error) => {
            let category = llm_config_set::classify_fallback(&error);
            let next_envelope = llm_config_set::mark_row_preflight(
                &envelope,
                &row_id,
                "failed",
                Some(category.reason_code()),
                Some(&error.message),
                Some(&compute_llm_fingerprint(&runtime)),
            );
            let _ = system_config::save_current(
                &state,
                next_envelope,
                stored.other_config_json,
                json!({}),
            )
            .await;
            Ok(Json(LlmTestResponse {
                success: false,
                message: error.message,
                model: None,
                response: None,
                metadata: Some(json!({"reasonCode": category.reason_code()})),
            }))
        }
    }
}

pub async fn test_llm_batch(
    State(state): State<AppState>,
    body: Bytes,
) -> Result<Json<LlmBatchTestResponse>, ApiError> {
    reject_batch_config_payload(&body)?;
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| {
            ApiError::BadRequest("请先保存 LLM 配置，再执行批量连接测试。".to_string())
        })?;
    let (mut envelope, _) =
        llm_config_set::normalize_envelope(&stored.llm_config_json, state.config.as_ref());
    let rows = envelope
        .get("rows")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let mut outcomes = Vec::new();
    let mut attempted_row_ids = Vec::new();
    let mut skipped_row_ids = Vec::new();
    let mut missing_field_row_ids = Vec::new();
    let mut failed_row_ids = Vec::new();
    let mut passed_row_ids = Vec::new();
    let mut last_success_metadata = json!({});

    for row in rows.iter() {
        let row_id = read_string(row, "id").unwrap_or_default();
        let priority = row.get("priority").and_then(Value::as_i64).unwrap_or(0);
        let model = read_string(row, "model").filter(|value| !value.trim().is_empty());
        if !row.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
            skipped_row_ids.push(row_id.clone());
            outcomes.push(LlmBatchTestRowOutcome {
                row_id,
                priority,
                status: "skipped_disabled".to_string(),
                reason_code: Some("skipped_disabled".to_string()),
                message: "配置行已禁用，本次批量验证跳过。".to_string(),
                checked_at: None,
                model,
            });
            continue;
        }

        let missing_fields = llm_config_set::missing_fields_for_row(row);
        if !missing_fields.is_empty() {
            envelope = llm_config_set::mark_row_preflight(
                &envelope,
                &row_id,
                "missing_fields",
                Some("missing_fields"),
                Some(&format!(
                    "配置行缺少必填字段：{}",
                    missing_fields.join("、")
                )),
                None,
            );
            missing_field_row_ids.push(row_id.clone());
            outcomes.push(LlmBatchTestRowOutcome {
                checked_at: read_row_preflight_checked_at(&envelope, &row_id),
                row_id,
                priority,
                status: "missing_fields".to_string(),
                reason_code: Some("missing_fields".to_string()),
                message: format!("配置行缺少必填字段：{}", missing_fields.join("、")),
                model,
            });
            continue;
        }

        attempted_row_ids.push(row_id.clone());
        let runtime_config = llm_config_set::row_to_legacy_config(row);
        let runtime = match build_runtime_config(&runtime_config, &stored.other_config_json) {
            Ok(runtime) => runtime,
            Err(error) => {
                let category = llm_config_set::classify_fallback(&error);
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "failed",
                    Some(category.reason_code()),
                    Some(&error.message),
                    None,
                );
                failed_row_ids.push(row_id.clone());
                outcomes.push(LlmBatchTestRowOutcome {
                    row_id,
                    priority,
                    status: "failed".to_string(),
                    reason_code: Some(category.reason_code().to_string()),
                    message: error.message,
                    checked_at: None,
                    model,
                });
                if let Some(last) = outcomes.last_mut() {
                    last.checked_at = read_row_preflight_checked_at(&envelope, &last.row_id);
                }
                continue;
            }
        };

        match test_llm_generation(&state.http_client, &runtime).await {
            Ok(outcome) => {
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "passed",
                    None,
                    Some("连接校验通过"),
                    Some(&outcome.fingerprint),
                );
                last_success_metadata = outcome.metadata();
                passed_row_ids.push(row_id.clone());
                outcomes.push(LlmBatchTestRowOutcome {
                    row_id,
                    priority,
                    status: "passed".to_string(),
                    reason_code: None,
                    message: "连接校验通过".to_string(),
                    checked_at: None,
                    model: Some(outcome.model),
                });
                if let Some(last) = outcomes.last_mut() {
                    last.checked_at = read_row_preflight_checked_at(&envelope, &last.row_id);
                }
            }
            Err(error) => {
                let category = llm_config_set::classify_fallback(&error);
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "failed",
                    Some(category.reason_code()),
                    Some(&error.message),
                    Some(&compute_llm_fingerprint(&runtime)),
                );
                failed_row_ids.push(row_id.clone());
                outcomes.push(LlmBatchTestRowOutcome {
                    row_id,
                    priority,
                    status: "failed".to_string(),
                    reason_code: Some(category.reason_code().to_string()),
                    message: error.message,
                    checked_at: None,
                    model,
                });
                if let Some(last) = outcomes.last_mut() {
                    last.checked_at = read_row_preflight_checked_at(&envelope, &last.row_id);
                }
            }
        }
    }

    envelope =
        llm_config_set::set_latest_preflight_run(&envelope, attempted_row_ids.clone(), None, None);
    let stored = system_config::save_current(
        &state,
        envelope,
        stored.other_config_json,
        last_success_metadata,
    )
    .await
    .map_err(internal_error)?;
    let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
    sync_python_user_config_mirror(&state, Some(&merged)).await?;

    let enabled_problem_count = missing_field_row_ids.len() + failed_row_ids.len();
    let reason_code = if attempted_row_ids.is_empty() {
        "no_eligible_rows"
    } else if enabled_problem_count > 0 {
        "row_validation_failed"
    } else {
        "all_rows_passed"
    };
    let success = reason_code == "all_rows_passed";
    let message = match reason_code {
        "all_rows_passed" => format!("批量验证通过：{} 行可用。", passed_row_ids.len()),
        "no_eligible_rows" => "没有可执行实时验证的已启用完整配置行。".to_string(),
        _ => format!(
            "批量验证完成：{} 行通过，{} 行失败，{} 行字段不完整，{} 行跳过。",
            passed_row_ids.len(),
            failed_row_ids.len(),
            missing_field_row_ids.len(),
            skipped_row_ids.len()
        ),
    };

    Ok(Json(LlmBatchTestResponse {
        success,
        message,
        reason_code: reason_code.to_string(),
        rows: outcomes,
        attempted_row_ids,
        skipped_row_ids,
        missing_field_row_ids,
        failed_row_ids,
        passed_row_ids,
    }))
}

pub async fn import_env(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ImportEnvResponse>, ApiError> {
    verify_import_token(&headers)?;
    let defaults = default_config(state.config.as_ref());
    let imported_llm =
        import_llm_config_from_env(&llm_config_set::legacy_defaults(state.config.as_ref()))?;
    let imported_other = merge_json(&defaults.other_config, &json!({}));
    let runtime =
        build_runtime_config(&imported_llm, &imported_other).map_err(llm_gate_bad_request)?;

    match test_llm_generation(&state.http_client, &runtime).await {
        Ok(outcome) => {
            let metadata = outcome.metadata();
            let mut imported_envelope = llm_config_set::normalize_for_save(
                &mark_imported_system_config(&imported_llm),
                None,
                state.config.as_ref(),
            )
            .map_err(llm_gate_bad_request)?;
            let imported_row_id = imported_envelope["rows"][0]["id"]
                .as_str()
                .unwrap_or_default()
                .to_string();
            imported_envelope = llm_config_set::mark_row_preflight(
                &imported_envelope,
                &imported_row_id,
                "passed",
                None,
                Some("导入后连接校验通过"),
                Some(&outcome.fingerprint),
            );
            imported_envelope = llm_config_set::set_latest_preflight_run(
                &imported_envelope,
                vec![imported_row_id.clone()],
                Some(imported_row_id),
                Some(outcome.fingerprint.clone()),
            );
            let stored = system_config::save_current(
                &state,
                imported_envelope,
                imported_other,
                metadata.clone(),
            )
            .await
            .map_err(internal_error)?;
            let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
            sync_python_user_config_mirror(&state, Some(&merged)).await?;
            Ok(Json(import_response(
                true,
                "已从 .argus-intelligent-audit.env 导入并完成 LLM 测试。",
                &imported_llm,
                Some(metadata),
                None,
                None,
            )))
        }
        Err(error) => {
            let imported_envelope = llm_config_set::normalize_for_save(
                &mark_imported_system_config(&imported_llm),
                None,
                state.config.as_ref(),
            )
            .map_err(llm_gate_bad_request)?;
            let stored =
                system_config::save_current(&state, imported_envelope, imported_other, json!({}))
                    .await
                    .map_err(internal_error)?;
            let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
            sync_python_user_config_mirror(&state, Some(&merged)).await?;
            Ok(Json(import_response(
                false,
                &error.message,
                &imported_llm,
                None,
                Some(error.reason_code.to_string()),
                Some("llm_test".to_string()),
            )))
        }
    }
}

pub async fn fetch_llm_models(
    State(state): State<AppState>,
    Json(request): Json<FetchModelsRequest>,
) -> Result<Json<FetchModelsResponse>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let effective_llm_config = stored
        .as_ref()
        .and_then(|saved| {
            saved_fetch_models_config(&saved.llm_config_json, &request, &state.config)
        })
        .unwrap_or_else(|| json!({}));
    let saved_provider = read_string(&effective_llm_config, "llmProvider").unwrap_or_default();
    let requested_provider = request.provider.trim();
    let provider = normalize_provider_for_route(if requested_provider.is_empty() {
        &saved_provider
    } else {
        requested_provider
    });
    let provider_item = provider_catalog_entry_or_fallback(&provider);
    let custom_headers = if request.custom_headers.is_some() {
        parse_custom_headers(request.custom_headers.as_ref()).map_err(ApiError::BadRequest)?
    } else {
        parse_custom_headers(effective_llm_config.get("llmCustomHeaders"))
            .map_err(ApiError::BadRequest)?
    };
    let requested_base_url = request.base_url.as_deref().unwrap_or_default().trim();
    let saved_base_url = read_string(&effective_llm_config, "llmBaseUrl").unwrap_or_default();
    let base_url_used = Some(normalize_base_url(if requested_base_url.is_empty() {
        &saved_base_url
    } else {
        requested_base_url
    }))
    .filter(|value| !value.is_empty())
    .or_else(|| {
        if provider_item.default_base_url.is_empty() {
            None
        } else {
            Some(provider_item.default_base_url.clone())
        }
    });
    let request_api_key = request.api_key.trim().to_string();
    let saved_api_key = read_string(&effective_llm_config, "llmApiKey").unwrap_or_default();
    let api_key = if request_api_key.is_empty() {
        saved_api_key.trim().to_string()
    } else {
        request_api_key
    };

    if provider_item.supports_model_fetch && provider_item.fetch_style == "openai_compatible" {
        if let Some(base_url) = base_url_used.as_deref() {
            if !provider_item.requires_api_key || !api_key.trim().is_empty() {
                if let Ok(online) = fetch_openai_compatible_models(
                    &state,
                    base_url,
                    &api_key,
                    &custom_headers,
                    &provider_item,
                )
                .await
                {
                    return Ok(Json(online));
                }
            }
        }
    }

    let model_metadata = static_model_metadata(&provider_item);
    Ok(Json(FetchModelsResponse {
        success: true,
        message: format!("已返回 {} 个静态模型目录", provider_item.models.len()),
        provider: provider.clone(),
        resolved_provider: provider.clone(),
        models: provider_item.models,
        default_model: provider_item.default_model,
        source: "fallback_static".to_string(),
        base_url_used,
        model_metadata,
        token_recommendation_source: "static_mapping".to_string(),
    }))
}

fn saved_fetch_models_config(
    saved_llm_config: &Value,
    request: &FetchModelsRequest,
    config: &AppConfig,
) -> Option<Value> {
    let (envelope, _) = llm_config_set::normalize_envelope(saved_llm_config, config);
    let rows = envelope.get("rows").and_then(Value::as_array)?;
    let requested_row_id = request.row_id.as_deref().unwrap_or_default().trim();
    let row = rows
        .iter()
        .find(|row| {
            !requested_row_id.is_empty()
                && read_string(row, "id").as_deref() == Some(requested_row_id)
        })
        .or_else(|| {
            rows.iter()
                .find(|row| row.get("enabled").and_then(Value::as_bool).unwrap_or(true))
        })?;
    Some(llm_config_set::row_to_legacy_config(row))
}

async fn fetch_openai_compatible_models(
    state: &AppState,
    base_url: &str,
    api_key: &str,
    custom_headers: &BTreeMap<String, String>,
    provider_item: &LlmProviderItem,
) -> Result<FetchModelsResponse, String> {
    let url = format!("{}/models", base_url.trim_end_matches('/'));
    let mut headers = reqwest::header::HeaderMap::new();
    for (name, value) in custom_headers {
        let header_name = reqwest::header::HeaderName::from_bytes(name.as_bytes())
            .map_err(|_| "invalid header name".to_string())?;
        let header_value = reqwest::header::HeaderValue::from_str(value)
            .map_err(|_| "invalid header value".to_string())?;
        headers.insert(header_name, header_value);
    }
    if provider_item.requires_api_key {
        let header_value = reqwest::header::HeaderValue::from_str(&format!("Bearer {api_key}"))
            .map_err(|_| "invalid api key".to_string())?;
        headers.insert(reqwest::header::AUTHORIZATION, header_value);
    }

    let response = state
        .http_client
        .get(url)
        .headers(headers)
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("upstream status {}", response.status()));
    }
    let payload: Value = response.json().await.map_err(|error| error.to_string())?;
    let mut models = normalize_models_response(&payload);
    if models.is_empty() {
        return Err("empty model list".to_string());
    }
    models.sort();
    models.dedup();
    let default_model = models
        .first()
        .cloned()
        .unwrap_or_else(|| provider_item.default_model.clone());
    let model_metadata = models
        .iter()
        .map(|model| {
            (
                model.clone(),
                json!({
                    "contextWindow": Value::Null,
                    "maxOutputTokens": Value::Null,
                    "recommendedMaxTokens": recommend_tokens(model),
                    "source": "online",
                }),
            )
        })
        .collect();
    Ok(FetchModelsResponse {
        success: true,
        message: format!("已在线获取 {} 个可用模型", models.len()),
        provider: provider_item.id.clone(),
        resolved_provider: provider_item.id.clone(),
        models,
        default_model,
        source: "online".to_string(),
        base_url_used: Some(base_url.to_string()),
        model_metadata,
        token_recommendation_source: "online_mapping".to_string(),
    })
}

fn normalize_models_response(payload: &Value) -> Vec<String> {
    if let Some(items) = payload.get("data").and_then(Value::as_array) {
        return items
            .iter()
            .filter_map(|item| {
                item.get("id")
                    .and_then(Value::as_str)
                    .or_else(|| item.as_str())
                    .map(str::trim)
                    .filter(|model| !model.is_empty())
                    .map(ToString::to_string)
            })
            .collect();
    }
    if let Some(items) = payload.get("models").and_then(Value::as_array) {
        return items
            .iter()
            .filter_map(|item| item.as_str().map(str::trim))
            .filter(|model| !model.is_empty())
            .map(ToString::to_string)
            .collect();
    }
    if let Some(items) = payload.as_array() {
        return items
            .iter()
            .filter_map(|item| item.as_str().map(str::trim))
            .filter(|model| !model.is_empty())
            .map(ToString::to_string)
            .collect();
    }
    Vec::new()
}

fn static_model_metadata(provider_item: &LlmProviderItem) -> BTreeMap<String, Value> {
    provider_item
        .models
        .iter()
        .map(|model| {
            (
                model.clone(),
                json!({
                    "contextWindow": Value::Null,
                    "maxOutputTokens": Value::Null,
                    "recommendedMaxTokens": recommend_tokens(model),
                    "source": "static_mapping",
                }),
            )
        })
        .collect()
}

pub async fn agent_preflight(
    State(state): State<AppState>,
) -> Result<Json<AgentPreflightPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let Some(stored_config) = stored.as_ref() else {
        let defaults = llm_config_set::default_envelope(state.config.as_ref());
        let row = defaults
            .get("rows")
            .and_then(Value::as_array)
            .and_then(|rows| rows.first())
            .cloned()
            .unwrap_or_else(|| json!({}));
        let snapshot: LlmQuickConfigSnapshot =
            serde_json::from_value(llm_config_set::quick_snapshot(&row)).unwrap_or_else(|_| {
                build_quick_snapshot(&llm_config_set::row_to_legacy_config(&row))
            });
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_config".to_string()),
            message: "检测到当前仍在使用默认 LLM 配置，请先保存并测试专属 LLM 配置。".to_string(),
            reason_code: Some("default_config".to_string()),
            missing_fields: None,
            effective_config: snapshot,
            saved_config: None,
            metadata: Some(agent_preflight_metadata(
                "llm_config",
                "default_config",
                None,
            )),
            llm_test_metadata: None,
        }));
    };

    let (mut envelope, _) =
        llm_config_set::normalize_envelope(&stored_config.llm_config_json, state.config.as_ref());
    let rows = envelope
        .get("rows")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut attempted_row_ids = Vec::new();
    let mut first_snapshot: Option<LlmQuickConfigSnapshot> = None;
    let mut first_saved_snapshot: Option<LlmQuickConfigSnapshot> = None;
    let mut last_failure: Option<(String, String, String, Option<Vec<String>>)> = None;

    for row in rows
        .iter()
        .filter(|row| row.get("enabled").and_then(Value::as_bool).unwrap_or(true))
    {
        let row_id = read_string(row, "id").unwrap_or_default();
        let snapshot: LlmQuickConfigSnapshot =
            serde_json::from_value(llm_config_set::quick_snapshot(row)).unwrap_or_else(|_| {
                build_quick_snapshot(&llm_config_set::row_to_legacy_config(row))
            });
        if first_snapshot.is_none() {
            first_snapshot = Some(snapshot.clone());
            first_saved_snapshot = Some(snapshot.clone());
        }
        attempted_row_ids.push(row_id.clone());
        let missing_fields = llm_config_set::missing_fields_for_row(row);
        if !missing_fields.is_empty() {
            envelope = llm_config_set::mark_row_preflight(
                &envelope,
                &row_id,
                "failed",
                Some("missing_fields"),
                Some("配置行缺少必填字段"),
                None,
            );
            last_failure = Some((
                "llm_config".to_string(),
                "missing_fields".to_string(),
                format!(
                    "智能审计初始化失败：LLM 缺少必填配置 {}，请先补全并保存。",
                    missing_fields.join("、")
                ),
                Some(missing_fields),
            ));
            continue;
        }
        let runtime_config = llm_config_set::row_to_legacy_config(row);
        let runtime = match build_runtime_config(&runtime_config, &stored_config.other_config_json)
        {
            Ok(runtime) => runtime,
            Err(error) => {
                let category = llm_config_set::classify_fallback(&error);
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "failed",
                    Some(category.reason_code()),
                    Some(&error.message),
                    None,
                );
                last_failure = Some((
                    "llm_config".to_string(),
                    category.reason_code().to_string(),
                    error.message,
                    None,
                ));
                if category.is_fallback_eligible() {
                    continue;
                }
                break;
            }
        };
        let fingerprint = compute_llm_fingerprint(&runtime);
        match test_llm_generation(&state.http_client, &runtime).await {
            Ok(outcome) => {
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "passed",
                    None,
                    Some("预检通过"),
                    Some(&outcome.fingerprint),
                );
                envelope = llm_config_set::set_latest_preflight_run(
                    &envelope,
                    attempted_row_ids.clone(),
                    Some(row_id.clone()),
                    Some(outcome.fingerprint.clone()),
                );
                let stored = system_config::save_current(
                    &state,
                    envelope.clone(),
                    stored_config.other_config_json.clone(),
                    outcome.metadata(),
                )
                .await
                .map_err(internal_error)?;
                let selected_snapshot: LlmQuickConfigSnapshot =
                    serde_json::from_value(llm_config_set::quick_snapshot(row))
                        .unwrap_or_else(|_| build_quick_snapshot(&runtime_config));
                let runner_metadata = annotate_llm_preflight_metadata(
                    add_preflight_attempt_metadata(
                        agent_preflight_metadata("runner", "runner_missing", None),
                        &attempted_row_ids,
                        Some(&row_id),
                        Some(&outcome.fingerprint),
                    ),
                    &runtime_config,
                );
                if runner_metadata["runner"]["ok"] != true {
                    return Ok(Json(AgentPreflightPayload {
                        ok: false,
                        stage: Some("runner".to_string()),
                        message: "智能审计初始化失败：AgentFlow runner 尚未配置或不可用。"
                            .to_string(),
                        reason_code: Some("runner_missing".to_string()),
                        missing_fields: None,
                        effective_config: selected_snapshot.clone(),
                        saved_config: Some(selected_snapshot),
                        metadata: Some(runner_metadata),
                        llm_test_metadata: Some(stored.llm_test_metadata_json),
                    }));
                }
                return Ok(Json(AgentPreflightPayload {
                    ok: true,
                    stage: None,
                    message: "智能审计预检通过。".to_string(),
                    reason_code: None,
                    missing_fields: None,
                    effective_config: selected_snapshot.clone(),
                    saved_config: Some(selected_snapshot),
                    metadata: Some(runner_metadata),
                    llm_test_metadata: Some(stored.llm_test_metadata_json),
                }));
            }
            Err(error) => {
                let category = llm_config_set::classify_fallback(&error);
                envelope = llm_config_set::mark_row_preflight(
                    &envelope,
                    &row_id,
                    "failed",
                    Some(category.reason_code()),
                    Some(&error.message),
                    Some(&fingerprint),
                );
                last_failure = Some((
                    "llm_test".to_string(),
                    category.reason_code().to_string(),
                    error.message,
                    None,
                ));
                if category.is_fallback_eligible() {
                    continue;
                }
                break;
            }
        }
    }

    envelope =
        llm_config_set::set_latest_preflight_run(&envelope, attempted_row_ids.clone(), None, None);
    let _ = system_config::save_current(
        &state,
        envelope,
        stored_config.other_config_json.clone(),
        json!({}),
    )
    .await;
    let (stage, reason, message, missing_fields) = last_failure.unwrap_or_else(|| {
        (
            "llm_config".to_string(),
            "missing_fields".to_string(),
            "没有可用于预检的已启用 LLM 配置行。".to_string(),
            None,
        )
    });
    let effective = first_snapshot.unwrap_or_else(|| LlmQuickConfigSnapshot {
        provider: "openai_compatible".to_string(),
        model: String::new(),
        base_url: String::new(),
        api_key: String::new(),
        has_saved_api_key: false,
        secret_source: "none".to_string(),
    });
    Ok(Json(AgentPreflightPayload {
        ok: false,
        stage: Some(stage.clone()),
        message,
        reason_code: Some(reason.clone()),
        missing_fields,
        effective_config: effective,
        saved_config: first_saved_snapshot,
        metadata: Some(add_preflight_attempt_metadata(
            agent_preflight_metadata(&stage, &reason, None),
            &attempted_row_ids,
            None,
            None,
        )),
        llm_test_metadata: None,
    }))
}

pub fn default_config(config: &AppConfig) -> SystemConfigPayload {
    SystemConfigPayload {
        llm_config: llm_config_set::default_envelope(config),
        other_config: json!({
            "maxAnalyzeFiles": config.max_analyze_files,
            "llmConcurrency": config.llm_concurrency,
            "llmGapMs": config.llm_gap_ms,
            "cubeSandbox": CubeSandboxConfig::defaults(config).to_public_json()
        }),
        llm_test_metadata: json!({}),
    }
}

fn merge_with_defaults(
    config: &AppConfig,
    stored: Option<StoredSystemConfig>,
) -> SystemConfigPayload {
    let defaults = default_config(config);
    match stored {
        Some(stored) => {
            let (llm_config, _) =
                llm_config_set::normalize_envelope(&stored.llm_config_json, config);
            SystemConfigPayload {
                llm_config,
                other_config: merge_json(&defaults.other_config, &stored.other_config_json),
                llm_test_metadata: stored.llm_test_metadata_json,
            }
        }
        None => defaults,
    }
}

fn merge_json(defaults: &Value, overrides: &Value) -> Value {
    match (defaults, overrides) {
        (Value::Object(default_map), Value::Object(override_map)) => {
            let mut merged = default_map.clone();
            for (key, value) in override_map {
                merged.insert(key.clone(), value.clone());
            }
            Value::Object(merged)
        }
        (_, Value::Null) => defaults.clone(),
        (_, override_value) => override_value.clone(),
    }
}

fn public_payload(mut payload: SystemConfigPayload, config: &AppConfig) -> SystemConfigPayload {
    payload.llm_config = llm_config_set::public_envelope(&payload.llm_config, config);
    payload
}

fn reject_batch_config_payload(body: &Bytes) -> Result<(), ApiError> {
    if body.is_empty() {
        return Ok(());
    }
    let value: Value = serde_json::from_slice(body)
        .map_err(|_| ApiError::BadRequest("批量验证请求体必须为空或空 JSON 对象。".to_string()))?;
    match value {
        Value::Object(map) if map.is_empty() => Ok(()),
        _ => Err(ApiError::BadRequest(
            "批量验证只使用已保存配置，不接受请求体中的 LLM 配置。".to_string(),
        )),
    }
}

fn read_row_preflight_checked_at(envelope: &Value, row_id: &str) -> Option<String> {
    envelope
        .get("rows")
        .and_then(Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .find(|row| read_string(row, "id").as_deref() == Some(row_id))
        })
        .and_then(|row| row.get("preflight"))
        .and_then(|preflight| preflight.get("checkedAt"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn resolve_test_api_key(
    request: &LlmTestRequest,
    stored_llm_config: &Value,
) -> Result<String, ApiError> {
    let api_key = request
        .api_key
        .clone()
        .unwrap_or_default()
        .trim()
        .to_string();
    if api_key == REDACTED_SECRET_PLACEHOLDER {
        return Err(ApiError::BadRequest(
            "不能使用脱敏占位符测试 LLM，请选择使用已保存密钥或重新输入密钥。".to_string(),
        ));
    }
    let secret_source = request.secret_source.clone().unwrap_or_default();
    if api_key.is_empty()
        && matches!(
            secret_source.as_str(),
            "saved" | "imported" | "use_saved" | "use_imported"
        )
    {
        return read_string(stored_llm_config, "llmApiKey")
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| ApiError::BadRequest("当前没有可复用的已保存 LLM 密钥。".to_string()));
    }
    Ok(api_key)
}

fn verify_import_token(headers: &HeaderMap) -> Result<(), ApiError> {
    let expected = env::var(IMPORT_TOKEN_ENV).unwrap_or_default();
    if expected.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "重置导入令牌未配置，拒绝导入 LLM 环境配置。".to_string(),
        ));
    }
    let supplied = headers
        .get(IMPORT_TOKEN_HEADER)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if supplied.trim().is_empty() || supplied != expected {
        return Err(ApiError::BadRequest(
            "重置导入令牌无效，拒绝导入 LLM 环境配置。".to_string(),
        ));
    }
    Ok(())
}

fn import_llm_config_from_env(default_llm_config: &Value) -> Result<Value, ApiError> {
    let provider = env_required("LLM_PROVIDER")?;
    let provider = normalize_provider_id(&provider);
    if !is_supported_protocol_provider(&provider) {
        return Err(ApiError::BadRequest(
            "LLM_PROVIDER 必须是 openai_compatible 或 anthropic_compatible。".to_string(),
        ));
    }
    let api_key = env_required("LLM_API_KEY")?;
    if api_key == REDACTED_SECRET_PLACEHOLDER {
        return Err(ApiError::BadRequest(
            "LLM_API_KEY 不能是脱敏占位符。".to_string(),
        ));
    }
    let model = env_required("LLM_MODEL")?;
    let base_url = env_required("LLM_BASE_URL")?;
    let mut overrides = json!({
        "llmConfigVersion": crate::llm::LLM_CONFIG_VERSION,
        "llmProvider": provider,
        "llmApiKey": api_key,
        "llmModel": model,
        "llmBaseUrl": base_url,
        "secretSource": "imported",
        "credentialSource": "system_config",
        "llmApiKeyRef": "system_config:llmApiKey",
    });
    if let Some(map) = overrides.as_object_mut() {
        if let Some(value) = env_optional("LLM_TIMEOUT")
            .and_then(|value| parse_i64_env_value("LLM_TIMEOUT", &value).ok())
        {
            map.insert(
                "llmTimeout".to_string(),
                Value::Number((value * 1000).into()),
            );
        }
        if let Some(value) =
            env_optional("LLM_TEMPERATURE").and_then(|value| parse_f64_json_value(&value))
        {
            map.insert("llmTemperature".to_string(), value);
        }
        if let Some(value) = env_optional("LLM_MAX_TOKENS")
            .and_then(|value| parse_i64_env_value("LLM_MAX_TOKENS", &value).ok())
        {
            map.insert("llmMaxTokens".to_string(), Value::Number(value.into()));
        }
        if let Some(value) = env_optional("LLM_FIRST_TOKEN_TIMEOUT")
            .and_then(|value| parse_i64_env_value("LLM_FIRST_TOKEN_TIMEOUT", &value).ok())
        {
            map.insert(
                "llmFirstTokenTimeout".to_string(),
                Value::Number(value.into()),
            );
        }
        if let Some(value) = env_optional("LLM_STREAM_TIMEOUT")
            .and_then(|value| parse_i64_env_value("LLM_STREAM_TIMEOUT", &value).ok())
        {
            map.insert("llmStreamTimeout".to_string(), Value::Number(value.into()));
        }
        if let Some(value) = env_optional("AGENT_TIMEOUT")
            .or_else(|| env_optional("AGENT_TIMEOUT_SECONDS"))
            .and_then(|value| parse_i64_env_value("AGENT_TIMEOUT", &value).ok())
        {
            map.insert("agentTimeout".to_string(), Value::Number(value.into()));
        }
        if let Some(value) = env_optional("LLM_CUSTOM_HEADERS") {
            map.insert("llmCustomHeaders".to_string(), Value::String(value));
        }
    }
    let merged = merge_json(default_llm_config, &overrides);
    sanitize_llm_config_for_save(&merged).map_err(llm_gate_bad_request)
}

fn env_required(key: &str) -> Result<String, ApiError> {
    env_optional(key).ok_or_else(|| ApiError::BadRequest(format!("{key} 未配置。")))
}

fn env_optional(key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn parse_i64_env_value(key: &str, value: &str) -> Result<i64, ApiError> {
    value
        .parse::<i64>()
        .map_err(|_| ApiError::BadRequest(format!("{key} 必须是整数。")))
}

fn parse_f64_json_value(value: &str) -> Option<Value> {
    serde_json::Number::from_f64(value.parse::<f64>().ok()?).map(Value::Number)
}

fn mark_imported_system_config(llm_config: &Value) -> Value {
    let mut marked = llm_config.clone();
    if let Some(map) = marked.as_object_mut() {
        map.insert(
            "secretSource".to_string(),
            Value::String("imported".to_string()),
        );
        map.insert(
            "credentialSource".to_string(),
            Value::String("system_config".to_string()),
        );
        map.insert(
            "llmApiKeyRef".to_string(),
            Value::String("system_config:llmApiKey".to_string()),
        );
    }
    marked
}

fn import_response(
    success: bool,
    message: &str,
    llm_config: &Value,
    metadata: Option<Value>,
    reason_code: Option<String>,
    stage: Option<String>,
) -> ImportEnvResponse {
    ImportEnvResponse {
        success,
        message: message.to_string(),
        provider: read_string(llm_config, "llmProvider"),
        model: read_string(llm_config, "llmModel"),
        base_url: read_string(llm_config, "llmBaseUrl"),
        has_saved_api_key: read_string(llm_config, "llmApiKey")
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false),
        secret_source: "imported".to_string(),
        reason_code,
        stage,
        metadata,
    }
}

fn build_quick_snapshot(llm_config: &Value) -> LlmQuickConfigSnapshot {
    let provider = normalize_provider_for_route(
        read_string(llm_config, "llmProvider")
            .as_deref()
            .unwrap_or("openai_compatible"),
    );
    let base_url = read_string(llm_config, "llmBaseUrl")
        .or_else(|| read_string(llm_config, "ollamaBaseUrl"))
        .unwrap_or_default();
    let has_saved_api_key = read_string(llm_config, "llmApiKey")
        .or_else(|| {
            provider_api_key_field(&provider).and_then(|field| read_string(llm_config, field))
        })
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false);
    let secret_source = read_string(llm_config, "secretSource")
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| {
            if has_saved_api_key {
                "saved".to_string()
            } else {
                "none".to_string()
            }
        });

    LlmQuickConfigSnapshot {
        provider,
        model: read_string(llm_config, "llmModel").unwrap_or_default(),
        base_url,
        api_key: String::new(),
        has_saved_api_key,
        secret_source,
    }
}

fn agent_preflight_metadata(stage: &str, reason_code: &str, details: Option<Value>) -> Value {
    json!({
        "llm": {
            "ok": stage != "llm_config",
            "reason_code": reason_code,
        },
        "runner": {
            "ok": false,
            "reason_code": "not_checked",
        },
        "pipeline": {
            "ok": false,
            "reason_code": "not_checked",
        },
        "output_dir": {
            "ok": false,
            "reason_code": "not_checked",
        },
        "resource": {
            "ok": false,
            "reason_code": "not_checked",
        },
        "details": details.unwrap_or(Value::Null),
    })
}

fn annotate_llm_preflight_metadata(mut metadata: Value, llm_config: &Value) -> Value {
    if let Some(llm) = metadata.get_mut("llm").and_then(Value::as_object_mut) {
        llm.insert(
            "credential_source".to_string(),
            Value::String(
                read_string(llm_config, "credentialSource")
                    .unwrap_or_else(|| "app_config".to_string()),
            ),
        );
        if let Some(api_key_ref) = read_string(llm_config, "llmApiKeyRef") {
            llm.insert("api_key_ref".to_string(), Value::String(api_key_ref));
        }
    }
    metadata
}

fn add_preflight_attempt_metadata(
    mut metadata: Value,
    attempted_row_ids: &[String],
    winning_row_id: Option<&str>,
    winning_fingerprint: Option<&str>,
) -> Value {
    if let Some(map) = metadata.as_object_mut() {
        map.insert(
            "preflightRows".to_string(),
            json!({
                "attemptedRowIds": attempted_row_ids,
                "winningRowId": winning_row_id,
                "winningFingerprint": winning_fingerprint,
            }),
        );
    }
    metadata
}

fn normalize_provider_for_route(provider: &str) -> String {
    let normalized = normalize_provider_id(provider);
    if normalized.is_empty() {
        "openai_compatible".to_string()
    } else {
        normalized
    }
}

fn read_string(value: &Value, key: &str) -> Option<String> {
    value.get(key)?.as_str().map(str::to_string)
}

fn internal_error(error: anyhow::Error) -> ApiError {
    ApiError::Internal(error.to_string())
}

fn llm_gate_bad_request(error: LlmGateError) -> ApiError {
    ApiError::BadRequest(error.message)
}

async fn sync_python_user_config_mirror(
    state: &AppState,
    payload: Option<&SystemConfigPayload>,
) -> Result<(), ApiError> {
    let Some(pool) = &state.db_pool else {
        return Ok(());
    };

    let bootstrap_user_id: Option<String> =
        sqlx::query_scalar("select id from users order by created_at asc limit 1")
            .fetch_optional(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;

    let Some(bootstrap_user_id) = bootstrap_user_id else {
        return Ok(());
    };

    match payload {
        Some(payload) => {
            let (encrypted_llm_config, legacy_other_config) =
                prepare_legacy_user_config_payload(payload, &state.config.secret_key)
                    .map_err(internal_error)?;
            sqlx::query(
                r#"
                insert into user_configs (id, user_id, llm_config, other_config)
                values ($1, $2, $3, $4)
                on conflict (user_id) do update
                set llm_config = excluded.llm_config,
                    other_config = excluded.other_config,
                    updated_at = now()
                "#,
            )
            .bind(Uuid::new_v4().to_string())
            .bind(bootstrap_user_id)
            .bind(encrypted_llm_config.to_string())
            .bind(legacy_other_config.to_string())
            .execute(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        }
        None => {
            sqlx::query("delete from user_configs where user_id = $1")
                .bind(bootstrap_user_id)
                .execute(pool)
                .await
                .map_err(|error| ApiError::Internal(error.to_string()))?;
        }
    }

    Ok(())
}

fn prepare_legacy_user_config_payload(
    payload: &SystemConfigPayload,
    secret_key: &str,
) -> Result<(Value, Value), anyhow::Error> {
    Ok((
        encrypt_sensitive_fields(&payload.llm_config, secret_key)?,
        payload.other_config.clone(),
    ))
}

#[cfg(test)]
mod tests {
    use super::{default_config, prepare_legacy_user_config_payload};
    use crate::{config::AppConfig, core::encryption::decrypt_sensitive_string};
    use serde_json::json;

    #[test]
    fn default_config_reads_runtime_defaults_from_app_config() {
        let mut config = AppConfig::for_tests();
        config.llm_provider = "gemini".to_string();
        config.llm_model = "gemini-2.5-pro".to_string();
        config.llm_base_url = "https://example.test/v1".to_string();
        config.llm_timeout_seconds = 123;
        config.agent_timeout_seconds = 456;
        config.sub_agent_timeout_seconds = 789;
        config.tool_timeout_seconds = 42;
        config.max_analyze_files = 77;
        config.llm_concurrency = 9;
        config.llm_gap_ms = 444;
        config.llm_api_key = "sk-app-default".to_string();
        config.gemini_api_key = "gemini-secret".to_string();
        config.openai_api_key = "openai-secret".to_string();
        config.doubao_api_key = "doubao-secret".to_string();
        config.ollama_base_url = "http://ollama.internal/v1".to_string();

        let defaults = default_config(&config);
        assert_eq!(defaults.llm_config["schemaVersion"], 2);
        let row = &defaults.llm_config["rows"][0];
        assert_eq!(row["provider"], "openai_compatible");
        assert_eq!(row["model"], "gemini-2.5-pro");
        assert_eq!(row["baseUrl"], "https://example.test/v1");
        assert_eq!(row["advanced"]["llmTimeout"], 123_000);
        assert_eq!(row["advanced"]["agentTimeout"], 456);
        assert_eq!(row["advanced"]["subAgentTimeout"], 789);
        assert_eq!(row["advanced"]["toolTimeout"], 42);
        assert_eq!(row["apiKey"], "");
        assert_eq!(defaults.other_config["maxAnalyzeFiles"], 77);
        assert_eq!(defaults.other_config["llmConcurrency"], 9);
        assert_eq!(defaults.other_config["llmGapMs"], 444);
    }

    #[test]
    fn legacy_payload_encrypts_sensitive_llm_fields_only() {
        let payload = super::SystemConfigPayload {
            llm_config: json!({
                "llmApiKey": "sk-test-openai",
                "openaiApiKey": "sk-provider",
                "llmModel": "gpt-5",
                "llmBaseUrl": "https://api.openai.com/v1"
            }),
            other_config: json!({
                "llmConcurrency": 3
            }),
            llm_test_metadata: json!({}),
        };

        let (legacy_llm_config, legacy_other_config) =
            prepare_legacy_user_config_payload(&payload, "test-secret")
                .expect("legacy payload should build");
        assert_ne!(
            legacy_llm_config["llmApiKey"],
            payload.llm_config["llmApiKey"]
        );
        assert_ne!(
            legacy_llm_config["openaiApiKey"],
            payload.llm_config["openaiApiKey"]
        );
        assert_eq!(
            legacy_llm_config["llmModel"],
            payload.llm_config["llmModel"]
        );
        assert_eq!(
            legacy_llm_config["llmBaseUrl"],
            payload.llm_config["llmBaseUrl"]
        );
        assert_eq!(legacy_other_config, payload.other_config);

        let decrypted = decrypt_sensitive_string(
            legacy_llm_config["llmApiKey"].as_str().unwrap(),
            "test-secret",
        )
        .expect("encrypted mirror field should decrypt");
        assert_eq!(decrypted, "sk-test-openai");
    }
}
