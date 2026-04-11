use std::collections::BTreeMap;

use axum::{
    extract::State,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::{
    db::system_config,
    error::ApiError,
    state::{AppState, StoredSystemConfig},
};

const DEFAULT_LLM_TIMEOUT_MS: i64 = 300_000;
const DEFAULT_AGENT_TIMEOUT_SECONDS: i64 = 3_600;
const DEFAULT_SUB_AGENT_TIMEOUT_SECONDS: i64 = 1_200;
const DEFAULT_TOOL_TIMEOUT_SECONDS: i64 = 120;
const DEFAULT_LLM_FIRST_TOKEN_TIMEOUT_SECONDS: i64 = 180;
const DEFAULT_LLM_STREAM_TIMEOUT_SECONDS: i64 = 180;
const DEFAULT_LLM_MAX_TOKENS: i64 = 16_384;
const DEFAULT_LLM_CONCURRENCY: i64 = 1;
const DEFAULT_LLM_GAP_MS: i64 = 3_000;

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
    pub custom_headers: Option<String>,
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

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmProviderItem {
    id: String,
    name: String,
    description: String,
    default_model: String,
    models: Vec<String>,
    default_base_url: String,
    requires_api_key: bool,
    supports_model_fetch: bool,
    fetch_style: &'static str,
    example_base_urls: Vec<String>,
    supports_custom_headers: bool,
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

pub async fn get_defaults() -> Json<SystemConfigPayload> {
    Json(default_config())
}

pub async fn get_current(
    State(state): State<AppState>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let stored = system_config::load_current(&state)
        .await
        .map_err(internal_error)?;
    Ok(Json(merge_with_defaults(stored)))
}

pub async fn put_current(
    State(state): State<AppState>,
    Json(payload): Json<SystemConfigPayload>,
) -> Result<Json<SystemConfigPayload>, ApiError> {
    let defaults = default_config();
    let stored = system_config::save_current(
        &state,
        merge_json(&defaults.llm_config, &payload.llm_config),
        merge_json(&defaults.other_config, &payload.other_config),
    )
    .await
    .map_err(internal_error)?;

    let merged = merge_with_defaults(Some(stored));
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
    Ok(Json(default_config()))
}

async fn get_llm_providers() -> Json<LlmProviderCatalogResponse> {
    Json(LlmProviderCatalogResponse {
        providers: builtin_providers(),
    })
}

pub async fn test_llm(
    Json(request): Json<LlmTestRequest>,
) -> Result<Json<LlmTestResponse>, ApiError> {
    let provider = normalize_provider_id(&request.provider);
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
    let provider = normalize_provider_id(&request.provider);
    let provider_item = builtin_providers()
        .into_iter()
        .find(|item| item.id == provider)
        .unwrap_or_else(|| fallback_provider(&provider));

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
        base_url_used: request.base_url.or(Some(provider_item.default_base_url)),
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
    let effective = merge_with_defaults(stored.clone());
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
                "智能扫描初始化失败：LLM 缺少必填配置 {}，请先补全并保存。",
                missing_fields.join("、")
            ),
            reason_code: Some("missing_fields".to_string()),
            missing_fields: Some(missing_fields),
            effective_config: effective_snapshot,
            saved_config: Some(saved_snapshot),
        }));
    }

    Ok(Json(AgentPreflightPayload {
        ok: true,
        stage: None,
        message: "LLM 配置测试通过。".to_string(),
        reason_code: None,
        missing_fields: None,
        effective_config: effective_snapshot,
        saved_config: Some(saved_snapshot),
    }))
}

pub fn default_config() -> SystemConfigPayload {
    SystemConfigPayload {
        llm_config: json!({
            "llmProvider": "openai",
            "llmApiKey": "",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.openai.com/v1",
            "llmTimeout": DEFAULT_LLM_TIMEOUT_MS,
            "llmTemperature": 0.05,
            "llmMaxTokens": DEFAULT_LLM_MAX_TOKENS,
            "llmCustomHeaders": "",
            "llmFirstTokenTimeout": DEFAULT_LLM_FIRST_TOKEN_TIMEOUT_SECONDS,
            "llmStreamTimeout": DEFAULT_LLM_STREAM_TIMEOUT_SECONDS,
            "agentTimeout": DEFAULT_AGENT_TIMEOUT_SECONDS,
            "subAgentTimeout": DEFAULT_SUB_AGENT_TIMEOUT_SECONDS,
            "toolTimeout": DEFAULT_TOOL_TIMEOUT_SECONDS,
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
            "ollamaBaseUrl": "http://localhost:11434/v1"
        }),
        other_config: json!({
            "maxAnalyzeFiles": 0,
            "llmConcurrency": DEFAULT_LLM_CONCURRENCY,
            "llmGapMs": DEFAULT_LLM_GAP_MS
        }),
    }
}

fn merge_with_defaults(stored: Option<StoredSystemConfig>) -> SystemConfigPayload {
    let defaults = default_config();
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
    let provider = normalize_provider_id(
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
        api_key,
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

fn builtin_providers() -> Vec<LlmProviderItem> {
    vec![
        provider(
            "custom",
            "OpenAI Compatible",
            "适用于 OpenAI 兼容站点、中转服务和自建网关。",
            "gpt-5",
            vec!["gpt-5", "kimi-k2", "deepseek-chat", "qwen-max"],
            "",
            true,
            "openai_compatible",
            vec![
                "https://api.openai.com/v1",
                "https://api.moonshot.cn/v1",
                "http://localhost:11434/v1",
            ],
        ),
        provider(
            "openai",
            "OpenAI",
            "OpenAI 官方接口。",
            "gpt-5",
            vec!["gpt-5", "gpt-5.1", "gpt-4o", "gpt-4o-mini"],
            "https://api.openai.com/v1",
            true,
            "openai_compatible",
            vec!["https://api.openai.com/v1"],
        ),
        provider(
            "openrouter",
            "OpenRouter",
            "统一多模型路由聚合服务（OpenAI 兼容）。",
            "openai/gpt-5-mini",
            vec![
                "openai/gpt-5-mini",
                "anthropic/claude-3.7-sonnet",
                "google/gemini-2.5-pro",
            ],
            "https://openrouter.ai/api/v1",
            true,
            "openai_compatible",
            vec!["https://openrouter.ai/api/v1"],
        ),
        provider(
            "anthropic",
            "Anthropic",
            "Claude 系列模型服务。",
            "claude-sonnet-4.5",
            vec!["claude-sonnet-4.5", "claude-opus-4.5", "claude-haiku-4.5"],
            "https://api.anthropic.com/v1",
            true,
            "anthropic",
            vec!["https://api.anthropic.com/v1"],
        ),
        provider(
            "azure_openai",
            "Azure OpenAI",
            "Azure 托管 OpenAI 接口。",
            "gpt-5",
            vec!["gpt-5", "gpt-4o", "o4-mini"],
            "https://{resource}.openai.azure.com/openai/v1",
            true,
            "azure_openai",
            vec!["https://{resource}.openai.azure.com/openai/v1"],
        ),
        provider(
            "moonshot",
            "Moonshot / Kimi",
            "Moonshot Kimi 官方接口（OpenAI 兼容）。",
            "kimi-k2",
            vec!["kimi-k2", "kimi-k2-thinking", "moonshot-v1-128k"],
            "https://api.moonshot.cn/v1",
            true,
            "openai_compatible",
            vec!["https://api.moonshot.cn/v1"],
        ),
        provider(
            "ollama",
            "Ollama",
            "本地部署 LLM（OpenAI 兼容，无需 API Key）。",
            "llama3.3-70b",
            vec!["llama3.3-70b", "qwen3-8b", "deepseek-r1"],
            "http://localhost:11434/v1",
            false,
            "openai_compatible",
            vec!["http://localhost:11434/v1"],
        ),
        provider(
            "gemini",
            "Google Gemini",
            "Google Gemini 模型服务。",
            "gemini-3-pro",
            vec!["gemini-3-pro", "gemini-2.5-pro", "gemini-2.5-flash"],
            "https://generativelanguage.googleapis.com/v1beta",
            true,
            "openai_compatible",
            vec![],
        ),
        provider(
            "deepseek",
            "DeepSeek",
            "DeepSeek 推理与对话模型。",
            "deepseek-v3.1-terminus",
            vec![
                "deepseek-v3.1-terminus",
                "deepseek-chat",
                "deepseek-reasoner",
            ],
            "https://api.deepseek.com",
            true,
            "openai_compatible",
            vec![],
        ),
    ]
}

fn provider(
    id: &str,
    name: &str,
    description: &str,
    default_model: &str,
    models: Vec<&str>,
    default_base_url: &str,
    requires_api_key: bool,
    fetch_style: &'static str,
    example_base_urls: Vec<&str>,
) -> LlmProviderItem {
    LlmProviderItem {
        id: id.to_string(),
        name: name.to_string(),
        description: description.to_string(),
        default_model: default_model.to_string(),
        models: models.into_iter().map(str::to_string).collect(),
        default_base_url: default_base_url.to_string(),
        requires_api_key,
        supports_model_fetch: true,
        fetch_style,
        example_base_urls: example_base_urls.into_iter().map(str::to_string).collect(),
        supports_custom_headers: true,
    }
}

fn fallback_provider(id: &str) -> LlmProviderItem {
    provider(
        id,
        id,
        "自定义模型提供商",
        "",
        vec![],
        "",
        id != "ollama",
        "openai_compatible",
        vec![],
    )
}

fn provider_api_key_field(provider: &str) -> Option<&'static str> {
    match provider {
        "custom" | "openai" | "openrouter" | "azure_openai" => Some("openaiApiKey"),
        "anthropic" | "claude" => Some("claudeApiKey"),
        "gemini" => Some("geminiApiKey"),
        "qwen" => Some("qwenApiKey"),
        "deepseek" => Some("deepseekApiKey"),
        "zhipu" => Some("zhipuApiKey"),
        "moonshot" => Some("moonshotApiKey"),
        "baidu" => Some("baiduApiKey"),
        "minimax" => Some("minimaxApiKey"),
        "doubao" => Some("doubaoApiKey"),
        _ => None,
    }
}

fn normalize_provider_id(provider: &str) -> String {
    let normalized = provider.trim().to_lowercase();
    match normalized.as_str() {
        "" => "openai".to_string(),
        "claude" => "anthropic".to_string(),
        "openai_compatible" => "custom".to_string(),
        _ => normalized,
    }
}

fn read_string(value: &Value, key: &str) -> Option<String> {
    value.get(key)?.as_str().map(str::to_string)
}

fn recommend_tokens(model: &str) -> i64 {
    let normalized = model.to_lowercase();
    if [
        "gpt-5", "o3", "o4", "claude", "deepseek", "kimi", "glm", "gemini",
    ]
    .iter()
    .any(|hint| normalized.contains(hint))
    {
        return DEFAULT_LLM_MAX_TOKENS;
    }
    8_192
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
            .bind(payload.llm_config.to_string())
            .bind(payload.other_config.to_string())
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
