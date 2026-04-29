use std::{collections::BTreeMap, fmt};

use reqwest::{
    header::{HeaderMap, HeaderName, HeaderValue},
    Client,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

use super::{is_supported_protocol_provider, normalize_base_url, parse_custom_headers};

pub const LLM_CONFIG_VERSION: &str = "intelligent-engine-v1";
pub const LLM_TEST_SCHEMA_VERSION: &str = "llm-real-test-v1";

const ANTHROPIC_VERSION: &str = "2023-06-01";
const PROTECTED_HEADERS: &[&str] = &["authorization", "x-api-key", "api-key", "anthropic-version"];

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LlmRealTestOutcome {
    pub tested_at: String,
    pub fingerprint: String,
    pub provider: String,
    pub model: String,
    pub protocol: String,
    pub schema_version: String,
}

impl LlmRealTestOutcome {
    pub fn metadata(&self) -> Value {
        serde_json::to_value(self).unwrap_or_else(|_| json!({}))
    }
}

#[derive(Clone, Debug)]
pub struct RuntimeLlmConfig {
    pub provider: String,
    pub model: String,
    pub base_url: String,
    pub api_key: String,
    pub custom_headers: BTreeMap<String, String>,
    pub llm_timeout: i64,
    pub llm_temperature: f64,
    pub llm_max_tokens: i64,
    pub llm_first_token_timeout: i64,
    pub llm_stream_timeout: i64,
    pub agent_timeout: i64,
    pub sub_agent_timeout: i64,
    pub tool_timeout: i64,
    pub llm_concurrency: i64,
    pub llm_gap_ms: i64,
}

#[derive(Clone, Debug)]
pub struct LlmGateError {
    pub reason_code: &'static str,
    pub message: String,
}

impl LlmGateError {
    pub fn new(reason_code: &'static str, message: impl Into<String>) -> Self {
        Self {
            reason_code,
            message: message.into(),
        }
    }
}

impl fmt::Display for LlmGateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for LlmGateError {}

pub fn empty_protocol_llm_config() -> Value {
    json!({
        "llmConfigVersion": LLM_CONFIG_VERSION,
        "llmProvider": "openai_compatible",
        "llmApiKey": "",
        "llmModel": "",
        "llmBaseUrl": "",
        "llmTimeout": 120000,
        "llmTemperature": 0.1,
        "llmMaxTokens": 16384,
        "llmCustomHeaders": "",
        "llmFirstTokenTimeout": 180,
        "llmStreamTimeout": 600,
        "agentTimeout": 600,
        "subAgentTimeout": 300,
        "toolTimeout": 120
    })
}

pub fn sanitize_llm_config_for_save(llm_config: &Value) -> Result<Value, LlmGateError> {
    let provider = read_string(llm_config, "llmProvider");
    if !is_supported_protocol_provider(&provider) {
        return Err(LlmGateError::new(
            "unsupported_provider",
            "LLM 配置仅支持 OpenAI-compatible 或 Anthropic-compatible 协议。",
        ));
    }
    validate_required_text(llm_config, "llmBaseUrl", "baseUrl")?;
    validate_required_text(llm_config, "llmApiKey", "apiKey")?;
    normalized_custom_headers(llm_config.get("llmCustomHeaders"))?;

    let mut sanitized = match llm_config {
        Value::Object(map) => Value::Object(map.clone()),
        _ => {
            return Err(LlmGateError::new(
                "invalid_config",
                "LLM 配置必须是 JSON 对象。",
            ))
        }
    };
    if let Some(map) = sanitized.as_object_mut() {
        map.insert(
            "llmProvider".to_string(),
            Value::String(provider.to_string()),
        );
        map.insert(
            "llmBaseUrl".to_string(),
            Value::String(normalize_base_url(&read_string(llm_config, "llmBaseUrl"))),
        );
        map.insert(
            "llmConfigVersion".to_string(),
            Value::String(LLM_CONFIG_VERSION.to_string()),
        );
    }
    Ok(sanitized)
}

pub fn normalize_stored_llm_config(llm_config: &Value, metadata: &Value) -> (Value, Value, bool) {
    let provider = read_string(llm_config, "llmProvider");
    let version = read_string(llm_config, "llmConfigVersion");
    if version != LLM_CONFIG_VERSION || !is_supported_protocol_provider(&provider) {
        return (empty_protocol_llm_config(), json!({}), true);
    }
    (llm_config.clone(), metadata.clone(), false)
}

pub fn build_runtime_config(
    llm_config: &Value,
    other_config: &Value,
) -> Result<RuntimeLlmConfig, LlmGateError> {
    let provider = read_string(llm_config, "llmProvider");
    if !is_supported_protocol_provider(&provider) {
        return Err(LlmGateError::new(
            "unsupported_provider",
            "请在扫描配置 > 智能引擎中选择 OpenAI-compatible 或 Anthropic-compatible 协议并重新测试。",
        ));
    }
    let model = validate_required_text(llm_config, "llmModel", "model")?;
    let base_url = normalize_base_url(&validate_required_text(
        llm_config,
        "llmBaseUrl",
        "baseUrl",
    )?);
    let api_key = validate_required_text(llm_config, "llmApiKey", "apiKey")?;

    Ok(RuntimeLlmConfig {
        provider: provider.to_string(),
        model,
        base_url,
        api_key,
        custom_headers: normalized_custom_headers(llm_config.get("llmCustomHeaders"))?,
        llm_timeout: read_i64(llm_config, "llmTimeout", 120_000),
        llm_temperature: read_f64(llm_config, "llmTemperature", 0.1),
        llm_max_tokens: read_i64(llm_config, "llmMaxTokens", 16_384),
        llm_first_token_timeout: read_i64(llm_config, "llmFirstTokenTimeout", 180),
        llm_stream_timeout: read_i64(llm_config, "llmStreamTimeout", 600),
        agent_timeout: read_i64(llm_config, "agentTimeout", 600),
        sub_agent_timeout: read_i64(llm_config, "subAgentTimeout", 300),
        tool_timeout: read_i64(llm_config, "toolTimeout", 120),
        llm_concurrency: read_i64(other_config, "llmConcurrency", 1),
        llm_gap_ms: read_i64(other_config, "llmGapMs", 0),
    })
}

pub fn compute_llm_fingerprint(runtime: &RuntimeLlmConfig) -> String {
    let custom_headers = runtime
        .custom_headers
        .iter()
        .map(|(name, value)| (name.clone(), sha256_hex(value.as_bytes())))
        .collect::<BTreeMap<_, _>>();
    let canonical = json!({
        "schemaVersion": LLM_TEST_SCHEMA_VERSION,
        "llmProvider": runtime.provider,
        "llmModel": runtime.model,
        "llmBaseUrl": runtime.base_url,
        "llmApiKeySha256": sha256_hex(runtime.api_key.as_bytes()),
        "customHeaders": custom_headers,
        "llmTimeout": runtime.llm_timeout,
        "llmTemperature": runtime.llm_temperature,
        "llmMaxTokens": runtime.llm_max_tokens,
        "llmFirstTokenTimeout": runtime.llm_first_token_timeout,
        "llmStreamTimeout": runtime.llm_stream_timeout,
        "agentTimeout": runtime.agent_timeout,
        "subAgentTimeout": runtime.sub_agent_timeout,
        "toolTimeout": runtime.tool_timeout,
        "otherConfig": {
            "llmConcurrency": runtime.llm_concurrency,
            "llmGapMs": runtime.llm_gap_ms,
        }
    });
    let bytes = serde_json::to_vec(&canonical).unwrap_or_default();
    format!("sha256:{}", sha256_hex(&bytes))
}

pub fn metadata_matches(metadata: &Value, fingerprint: &str) -> bool {
    metadata
        .get("schemaVersion")
        .and_then(Value::as_str)
        .is_some_and(|value| value == LLM_TEST_SCHEMA_VERSION)
        && metadata
            .get("fingerprint")
            .and_then(Value::as_str)
            .is_some_and(|value| value == fingerprint)
}

pub async fn test_llm_generation(
    client: &Client,
    runtime: &RuntimeLlmConfig,
) -> Result<LlmRealTestOutcome, LlmGateError> {
    let text = match runtime.provider.as_str() {
        "openai_compatible" => test_openai_compatible(client, runtime).await?,
        "anthropic_compatible" => test_anthropic_compatible(client, runtime).await?,
        _ => {
            return Err(LlmGateError::new(
                "unsupported_provider",
                "不支持的 LLM 协议。",
            ))
        }
    };
    if text.trim().is_empty() {
        return Err(LlmGateError::new(
            "empty_response",
            "LLM 测试失败：模型返回了空文本。",
        ));
    }
    Ok(LlmRealTestOutcome {
        tested_at: OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string()),
        fingerprint: compute_llm_fingerprint(runtime),
        provider: runtime.provider.clone(),
        model: runtime.model.clone(),
        protocol: runtime.provider.clone(),
        schema_version: LLM_TEST_SCHEMA_VERSION.to_string(),
    })
}

async fn test_openai_compatible(
    client: &Client,
    runtime: &RuntimeLlmConfig,
) -> Result<String, LlmGateError> {
    let url = format!(
        "{}/chat/completions",
        runtime.base_url.trim_end_matches('/')
    );
    let response = client
        .post(url)
        .headers(runtime_headers(runtime)?)
        .json(&json!({
            "model": runtime.model,
            "messages": [{"role": "user", "content": "Return the word ok."}],
            "max_tokens": runtime.llm_max_tokens.clamp(1, 16),
            "temperature": runtime.llm_temperature,
            "stream": false
        }))
        .send()
        .await
        .map_err(|error| {
            LlmGateError::new("request_failed", format!("LLM 测试请求失败：{error}"))
        })?;
    parse_json_response(response, |json| {
        json.pointer("/choices/0/message/content")
            .and_then(Value::as_str)
            .or_else(|| json.pointer("/choices/0/text").and_then(Value::as_str))
            .map(ToString::to_string)
    })
    .await
}

async fn test_anthropic_compatible(
    client: &Client,
    runtime: &RuntimeLlmConfig,
) -> Result<String, LlmGateError> {
    let url = format!("{}/messages", runtime.base_url.trim_end_matches('/'));
    let response = client
        .post(url)
        .headers(runtime_headers(runtime)?)
        .json(&json!({
            "model": runtime.model,
            "messages": [{"role": "user", "content": "Return the word ok."}],
            "max_tokens": runtime.llm_max_tokens.clamp(1, 16)
        }))
        .send()
        .await
        .map_err(|error| {
            LlmGateError::new("request_failed", format!("LLM 测试请求失败：{error}"))
        })?;
    parse_json_response(response, |json| {
        json.get("content")
            .and_then(Value::as_array)
            .and_then(|items| {
                items
                    .iter()
                    .find_map(|item| item.get("text").and_then(Value::as_str))
            })
            .map(ToString::to_string)
    })
    .await
}

async fn parse_json_response(
    response: reqwest::Response,
    text: impl FnOnce(&Value) -> Option<String>,
) -> Result<String, LlmGateError> {
    let status = response.status();
    if !status.is_success() {
        return Err(LlmGateError::new(
            "upstream_status",
            format!("LLM 测试失败：服务返回 HTTP {status}。"),
        ));
    }
    let json = response.json::<Value>().await.map_err(|error| {
        LlmGateError::new(
            "invalid_response",
            format!("LLM 测试响应不是有效 JSON：{error}"),
        )
    })?;
    text(&json)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            LlmGateError::new(
                "empty_response",
                "LLM 测试失败：响应中没有可解析的非空文本。",
            )
        })
}

fn runtime_headers(runtime: &RuntimeLlmConfig) -> Result<HeaderMap, LlmGateError> {
    let mut headers = HeaderMap::new();
    for (name, value) in &runtime.custom_headers {
        let header_name = HeaderName::from_bytes(name.as_bytes()).map_err(|_| {
            LlmGateError::new(
                "invalid_header",
                format!("LLM 自定义请求头 `{name}` 不是合法名称。"),
            )
        })?;
        let header_value = HeaderValue::from_str(value).map_err(|_| {
            LlmGateError::new(
                "invalid_header",
                format!("LLM 自定义请求头 `{name}` 不是合法值。"),
            )
        })?;
        headers.insert(header_name, header_value);
    }
    match runtime.provider.as_str() {
        "openai_compatible" => {
            headers.insert(
                reqwest::header::AUTHORIZATION,
                HeaderValue::from_str(&format!("Bearer {}", runtime.api_key)).map_err(|_| {
                    LlmGateError::new("invalid_api_key", "LLM API Key 不是合法请求头值。")
                })?,
            );
        }
        "anthropic_compatible" => {
            headers.insert(
                HeaderName::from_static("x-api-key"),
                HeaderValue::from_str(&runtime.api_key).map_err(|_| {
                    LlmGateError::new("invalid_api_key", "LLM API Key 不是合法请求头值。")
                })?,
            );
            headers.insert(
                HeaderName::from_static("anthropic-version"),
                HeaderValue::from_static(ANTHROPIC_VERSION),
            );
        }
        _ => {}
    }
    Ok(headers)
}

fn normalized_custom_headers(
    value: Option<&Value>,
) -> Result<BTreeMap<String, String>, LlmGateError> {
    let parsed = parse_custom_headers(value)
        .map_err(|message| LlmGateError::new("invalid_headers", message))?;
    let mut headers = BTreeMap::new();
    for (name, value) in parsed {
        let normalized = name.trim().to_ascii_lowercase();
        if normalized.is_empty() {
            continue;
        }
        if PROTECTED_HEADERS.contains(&normalized.as_str()) {
            return Err(LlmGateError::new(
                "protected_header",
                format!("自定义请求头 `{name}` 与协议保留请求头冲突。"),
            ));
        }
        if headers.insert(normalized.clone(), value).is_some() {
            return Err(LlmGateError::new(
                "duplicate_header",
                format!("自定义请求头 `{name}` 与另一个请求头名称重复。"),
            ));
        }
    }
    Ok(headers)
}

fn validate_required_text(
    value: &Value,
    key: &'static str,
    label: &'static str,
) -> Result<String, LlmGateError> {
    let text = read_string(value, key);
    if text.is_empty() {
        return Err(LlmGateError::new(
            "missing_fields",
            format!("LLM 配置缺失：`{label}` 必填。"),
        ));
    }
    Ok(text)
}

fn read_string(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_string()
}

fn read_i64(value: &Value, key: &str, default: i64) -> i64 {
    value.get(key).and_then(Value::as_i64).unwrap_or(default)
}

fn read_f64(value: &Value, key: &str, default: f64) -> f64 {
    value.get(key).and_then(Value::as_f64).unwrap_or(default)
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct _SerdeShapeGuard {
    _tested_at: Option<String>,
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        build_runtime_config, compute_llm_fingerprint, metadata_matches,
        sanitize_llm_config_for_save, LLM_TEST_SCHEMA_VERSION,
    };

    #[test]
    fn protected_header_collisions_are_rejected_case_insensitively() {
        let config = json!({
            "llmProvider": "openai_compatible",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.example/v1",
            "llmApiKey": "sk-secret",
            "llmCustomHeaders": {" Authorization ": "bad"}
        });
        let error = sanitize_llm_config_for_save(&config).expect_err("protected header fails");
        assert_eq!(error.reason_code, "protected_header");
    }

    #[test]
    fn fingerprint_changes_without_exposing_plaintext_secrets() {
        let base = json!({
            "llmProvider": "openai_compatible",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.example/v1/chat/completions",
            "llmApiKey": "sk-secret",
            "llmCustomHeaders": {"X-Trace": "header-secret"}
        });
        let runtime = build_runtime_config(&base, &json!({"llmConcurrency": 1, "llmGapMs": 0}))
            .expect("runtime config");
        let fingerprint = compute_llm_fingerprint(&runtime);
        assert!(fingerprint.starts_with("sha256:"));
        assert!(!fingerprint.contains("sk-secret"));
        assert!(!fingerprint.contains("header-secret"));

        let metadata = json!({
            "schemaVersion": LLM_TEST_SCHEMA_VERSION,
            "fingerprint": fingerprint,
        });
        assert!(metadata_matches(
            &metadata,
            metadata["fingerprint"].as_str().unwrap()
        ));
    }
}
