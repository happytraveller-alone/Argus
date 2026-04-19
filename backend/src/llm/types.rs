use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct LlmConfig {
    pub provider: String,
    pub api_key: String,
    pub model: String,
    pub base_url: Option<String>,
    pub timeout_seconds: u64,
    pub temperature: f64,
    pub max_tokens: i64,
    pub top_p: f64,
    pub frequency_penalty: f64,
    pub presence_penalty: f64,
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            provider: "openai".to_string(),
            api_key: String::new(),
            model: "gpt-5".to_string(),
            base_url: Some("https://api.openai.com/v1".to_string()),
            timeout_seconds: 150,
            temperature: 0.2,
            max_tokens: 4_096,
            top_p: 1.0,
            frequency_penalty: 0.0,
            presence_penalty: 0.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LlmMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct LlmRequest {
    pub messages: Vec<LlmMessage>,
    pub temperature: Option<f64>,
    pub max_tokens: Option<i64>,
    pub top_p: Option<f64>,
    pub stream: bool,
    pub tools: Option<Vec<Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct LlmUsage {
    pub prompt_tokens: i64,
    pub completion_tokens: i64,
    pub total_tokens: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct LlmResponse {
    pub content: String,
    pub model: Option<String>,
    pub usage: Option<LlmUsage>,
    pub finish_reason: Option<String>,
    pub tool_calls: Option<Vec<Value>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct LlmErrorContext {
    pub message: String,
    pub provider: Option<String>,
    pub status_code: Option<i64>,
    pub api_response: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::{LlmConfig, LlmMessage, LlmRequest, LlmUsage};

    #[test]
    fn default_llm_config_matches_retired_python_defaults() {
        let config = LlmConfig::default();
        assert_eq!(config.provider, "openai");
        assert_eq!(config.model, "gpt-5");
        assert_eq!(config.base_url.as_deref(), Some("https://api.openai.com/v1"));
        assert_eq!(config.timeout_seconds, 150);
        assert_eq!(config.max_tokens, 4_096);
    }

    #[test]
    fn llm_request_and_usage_shape_stays_stable() {
        let request = LlmRequest {
            messages: vec![LlmMessage {
                role: "user".to_string(),
                content: "hello".to_string(),
            }],
            temperature: Some(0.1),
            max_tokens: Some(128),
            top_p: None,
            stream: true,
            tools: None,
        };
        let usage = LlmUsage {
            prompt_tokens: 10,
            completion_tokens: 3,
            total_tokens: 13,
        };

        assert_eq!(request.messages.len(), 1);
        assert!(request.stream);
        assert_eq!(usage.total_tokens, 13);
    }
}
