use reqwest::Url;
use serde::{Serialize, Serializer};

use crate::{
    config::AppConfig,
    llm::{normalize_base_url, RuntimeLlmConfig},
    routes::llm_config_set,
    state::StoredSystemConfig,
};

const CLAW_DEFAULT_MODEL: &str = "claude-3-5-sonnet";

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub enum IntelligentLlmProvider {
    #[serde(rename = "anthropic_compatible")]
    AnthropicCompatible,
    #[serde(rename = "openai_compatible")]
    OpenAiCompatible,
}

impl IntelligentLlmProvider {
    #[must_use]
    pub fn claw_auth_kind(&self) -> &'static str {
        match self {
            Self::AnthropicCompatible => "anthropic_api_key",
            Self::OpenAiCompatible => "openai_compatible_bearer",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentLlmConfig {
    pub row_id: String,
    pub provider: IntelligentLlmProvider,
    pub model: String,
    #[serde(serialize_with = "serialize_url")]
    pub base_url: Url,
    #[serde(skip_serializing)]
    pub api_key: String,
    pub fingerprint: String,
    pub timeout_ms: i64,
    pub temperature: f64,
    pub max_tokens_per_call: i64,
    pub first_token_timeout_seconds: i64,
    pub stream_timeout_seconds: i64,
    pub custom_header_names: Vec<String>,
    pub claw_auth_kind: &'static str,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IntelligentLlmConfigError {
    pub reason_code: &'static str,
    pub message: String,
}

impl IntelligentLlmConfigError {
    fn new(reason_code: &'static str, message: impl Into<String>) -> Self {
        Self {
            reason_code,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for IntelligentLlmConfigError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for IntelligentLlmConfigError {}

pub fn resolve_intelligent_llm_config(
    stored: &StoredSystemConfig,
    app_config: &AppConfig,
) -> Result<IntelligentLlmConfig, IntelligentLlmConfigError> {
    let selected = llm_config_set::selected_enabled_runtime(
        &stored.llm_config_json,
        &stored.other_config_json,
        app_config,
    )
    .map_err(|error| IntelligentLlmConfigError::new(error.reason_code, error.message))?;
    let provider = provider_from_runtime(&selected.runtime.provider)?;
    config_from_runtime(
        selected.row_id,
        selected.runtime,
        selected.fingerprint,
        provider,
    )
}

#[must_use]
pub fn is_llm_configured(stored: &StoredSystemConfig, app_config: &AppConfig) -> bool {
    resolve_intelligent_llm_config(stored, app_config).is_ok()
}

pub fn llm_api_key(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<String> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.api_key)
}

pub fn llm_base_url(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<Url> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.base_url)
}

pub fn llm_model_default(stored: &StoredSystemConfig, app_config: &AppConfig) -> Option<String> {
    resolve_intelligent_llm_config(stored, app_config)
        .ok()
        .map(|config| config.model)
}

pub fn config_from_runtime(
    row_id: String,
    runtime: RuntimeLlmConfig,
    fingerprint: String,
    provider: IntelligentLlmProvider,
) -> Result<IntelligentLlmConfig, IntelligentLlmConfigError> {
    let base_url = parse_absolute_base_url(&runtime.base_url, &provider)?;
    let model = if runtime.model.trim().is_empty() {
        CLAW_DEFAULT_MODEL.to_string()
    } else {
        runtime.model
    };
    let mut custom_header_names: Vec<String> = runtime.custom_headers.keys().cloned().collect();
    custom_header_names.sort();
    let claw_auth_kind = provider.claw_auth_kind();
    Ok(IntelligentLlmConfig {
        row_id,
        provider,
        model,
        base_url,
        api_key: runtime.api_key,
        fingerprint,
        timeout_ms: runtime.llm_timeout,
        temperature: runtime.llm_temperature,
        max_tokens_per_call: runtime.llm_max_tokens,
        first_token_timeout_seconds: runtime.llm_first_token_timeout,
        stream_timeout_seconds: runtime.llm_stream_timeout,
        custom_header_names,
        claw_auth_kind,
    })
}

fn provider_from_runtime(
    provider: &str,
) -> Result<IntelligentLlmProvider, IntelligentLlmConfigError> {
    match provider.trim().to_ascii_lowercase().as_str() {
        "anthropic_compatible" => Ok(IntelligentLlmProvider::AnthropicCompatible),
        "openai_compatible" => Ok(IntelligentLlmProvider::OpenAiCompatible),
        _ => Err(IntelligentLlmConfigError::new(
            "unsupported_provider",
            "智能审计 LLM 配置仅支持 OpenAI-compatible 或 Anthropic-compatible 协议。",
        )),
    }
}

fn parse_absolute_base_url(
    value: &str,
    provider: &IntelligentLlmProvider,
) -> Result<Url, IntelligentLlmConfigError> {
    let mut normalized = normalize_base_url(value);
    normalized = match provider {
        IntelligentLlmProvider::AnthropicCompatible => {
            let trimmed = normalized.trim_end_matches('/');
            trimmed
                .strip_suffix("/v1/messages")
                .unwrap_or(trimmed)
                .to_string()
        }
        IntelligentLlmProvider::OpenAiCompatible => normalized,
    };
    let parsed = Url::parse(&normalized).map_err(|_| {
        IntelligentLlmConfigError::new(
            "invalid_base_url",
            "智能审计 LLM 配置的 baseUrl 必须是包含 http/https scheme 的绝对 URL。",
        )
    })?;
    match parsed.scheme() {
        "http" | "https" if parsed.has_host() => Ok(parsed),
        _ => Err(IntelligentLlmConfigError::new(
            "invalid_base_url",
            "智能审计 LLM 配置的 baseUrl 必须是包含 http/https scheme 的绝对 URL。",
        )),
    }
}

fn serialize_url<S>(url: &Url, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    serializer.serialize_str(url.as_str())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::{
        config::AppConfig, llm::compute_llm_fingerprint, routes::llm_config_set,
        state::StoredSystemConfig,
    };

    #[test]
    fn resolves_enabled_schema_v2_row_into_claw_compatible_snapshot() {
        let app_config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [
                    {
                        "id": "disabled",
                        "priority": 1,
                        "enabled": false,
                        "provider": "openai_compatible",
                        "baseUrl": "https://disabled.example/v1",
                        "model": "gpt-disabled",
                        "apiKey": "sk-disabled",
                        "advanced": {}
                    },
                    {
                        "id": "anthropic-row",
                        "priority": 2,
                        "enabled": true,
                        "provider": "anthropic_compatible",
                        "baseUrl": "https://api.anthropic.example/v1/messages",
                        "model": "claude-sonnet-4.5",
                        "apiKey": "sk-ant-secret",
                        "advanced": {
                            "llmTimeout": 123000,
                            "llmTemperature": 0.2,
                            "llmMaxTokens": 4096,
                            "llmFirstTokenTimeout": 31,
                            "llmStreamTimeout": 122,
                            "llmCustomHeaders": {"X-Trace": "secret-header"}
                        }
                    }
                ]
            }),
            other_config_json: json!({"llmConcurrency": 2, "llmGapMs": 5}),
            llm_test_metadata_json: json!({}),
        };

        let config = resolve_intelligent_llm_config(&stored, &app_config).unwrap();

        assert_eq!(config.row_id, "anthropic-row");
        assert_eq!(config.provider, IntelligentLlmProvider::AnthropicCompatible);
        assert_eq!(config.claw_auth_kind, "anthropic_api_key");
        assert_eq!(config.model, "claude-sonnet-4.5");
        assert_eq!(config.base_url.as_str(), "https://api.anthropic.example/");
        assert_eq!(config.api_key, "sk-ant-secret");
        assert_eq!(config.timeout_ms, 123000);
        assert_eq!(config.temperature, 0.2);
        assert_eq!(config.max_tokens_per_call, 4096);
        assert_eq!(config.first_token_timeout_seconds, 31);
        assert_eq!(config.stream_timeout_seconds, 122);
        assert_eq!(config.custom_header_names, vec!["x-trace"]);
        assert!(config.fingerprint.starts_with("sha256:"));
    }

    #[test]
    fn rejects_missing_malformed_or_relative_configs_without_panicking() {
        let app_config = AppConfig::for_tests();
        let empty = StoredSystemConfig {
            llm_config_json: json!({}),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        assert!(!is_llm_configured(&empty, &app_config));
        assert!(llm_api_key(&empty, &app_config).is_none());
        assert!(llm_base_url(&empty, &app_config).is_none());
        assert!(llm_model_default(&empty, &app_config).is_none());

        let relative_url = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [{
                    "id": "bad-url",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "/local/v1",
                    "model": "gpt-5",
                    "apiKey": "sk-test",
                    "advanced": {}
                }]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };
        let error = resolve_intelligent_llm_config(&relative_url, &app_config).unwrap_err();
        assert_eq!(error.reason_code, "invalid_base_url");
    }

    #[test]
    fn exposes_openai_compatible_runtime_for_future_claw_client_builder() {
        let app_config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [{
                    "id": "openai-row",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "https://gateway.example/v1/chat/completions",
                    "model": "gpt-5",
                    "apiKey": "sk-openai-secret",
                    "advanced": {}
                }]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };

        let config = resolve_intelligent_llm_config(&stored, &app_config).unwrap();

        assert_eq!(config.provider, IntelligentLlmProvider::OpenAiCompatible);
        assert_eq!(config.claw_auth_kind, "openai_compatible_bearer");
        assert_eq!(config.base_url.as_str(), "https://gateway.example/v1");
        assert_eq!(
            llm_api_key(&stored, &app_config).as_deref(),
            Some("sk-openai-secret")
        );
        assert_eq!(
            llm_base_url(&stored, &app_config).map(|url| url.to_string()),
            Some("https://gateway.example/v1".to_string())
        );
        assert_eq!(
            llm_model_default(&stored, &app_config).as_deref(),
            Some("gpt-5")
        );
    }

    #[test]
    fn serialized_config_never_exposes_secret_material() {
        let app_config = AppConfig::for_tests();
        let row = json!({
            "id": "row-secret",
            "priority": 1,
            "enabled": true,
            "provider": "openai_compatible",
            "baseUrl": "https://gateway.example/v1",
            "model": "gpt-5",
            "apiKey": "sk-secret",
            "advanced": {"llmCustomHeaders": {"X-Secret": "header-secret"}}
        });
        let runtime = llm_config_set::selected_enabled_runtime(
            &json!({"schemaVersion": 2, "rows": [row]}),
            &json!({}),
            &app_config,
        )
        .unwrap();
        let fingerprint = compute_llm_fingerprint(&runtime.runtime);
        let config = config_from_runtime(
            runtime.row_id,
            runtime.runtime,
            fingerprint,
            IntelligentLlmProvider::OpenAiCompatible,
        )
        .unwrap();

        let serialized = serde_json::to_string(&config).unwrap();

        assert!(!serialized.contains("sk-secret"));
        assert!(!serialized.contains("header-secret"));
        assert!(serialized.contains("customHeaderNames"));
        assert!(serialized.contains("x-secret"));
    }
}
