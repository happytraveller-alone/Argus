use serde_json::{Map, Value};

use crate::config::AppConfig;

pub fn build_agentflow_llm_config(_config: &AppConfig, saved: Option<&Value>) -> Value {
    let saved_has_api_key = config_value(saved, "llmApiKey").is_some();
    let mut object = Map::new();
    object.insert(
        "llmProvider".to_string(),
        Value::String(config_value(saved, "llmProvider").unwrap_or_default()),
    );
    object.insert(
        "llmModel".to_string(),
        Value::String(config_value(saved, "llmModel").unwrap_or_default()),
    );
    object.insert(
        "llmBaseUrl".to_string(),
        Value::String(config_value(saved, "llmBaseUrl").unwrap_or_default()),
    );
    object.insert(
        "llmApiKey".to_string(),
        Value::String(config_value(saved, "llmApiKey").unwrap_or_default()),
    );
    object.insert(
        "credentialSource".to_string(),
        Value::String(if saved_has_api_key {
            "system_config".to_string()
        } else {
            "missing_system_config".to_string()
        }),
    );
    Value::Object(object)
}

fn config_value(value: Option<&Value>, key: &str) -> Option<String> {
    value?
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}
