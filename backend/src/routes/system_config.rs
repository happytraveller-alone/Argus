use std::{collections::BTreeMap, env, path::Path};

use axum::{
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
        metadata_matches, normalize_base_url, normalize_provider_id, normalize_stored_llm_config,
        parse_custom_headers, provider_api_key_field, provider_catalog,
        provider_catalog_entry_or_fallback, recommend_tokens, sanitize_llm_config_for_save,
        test_llm_generation, LlmGateError, ProviderCatalogItem as LlmProviderItem,
    },
    runtime::agentflow::codex_config::build_agentflow_llm_config,
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
const REDACTED_SECRET_PLACEHOLDER: &str = "***configured***";

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

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FetchModelsRequest {
    pub provider: String,
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
        .route("/import-env", post(import_env))
        .route("/fetch-llm-models", post(fetch_llm_models))
        .route("/agent-preflight", post(agent_preflight))
}

pub async fn get_defaults(State(state): State<AppState>) -> Json<SystemConfigPayload> {
    Json(public_payload(default_config(state.config.as_ref())))
}

pub async fn get_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    Ok(Json(public_payload(merge_with_defaults(
        state.config.as_ref(),
        stored,
    ))))
}

pub async fn put_current(
    State(state): State<AppState>,
    Json(payload): Json<SystemConfigPayload>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let defaults = default_config(state.config.as_ref());
    let existing = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let merged_input_llm = merge_json(&defaults.llm_config, &payload.llm_config);
    let next_llm_input = resolve_llm_secret_for_save(
        &merged_input_llm,
        existing.as_ref().map(|stored| &stored.llm_config_json),
        "saved",
    )
    .map_err(llm_gate_bad_request)?;
    let next_llm = sanitize_llm_config_for_save(&next_llm_input).map_err(llm_gate_bad_request)?;
    let next_other = merge_json(&defaults.other_config, &payload.other_config);
    let next_runtime =
        build_runtime_config(&next_llm, &next_other).map_err(llm_gate_bad_request)?;
    let next_fingerprint = compute_llm_fingerprint(&next_runtime);
    let next_metadata = existing
        .as_ref()
        .map(|stored| &stored.llm_test_metadata_json)
        .filter(|metadata| metadata_matches(metadata, &next_fingerprint))
        .cloned()
        .unwrap_or_else(|| json!({}));
    let stored = system_config::save_current(&state, next_llm, next_other, next_metadata)
        .await
        .map_err(internal_error)?;

    let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
    sync_python_user_config_mirror(&state, Some(&merged)).await?;
    Ok(Json(public_payload(merged)))
}

pub async fn delete_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    system_config::clear_current(&state)
        .await
        .map_err(internal_error)?;
    sync_python_user_config_mirror(&state, None).await?;
    Ok(Json(public_payload(default_config(state.config.as_ref()))))
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
    let provider = normalize_provider_for_route(&request.provider);
    let model = request.model.clone().unwrap_or_default().trim().to_string();
    let base_url = request
        .base_url
        .clone()
        .unwrap_or_default()
        .trim()
        .to_string();
    let request_custom_headers_value = request
        .custom_headers
        .as_ref()
        .map(|headers| Value::String(headers.clone()));
    let request_custom_headers = parse_custom_headers(request_custom_headers_value.as_ref())
        .map_err(ApiError::BadRequest)?;
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::BadRequest("请先保存 LLM 配置，再执行连接测试。".to_string()))?;
    let api_key = resolve_test_api_key(&request, &stored.llm_config_json)?;
    let stored_custom_headers =
        parse_custom_headers(stored.llm_config_json.get("llmCustomHeaders"))
            .map_err(ApiError::BadRequest)?;
    if provider != read_string(&stored.llm_config_json, "llmProvider").unwrap_or_default()
        || model != read_string(&stored.llm_config_json, "llmModel").unwrap_or_default()
        || normalize_base_url(&base_url)
            != normalize_base_url(
                &read_string(&stored.llm_config_json, "llmBaseUrl").unwrap_or_default(),
            )
        || api_key != read_string(&stored.llm_config_json, "llmApiKey").unwrap_or_default()
        || request_custom_headers != stored_custom_headers
    {
        return Ok(Json(LlmTestResponse {
            success: false,
            message: "当前测试请求与已保存 LLM 配置不一致，请先保存后再测试。".to_string(),
            model: None,
            response: None,
            metadata: None,
        }));
    }
    let runtime = match build_runtime_config(&stored.llm_config_json, &stored.other_config_json) {
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
    match test_llm_generation(&state.http_client, &runtime).await {
        Ok(outcome) => {
            let metadata = outcome.metadata();
            let stored = system_config::save_current(
                &state,
                stored.llm_config_json,
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
            let current_fingerprint = compute_llm_fingerprint(&runtime);
            let metadata = if metadata_matches(&stored.llm_test_metadata_json, &current_fingerprint)
            {
                json!({})
            } else {
                stored.llm_test_metadata_json
            };
            let _ = system_config::save_current(
                &state,
                stored.llm_config_json,
                stored.other_config_json,
                metadata,
            )
            .await;
            Ok(Json(LlmTestResponse {
                success: false,
                message: error.message,
                model: None,
                response: None,
                metadata: None,
            }))
        }
    }
}

pub async fn import_env(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ImportEnvResponse>, ApiError> {
    verify_import_token(&headers)?;
    let defaults = default_config(state.config.as_ref());
    let imported_llm = import_llm_config_from_env(&defaults.llm_config)?;
    let imported_other = merge_json(&defaults.other_config, &json!({}));
    let runtime =
        build_runtime_config(&imported_llm, &imported_other).map_err(llm_gate_bad_request)?;

    match test_llm_generation(&state.http_client, &runtime).await {
        Ok(outcome) => {
            let metadata = outcome.metadata();
            let stored = system_config::save_current(
                &state,
                mark_imported_system_config(&imported_llm),
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
            let stored = system_config::save_current(
                &state,
                mark_imported_system_config(&imported_llm),
                imported_other,
                json!({}),
            )
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
    Json(request): Json<FetchModelsRequest>,
) -> Result<Json<FetchModelsResponse>, ApiError> {
    let provider = normalize_provider_for_route(&request.provider);
    let provider_item = provider_catalog_entry_or_fallback(&provider);
    parse_custom_headers(request.custom_headers.as_ref()).map_err(ApiError::BadRequest)?;
    let base_url_used = request
        .base_url
        .as_deref()
        .map(normalize_base_url)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            if provider_item.default_base_url.is_empty() {
                None
            } else {
                Some(provider_item.default_base_url.clone())
            }
        });

    let model_metadata = provider_item
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
        .collect();

    Ok(Json(FetchModelsResponse {
        success: true,
        message: format!("已返回 {} 个内置模型", provider_item.models.len()),
        provider: request.provider,
        resolved_provider: provider.clone(),
        models: provider_item.models,
        default_model: provider_item.default_model,
        source: "fallback_static".to_string(),
        base_url_used,
        model_metadata,
        token_recommendation_source: "static_mapping".to_string(),
    }))
}

pub async fn agent_preflight(
    State(state): State<AppState>,
) -> Result<Json<AgentPreflightPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    let saved_llm_config = stored.as_ref().map(|saved| &saved.llm_config_json);
    let effective_llm_config = build_agentflow_llm_config(state.config.as_ref(), saved_llm_config);
    let effective_snapshot = build_quick_snapshot(&effective_llm_config);
    let credential_source = read_string(&effective_llm_config, "credentialSource")
        .unwrap_or_else(|| "app_config".to_string());

    if stored.is_none() && credential_source == "app_config" {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_config".to_string()),
            message: "检测到当前仍在使用默认 LLM 配置，请先保存并测试专属 LLM 配置。".to_string(),
            reason_code: Some("default_config".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: None,
            metadata: Some(annotate_llm_preflight_metadata(
                agent_preflight_metadata("llm_config", "default_config", None),
                &effective_llm_config,
            )),
            llm_test_metadata: None,
        }));
    }

    let saved_snapshot = saved_llm_config.map(build_quick_snapshot);
    let missing_fields = collect_missing_fields(&effective_snapshot);
    if !missing_fields.is_empty() {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_config".to_string()),
            message: format!(
                "智能审计初始化失败：LLM 缺少必填配置 {}，请先补全并保存。",
                missing_fields.join("、")
            ),
            reason_code: Some("missing_fields".to_string()),
            missing_fields: Some(missing_fields),
            effective_config: effective_snapshot,
            saved_config: saved_snapshot,
            metadata: Some(annotate_llm_preflight_metadata(
                agent_preflight_metadata("llm_config", "missing_fields", None),
                &effective_llm_config,
            )),
            llm_test_metadata: None,
        }));
    }

    let Some(stored_config) = stored.as_ref() else {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_config".to_string()),
            message: "智能审计初始化失败：请先保存并测试专属 LLM 配置。".to_string(),
            reason_code: Some("default_config".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: saved_snapshot,
            metadata: Some(annotate_llm_preflight_metadata(
                agent_preflight_metadata("llm_config", "default_config", None),
                &effective_llm_config,
            )),
            llm_test_metadata: None,
        }));
    };
    let runtime = match build_runtime_config(
        &stored_config.llm_config_json,
        &stored_config.other_config_json,
    ) {
        Ok(runtime) => runtime,
        Err(error) => {
            return Ok(Json(AgentPreflightPayload {
                ok: false,
                stage: Some("llm_config".to_string()),
                message: error.message,
                reason_code: Some(error.reason_code.to_string()),
                missing_fields: None,
                effective_config: effective_snapshot,
                saved_config: saved_snapshot,
                metadata: Some(annotate_llm_preflight_metadata(
                    agent_preflight_metadata("llm_config", error.reason_code, None),
                    &effective_llm_config,
                )),
                llm_test_metadata: None,
            }))
        }
    };
    let fingerprint = compute_llm_fingerprint(&runtime);
    if !metadata_matches(&stored_config.llm_test_metadata_json, &fingerprint) {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_test".to_string()),
            message: "智能审计初始化失败：LLM 测试证据缺失或已过期，请重新保存并测试。".to_string(),
            reason_code: Some("llm_test_stale".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: saved_snapshot,
            metadata: Some(annotate_llm_preflight_metadata(
                agent_preflight_metadata("llm_test", "llm_test_stale", None),
                &effective_llm_config,
            )),
            llm_test_metadata: Some(stored_config.llm_test_metadata_json.clone()),
        }));
    }
    let outcome = match test_llm_generation(&state.http_client, &runtime).await {
        Ok(outcome) => outcome,
        Err(error) => {
            return Ok(Json(AgentPreflightPayload {
                ok: false,
                stage: Some("llm_test".to_string()),
                message: error.message,
                reason_code: Some(error.reason_code.to_string()),
                missing_fields: None,
                effective_config: effective_snapshot,
                saved_config: saved_snapshot,
                metadata: Some(annotate_llm_preflight_metadata(
                    agent_preflight_metadata("llm_test", error.reason_code, None),
                    &effective_llm_config,
                )),
                llm_test_metadata: Some(stored_config.llm_test_metadata_json.clone()),
            }))
        }
    };

    let runner_metadata = annotate_llm_preflight_metadata(
        agentflow_runner_preflight_metadata(state.config.as_ref()),
        &effective_llm_config,
    );
    if runner_metadata["runner"]["ok"] != true {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("runner".to_string()),
            message: "智能审计初始化失败：AgentFlow runner 尚未配置或不可用。".to_string(),
            reason_code: Some("runner_missing".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: saved_snapshot,
            metadata: Some(runner_metadata),
            llm_test_metadata: Some(outcome.metadata()),
        }));
    }

    Ok(Json(AgentPreflightPayload {
        ok: true,
        stage: None,
        message: "智能审计预检通过。".to_string(),
        reason_code: None,
        missing_fields: None,
        effective_config: effective_snapshot,
        saved_config: saved_snapshot,
        metadata: Some(runner_metadata),
        llm_test_metadata: Some(outcome.metadata()),
    }))
}

pub fn default_config(config: &AppConfig) -> SystemConfigPayload {
    SystemConfigPayload {
        llm_config: json!({
            "llmConfigVersion": crate::llm::LLM_CONFIG_VERSION,
            "llmProvider": if is_supported_protocol_provider(&config.llm_provider) { config.llm_provider.as_str() } else { "openai_compatible" },
            "llmApiKey": "",
            "llmModel": config.llm_model,
            "llmBaseUrl": config.llm_base_url,
            "llmTimeout": config.llm_timeout_seconds * 1000,
            "llmTemperature": config.llm_temperature,
            "llmMaxTokens": config.llm_max_tokens,
            "llmCustomHeaders": "",
            "llmFirstTokenTimeout": config.llm_first_token_timeout_seconds,
            "llmStreamTimeout": config.llm_stream_timeout_seconds,
            "agentTimeout": config.agent_timeout_seconds,
            "subAgentTimeout": config.sub_agent_timeout_seconds,
            "toolTimeout": config.tool_timeout_seconds,
            "geminiApiKey": "",
            "openaiApiKey": "",
            "claudeApiKey": "",
            "qwenApiKey": "",
            "deepseekApiKey": "",
            "zhipuApiKey": "",
            "moonshotApiKey": "",
            "baiduApiKey": "",
            "minimaxApiKey": "",
            "doubaoApiKey": "",
            "ollamaBaseUrl": config.ollama_base_url
        }),
        other_config: json!({
            "maxAnalyzeFiles": config.max_analyze_files,
            "llmConcurrency": config.llm_concurrency,
            "llmGapMs": config.llm_gap_ms
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
            let (llm_config, llm_test_metadata, _) = normalize_stored_llm_config(
                &stored.llm_config_json,
                &stored.llm_test_metadata_json,
            );
            SystemConfigPayload {
                llm_config: merge_json(&defaults.llm_config, &llm_config),
                other_config: merge_json(&defaults.other_config, &stored.other_config_json),
                llm_test_metadata,
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

fn public_payload(mut payload: SystemConfigPayload) -> SystemConfigPayload {
    payload.llm_config = redact_llm_config_for_response(&payload.llm_config);
    payload
}

fn redact_llm_config_for_response(llm_config: &Value) -> Value {
    let mut redacted = match llm_config {
        Value::Object(map) => Value::Object(map.clone()),
        _ => llm_config.clone(),
    };
    let has_saved_api_key = read_string(llm_config, "llmApiKey")
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false);
    if let Some(map) = redacted.as_object_mut() {
        for key in [
            "llmApiKey",
            "openaiApiKey",
            "claudeApiKey",
            "geminiApiKey",
            "qwenApiKey",
            "deepseekApiKey",
            "zhipuApiKey",
            "moonshotApiKey",
            "baiduApiKey",
            "minimaxApiKey",
            "doubaoApiKey",
        ] {
            if map.contains_key(key) {
                map.insert(key.to_string(), Value::String(String::new()));
            }
        }
        map.insert("hasSavedApiKey".to_string(), Value::Bool(has_saved_api_key));
        let secret_source = read_string(llm_config, "secretSource")
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| {
                if has_saved_api_key {
                    "saved".to_string()
                } else {
                    "none".to_string()
                }
            });
        map.insert("secretSource".to_string(), Value::String(secret_source));
    }
    redacted
}

fn resolve_llm_secret_for_save(
    llm_config: &Value,
    existing_llm_config: Option<&Value>,
    default_secret_source: &str,
) -> Result<Value, LlmGateError> {
    let mut resolved = match llm_config {
        Value::Object(map) => Value::Object(map.clone()),
        _ => llm_config.clone(),
    };
    let api_key = read_string(&resolved, "llmApiKey").unwrap_or_default();
    if api_key.trim() == REDACTED_SECRET_PLACEHOLDER {
        return Err(LlmGateError::new(
            "redacted_secret_placeholder",
            "请明确选择使用已保存密钥或重新输入密钥，不能提交脱敏占位符。",
        ));
    }
    let requested_source = read_string(&resolved, "secretSource").unwrap_or_default();
    let wants_saved_secret = matches!(
        requested_source.as_str(),
        "saved" | "imported" | "use_saved" | "use_imported"
    );
    if api_key.trim().is_empty() && wants_saved_secret {
        let existing_key = existing_llm_config
            .and_then(|value| read_string(value, "llmApiKey"))
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| {
                LlmGateError::new(
                    "missing_saved_secret",
                    "当前没有可复用的已保存 LLM 密钥，请重新输入密钥。",
                )
            })?;
        if let Some(map) = resolved.as_object_mut() {
            map.insert("llmApiKey".to_string(), Value::String(existing_key));
            map.insert(
                "secretSource".to_string(),
                Value::String(
                    if requested_source == "imported" || requested_source == "use_imported" {
                        "imported".to_string()
                    } else {
                        "saved".to_string()
                    },
                ),
            );
        }
    } else if !api_key.trim().is_empty() {
        if let Some(map) = resolved.as_object_mut() {
            map.insert(
                "secretSource".to_string(),
                Value::String(default_secret_source.to_string()),
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
    }
    Ok(resolved)
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

fn collect_missing_fields(snapshot: &LlmQuickConfigSnapshot) -> Vec<String> {
    let mut missing = Vec::new();
    if snapshot.model.trim().is_empty() {
        missing.push("llmModel".to_string());
    }
    if snapshot.base_url.trim().is_empty() {
        missing.push("llmBaseUrl".to_string());
    }
    if snapshot.api_key.trim().is_empty() && !snapshot.has_saved_api_key {
        missing.push("llmApiKey".to_string());
    }
    missing
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

fn agentflow_runner_preflight_metadata(config: &AppConfig) -> Value {
    let compose_path = Path::new("docker-compose.yml");
    let pipeline_path = if Path::new("backend/agentflow/pipelines/intelligent_audit.py").exists() {
        Path::new("backend/agentflow/pipelines/intelligent_audit.py")
    } else {
        Path::new("agentflow/pipelines/intelligent_audit.py")
    };
    let compose_has_runner = std::fs::read_to_string(compose_path)
        .map(|content| content.contains("agentflow-runner"))
        .unwrap_or(false);
    let runner_command_configured = std::env::var("AGENTFLOW_RUNNER_COMMAND")
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false);
    let default_runner_enabled = env_flag_enabled("AGENTFLOW_DEFAULT_RUNNER_ENABLED", true);
    let runner_ok = compose_has_runner || runner_command_configured || default_runner_enabled;
    let pipeline_ok = pipeline_path.exists();
    let output_dir_ok = config
        .zip_storage_path
        .parent()
        .map(|path| path.exists() || std::fs::create_dir_all(path).is_ok())
        .unwrap_or(true);
    let resource_ok =
        config.runner_preflight_max_concurrency > 0 && config.agent_timeout_seconds > 0;

    json!({
        "llm": {
            "ok": true,
            "reason_code": Value::Null,
        },
        "runner": {
            "ok": runner_ok,
            "reason_code": if runner_ok { Value::Null } else { json!("runner_missing") },
            "compose_has_agentflow_runner": compose_has_runner,
            "runner_command_configured": runner_command_configured,
            "default_runner_enabled": default_runner_enabled,
        },
        "pipeline": {
            "ok": pipeline_ok,
            "reason_code": if pipeline_ok { Value::Null } else { json!("pipeline_invalid") },
            "path": pipeline_path.display().to_string(),
        },
        "output_dir": {
            "ok": output_dir_ok,
            "reason_code": if output_dir_ok { Value::Null } else { json!("output_dir_unwritable") },
            "path": config.zip_storage_path.display().to_string(),
        },
        "resource": {
            "ok": resource_ok,
            "reason_code": if resource_ok { Value::Null } else { json!("resource_unavailable") },
            "max_concurrency": config.runner_preflight_max_concurrency,
            "agent_timeout_seconds": config.agent_timeout_seconds,
        },
    })
}

fn env_flag_enabled(key: &str, default: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            !matches!(
                normalized.as_str(),
                "0" | "false" | "no" | "off" | "disabled"
            )
        })
        .unwrap_or(default)
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
        assert_eq!(defaults.llm_config["llmProvider"], "openai_compatible");
        assert_eq!(defaults.llm_config["llmModel"], "gemini-2.5-pro");
        assert_eq!(defaults.llm_config["llmBaseUrl"], "https://example.test/v1");
        assert_eq!(defaults.llm_config["llmTimeout"], 123_000);
        assert_eq!(defaults.llm_config["agentTimeout"], 456);
        assert_eq!(defaults.llm_config["subAgentTimeout"], 789);
        assert_eq!(defaults.llm_config["toolTimeout"], 42);
        assert_eq!(defaults.llm_config["llmApiKey"], "");
        assert_eq!(defaults.llm_config["geminiApiKey"], "");
        assert_eq!(defaults.llm_config["openaiApiKey"], "");
        assert_eq!(defaults.llm_config["doubaoApiKey"], "");
        assert_eq!(
            defaults.llm_config["ollamaBaseUrl"],
            "http://ollama.internal/v1"
        );
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
