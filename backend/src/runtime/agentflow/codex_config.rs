use serde_json::{Map, Value};

use crate::{config::AppConfig, routes::llm_config_set};

pub fn build_agentflow_llm_config(config: &AppConfig, saved: Option<&Value>) -> Value {
    let normalized_saved = saved.map(|value| llm_config_set::normalize_envelope(value, config).0);
    let selected = normalized_saved
        .as_ref()
        .and_then(|envelope| envelope.get("rows"))
        .and_then(Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .filter(|row| row.get("enabled").and_then(Value::as_bool).unwrap_or(true))
                .min_by_key(|row| {
                    row.get("priority")
                        .and_then(Value::as_i64)
                        .unwrap_or(i64::MAX)
                })
        })
        .map(llm_config_set::row_to_legacy_config);
    let saved = selected.as_ref().or(saved);
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
