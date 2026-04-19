use std::collections::BTreeMap;

use reqwest::Url;
use serde_json::Value;

const ROOT_ENDPOINT_SUFFIXES: &[&str] = &[
    "/chat/completions",
    "/completions",
    "/responses",
    "/embeddings",
    "/models",
];

pub fn normalize_base_url(value: &str) -> String {
    let raw = value.trim();
    if raw.is_empty() {
        return String::new();
    }

    let Ok(parsed) = Url::parse(raw) else {
        return raw.trim_end_matches('/').to_string();
    };
    if !parsed.has_host() {
        return raw.trim_end_matches('/').to_string();
    }

    let mut normalized_path = parsed.path().trim_end_matches('/').to_string();
    let normalized_path_lower = normalized_path.to_ascii_lowercase();
    for suffix in ROOT_ENDPOINT_SUFFIXES {
        if normalized_path_lower.ends_with(suffix) {
            normalized_path.truncate(normalized_path.len() - suffix.len());
            break;
        }
    }
    let normalized_path = normalized_path.trim_end_matches('/');

    let origin = parsed.origin().ascii_serialization();
    if normalized_path.is_empty() {
        origin
    } else {
        format!("{origin}{normalized_path}")
    }
}

pub fn parse_custom_headers(value: Option<&Value>) -> Result<BTreeMap<String, String>, String> {
    let Some(value) = value else {
        return Ok(BTreeMap::new());
    };

    let raw_headers = match value {
        Value::Null => return Ok(BTreeMap::new()),
        Value::Object(map) => map.clone(),
        Value::String(text) => {
            let raw_text = text.trim();
            if raw_text.is_empty() {
                return Ok(BTreeMap::new());
            }
            let parsed: Value = serde_json::from_str(raw_text)
                .map_err(|_| "llmCustomHeaders 必须是 JSON 对象".to_string())?;
            let Value::Object(map) = parsed else {
                return Err("llmCustomHeaders 必须是 JSON 对象".to_string());
            };
            map
        }
        _ => return Err("llmCustomHeaders 必须是 JSON 对象".to_string()),
    };

    let mut normalized = BTreeMap::new();
    for (key, header_value) in raw_headers {
        let header_name = key.trim().to_string();
        if header_name.is_empty() {
            continue;
        }

        let header_value = match header_value {
            Value::Null => String::new(),
            Value::String(value) => value,
            Value::Bool(value) => {
                if value {
                    "True".to_string()
                } else {
                    "False".to_string()
                }
            }
            Value::Number(value) => value.to_string(),
            Value::Array(_) | Value::Object(_) => {
                return Err("llmCustomHeaders 必须是扁平的 JSON 对象".to_string())
            }
        };
        normalized.insert(header_name, header_value);
    }

    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{normalize_base_url, parse_custom_headers};

    #[test]
    fn normalize_base_url_strips_known_root_endpoints() {
        assert_eq!(
            normalize_base_url("https://gateway.example/v1/chat/completions?foo=bar#frag"),
            "https://gateway.example/v1"
        );
        assert_eq!(
            normalize_base_url("https://api.openai.com/v1/models"),
            "https://api.openai.com/v1"
        );
    }

    #[test]
    fn normalize_base_url_keeps_non_absolute_inputs_trimmed() {
        assert_eq!(normalize_base_url("/custom/path/"), "/custom/path");
        assert_eq!(normalize_base_url(""), "");
    }

    #[test]
    fn parse_custom_headers_normalizes_scalars_and_ignores_empty_names() {
        let headers = parse_custom_headers(Some(&json!(
            "{\" Authorization \": 123, \"\": \"skip\", \"X-Trace\": null, \"X-Mode\": true}"
        )))
        .expect("custom headers should parse");

        assert_eq!(headers.get("Authorization").map(String::as_str), Some("123"));
        assert_eq!(headers.get("X-Trace").map(String::as_str), Some(""));
        assert_eq!(headers.get("X-Mode").map(String::as_str), Some("True"));
        assert!(!headers.contains_key(""));
    }

    #[test]
    fn parse_custom_headers_rejects_nested_values() {
        let error = parse_custom_headers(Some(&json!({"X-Nested": {"bad": true}})))
            .expect_err("nested values should fail");
        assert_eq!(error, "llmCustomHeaders 必须是扁平的 JSON 对象");
    }
}
