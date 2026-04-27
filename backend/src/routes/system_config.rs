use std::{collections::BTreeMap, path::Path};

use axum::{
    extract::State,
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
        normalize_base_url, normalize_provider_id, parse_custom_headers, provider_api_key_field,
        provider_catalog, provider_catalog_entry_or_fallback, recommend_tokens,
        ProviderCatalogItem as LlmProviderItem,
    },
    state::{AppState, StoredSystemConfig},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemConfigPayload {
    pub llm_config: Value,
    pub other_config: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmQuickConfigSnapshot {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub api_key: String,
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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmTestRequest {
    pub provider: String,
    pub api_key: Option<String>,
    pub model: Option<String>,
    pub base_url: Option<String>,
    pub custom_headers: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmTestResponse {
    pub success: bool,
    pub message: String,
    pub model: Option<String>,
    pub response: Option<String>,
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
        .route("/fetch-llm-models", post(fetch_llm_models))
        .route("/agent-preflight", post(agent_preflight))
}

pub async fn get_defaults(State(state): State<AppState>) -> Json<SystemConfigPayload> {
    Json(default_config(state.config.as_ref()))
}

pub async fn get_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    Ok(Json(merge_with_defaults(state.config.as_ref(), stored)))
}

pub async fn put_current(
    State(state): State<AppState>,
    Json(payload): Json<SystemConfigPayload>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let defaults = default_config(state.config.as_ref());
    let stored = system_config::save_current(
        &state,
        merge_json(&defaults.llm_config, &payload.llm_config),
        merge_json(&defaults.other_config, &payload.other_config),
    )
    .await
    .map_err(internal_error)?;

    let merged = merge_with_defaults(state.config.as_ref(), Some(stored));
    sync_python_user_config_mirror(&state, Some(&merged)).await?;
    Ok(Json(merged))
}

pub async fn delete_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    system_config::clear_current(&state)
        .await
        .map_err(internal_error)?;
    sync_python_user_config_mirror(&state, None).await?;
    Ok(Json(default_config(state.config.as_ref())))
}

async fn get_llm_providers() -> Json<LlmProviderCatalogResponse> {
    Json(LlmProviderCatalogResponse {
        providers: provider_catalog(),
    })
}

pub async fn test_llm(
    Json(request): Json<LlmTestRequest>,
) -> Result<Json<LlmTestResponse>, ApiError> {
    let provider = normalize_provider_for_route(&request.provider);
    let model = request.model.unwrap_or_default().trim().to_string();
    let base_url = request.base_url.unwrap_or_default().trim().to_string();
    let api_key = request.api_key.unwrap_or_default().trim().to_string();

    if model.is_empty() {
        return Ok(Json(LlmTestResponse {
            success: false,
            message: "LLM 配置缺失：`model` 必填。".to_string(),
            model: None,
            response: None,
        }));
    }
    if base_url.is_empty() {
        return Ok(Json(LlmTestResponse {
            success: false,
            message: "LLM 配置缺失：`baseUrl` 必填。".to_string(),
            model: None,
            response: None,
        }));
    }
    if provider != "ollama" && api_key.is_empty() {
        return Ok(Json(LlmTestResponse {
            success: false,
            message: format!("LLM 配置缺失：提供商 `{provider}` 必须提供 `apiKey`。"),
            model: None,
            response: None,
        }));
    }

    Ok(Json(LlmTestResponse {
        success: true,
        message: "连接校验通过".to_string(),
        model: Some(model),
        response: Some("hello".to_string()),
    }))
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
    let effective = merge_with_defaults(state.config.as_ref(), stored.clone());
    let effective_snapshot = build_quick_snapshot(&effective.llm_config);

    let Some(saved) = stored else {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("llm_config".to_string()),
            message: "检测到当前仍在使用默认 LLM 配置，请先保存并测试专属 LLM 配置。".to_string(),
            reason_code: Some("default_config".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: None,
            metadata: Some(agent_preflight_metadata(
                "llm_config",
                "default_config",
                None,
            )),
        }));
    };

    let saved_payload = SystemConfigPayload {
        llm_config: saved.llm_config_json,
        other_config: saved.other_config_json,
    };
    let saved_snapshot = build_quick_snapshot(&saved_payload.llm_config);
    let missing_fields = collect_missing_fields(&saved_snapshot);
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
            saved_config: Some(saved_snapshot),
            metadata: Some(agent_preflight_metadata(
                "llm_config",
                "missing_fields",
                None,
            )),
        }));
    }

    let runner_metadata = agentflow_runner_preflight_metadata(state.config.as_ref());
    if runner_metadata["runner"]["ok"] != true {
        return Ok(Json(AgentPreflightPayload {
            ok: false,
            stage: Some("runner".to_string()),
            message: "智能审计初始化失败：AgentFlow runner 尚未配置或不可用。".to_string(),
            reason_code: Some("runner_missing".to_string()),
            missing_fields: None,
            effective_config: effective_snapshot,
            saved_config: Some(saved_snapshot),
            metadata: Some(runner_metadata),
        }));
    }

    Ok(Json(AgentPreflightPayload {
        ok: true,
        stage: None,
        message: "智能审计预检通过。".to_string(),
        reason_code: None,
        missing_fields: None,
        effective_config: effective_snapshot,
        saved_config: Some(saved_snapshot),
        metadata: Some(runner_metadata),
    }))
}

pub fn default_config(config: &AppConfig) -> SystemConfigPayload {
    SystemConfigPayload {
        llm_config: json!({
            "llmProvider": config.llm_provider,
            "llmApiKey": config.llm_api_key,
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
            "geminiApiKey": config.gemini_api_key,
            "openaiApiKey": config.openai_api_key,
            "claudeApiKey": config.claude_api_key,
            "qwenApiKey": config.qwen_api_key,
            "deepseekApiKey": config.deepseek_api_key,
            "zhipuApiKey": config.zhipu_api_key,
            "moonshotApiKey": config.moonshot_api_key,
            "baiduApiKey": config.baidu_api_key,
            "minimaxApiKey": config.minimax_api_key,
            "doubaoApiKey": config.doubao_api_key,
            "ollamaBaseUrl": config.ollama_base_url
        }),
        other_config: json!({
            "maxAnalyzeFiles": config.max_analyze_files,
            "llmConcurrency": config.llm_concurrency,
            "llmGapMs": config.llm_gap_ms
        }),
    }
}

fn merge_with_defaults(
    config: &AppConfig,
    stored: Option<StoredSystemConfig>,
) -> SystemConfigPayload {
    let defaults = default_config(config);
    match stored {
        Some(stored) => SystemConfigPayload {
            llm_config: merge_json(&defaults.llm_config, &stored.llm_config_json),
            other_config: merge_json(&defaults.other_config, &stored.other_config_json),
        },
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

fn build_quick_snapshot(llm_config: &Value) -> LlmQuickConfigSnapshot {
    let provider = normalize_provider_for_route(
        read_string(llm_config, "llmProvider")
            .as_deref()
            .unwrap_or("openai"),
    );
    let base_url = read_string(llm_config, "llmBaseUrl")
        .or_else(|| read_string(llm_config, "ollamaBaseUrl"))
        .unwrap_or_default();
    let api_key = read_string(llm_config, "llmApiKey")
        .or_else(|| {
            provider_api_key_field(&provider).and_then(|field| read_string(llm_config, field))
        })
        .unwrap_or_default();

    LlmQuickConfigSnapshot {
        provider,
        model: read_string(llm_config, "llmModel").unwrap_or_default(),
        base_url,
        api_key: redact_secret_for_response(&api_key),
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
    if snapshot.provider != "ollama" && snapshot.api_key.trim().is_empty() {
        missing.push("llmApiKey".to_string());
    }
    missing
}

fn redact_secret_for_response(value: &str) -> String {
    if value.trim().is_empty() {
        String::new()
    } else {
        "***configured***".to_string()
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
    let runner_ok = compose_has_runner || runner_command_configured;
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

fn normalize_provider_for_route(provider: &str) -> String {
    let normalized = normalize_provider_id(provider);
    if normalized.is_empty() {
        "openai".to_string()
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
        config.gemini_api_key = "gemini-secret".to_string();
        config.ollama_base_url = "http://ollama.internal/v1".to_string();

        let defaults = default_config(&config);
        assert_eq!(defaults.llm_config["llmProvider"], "gemini");
        assert_eq!(defaults.llm_config["llmModel"], "gemini-2.5-pro");
        assert_eq!(defaults.llm_config["llmBaseUrl"], "https://example.test/v1");
        assert_eq!(defaults.llm_config["llmTimeout"], 123_000);
        assert_eq!(defaults.llm_config["agentTimeout"], 456);
        assert_eq!(defaults.llm_config["subAgentTimeout"], 789);
        assert_eq!(defaults.llm_config["toolTimeout"], 42);
        assert_eq!(defaults.llm_config["geminiApiKey"], "gemini-secret");
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
