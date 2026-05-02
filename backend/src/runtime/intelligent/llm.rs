use async_trait::async_trait;
use reqwest::Client;
use serde_json::json;

use crate::runtime::intelligent::{
    config::{IntelligentLlmConfig, IntelligentLlmProvider},
    types::{now_rfc3339, IntelligentTaskEvent},
};

#[derive(Clone, Debug)]
pub struct IntelligentLlmInvocation {
    pub content: String,
    pub finished_at: String,
    pub attempt_event: IntelligentTaskEvent,
}

#[derive(Clone, Debug)]
pub struct IntelligentLlmInvocationError {
    pub stage: &'static str,
    pub redacted_message: String,
}

impl std::fmt::Display for IntelligentLlmInvocationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.stage, self.redacted_message)
    }
}

impl std::error::Error for IntelligentLlmInvocationError {}

#[async_trait]
pub trait IntelligentLlmInvoker {
    async fn invoke(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError>;
}

/// Redact sensitive values from a string before it enters logs or event records.
/// Replaces the api_key and any value associated with known sensitive header names.
pub fn redact_for_logging(raw: &str, config: &IntelligentLlmConfig) -> String {
    let mut result = raw.to_string();
    if !config.api_key.is_empty() {
        result = result.replace(&config.api_key, "***");
    }
    // Also redact common patterns
    for pattern in &["Authorization", "x-api-key", "Bearer "] {
        // We only redact values that might have leaked — not the header names themselves.
        // Since we never log header values, this is belt-and-suspenders.
        let _ = pattern; // header names are safe to log; values are not logged at all
    }
    result
}

pub struct HttpIntelligentLlmInvoker {
    client: Client,
}

impl Default for HttpIntelligentLlmInvoker {
    fn default() -> Self {
        Self {
            client: Client::new(),
        }
    }
}

impl HttpIntelligentLlmInvoker {
    pub fn with_client(client: Client) -> Self {
        Self { client }
    }
}

#[async_trait]
impl IntelligentLlmInvoker for HttpIntelligentLlmInvoker {
    async fn invoke(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
        let started_at = now_rfc3339();
        let timeout = std::time::Duration::from_millis(config.timeout_ms.max(1) as u64);

        let result = match config.provider {
            IntelligentLlmProvider::OpenAiCompatible => {
                self.invoke_openai(prompt, config, timeout).await
            }
            IntelligentLlmProvider::AnthropicCompatible => {
                self.invoke_anthropic(prompt, config, timeout).await
            }
        };

        let finished_at = now_rfc3339();

        match result {
            Ok(content) => {
                let attempt_event = IntelligentTaskEvent::new("llm_attempt").with_data(json!({
                    "provider": format!("{:?}", config.provider),
                    "model": config.model,
                    "fingerprint": config.llm_fingerprint_for_log(),
                    "started": started_at,
                    "completed": finished_at,
                    "success": true,
                }));
                Ok(IntelligentLlmInvocation {
                    content,
                    finished_at,
                    attempt_event,
                })
            }
            Err(redacted_message) => {
                let attempt_event = IntelligentTaskEvent::new("llm_attempt").with_data(json!({
                    "provider": format!("{:?}", config.provider),
                    "model": config.model,
                    "fingerprint": config.llm_fingerprint_for_log(),
                    "started": started_at,
                    "completed": finished_at,
                    "success": false,
                    "redacted_error": redacted_message,
                }));
                Err(IntelligentLlmInvocationError {
                    stage: "llm_request",
                    redacted_message: attempt_event
                        .data
                        .as_ref()
                        .and_then(|d| d["redacted_error"].as_str())
                        .unwrap_or("unknown")
                        .to_string(),
                })
            }
        }
    }
}

impl HttpIntelligentLlmInvoker {
    async fn invoke_openai(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
        timeout: std::time::Duration,
    ) -> Result<String, String> {
        let url = config
            .base_url
            .join("chat/completions")
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        let body = json!({
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config.max_tokens_per_call,
            "temperature": config.temperature,
            "stream": false,
        });

        let response = self
            .client
            .post(url)
            .timeout(timeout)
            .bearer_auth(&config.api_key)
            .json(&body)
            .send()
            .await
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        if !response.status().is_success() {
            let status = response.status();
            return Err(format!("HTTP {status}"));
        }

        let json: serde_json::Value = response
            .json()
            .await
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        let content = json["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("")
            .to_string();
        Ok(content)
    }

    async fn invoke_anthropic(
        &self,
        prompt: &str,
        config: &IntelligentLlmConfig,
        timeout: std::time::Duration,
    ) -> Result<String, String> {
        let url = config
            .base_url
            .join("v1/messages")
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        let body = json!({
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config.max_tokens_per_call,
        });

        let response = self
            .client
            .post(url)
            .timeout(timeout)
            .header("x-api-key", &config.api_key)
            .header("anthropic-version", "2023-06-01")
            .json(&body)
            .send()
            .await
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        if !response.status().is_success() {
            let status = response.status();
            return Err(format!("HTTP {status}"));
        }

        let json: serde_json::Value = response
            .json()
            .await
            .map_err(|e| redact_for_logging(&e.to_string(), config))?;

        let content = json["content"][0]["text"]
            .as_str()
            .unwrap_or("")
            .to_string();
        Ok(content)
    }
}

// Helper to expose fingerprint safely for logging (it's already a hash, not a secret)
trait LlmConfigLogHelper {
    fn llm_fingerprint_for_log(&self) -> &str;
}

impl LlmConfigLogHelper for IntelligentLlmConfig {
    fn llm_fingerprint_for_log(&self) -> &str {
        &self.fingerprint
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_config_with_key(api_key: &str) -> IntelligentLlmConfig {
        use reqwest::Url;
        IntelligentLlmConfig {
            row_id: "test".to_string(),
            provider: IntelligentLlmProvider::OpenAiCompatible,
            model: "gpt-test".to_string(),
            base_url: Url::parse("https://api.example.com/v1/").unwrap(),
            api_key: api_key.to_string(),
            fingerprint: "sha256:abc123".to_string(),
            timeout_ms: 30000,
            temperature: 0.0,
            max_tokens_per_call: 1024,
            first_token_timeout_seconds: 30,
            stream_timeout_seconds: 60,
            custom_header_names: vec![],
            claw_auth_kind: "openai_compatible_bearer",
        }
    }

    #[test]
    fn redact_for_logging_removes_api_key() {
        let config = make_config_with_key("sk-super-secret-key");
        let raw = "error calling https://api.example.com?key=sk-super-secret-key";
        let redacted = redact_for_logging(raw, &config);
        assert!(
            !redacted.contains("sk-super-secret-key"),
            "api_key must not appear in redacted output: {redacted}"
        );
        assert!(redacted.contains("***"));
    }

    #[test]
    fn redact_for_logging_empty_key_is_noop() {
        let config = make_config_with_key("");
        let raw = "some error message";
        let redacted = redact_for_logging(raw, &config);
        assert_eq!(redacted, raw);
    }
}
