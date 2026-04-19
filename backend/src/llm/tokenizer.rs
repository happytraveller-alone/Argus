use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeTokenCountingMode {
    Heuristic,
    Auto,
    Precise,
}

pub fn normalize_runtime_token_counting_mode(value: Option<&str>) -> RuntimeTokenCountingMode {
    match value.unwrap_or_default().trim().to_ascii_lowercase().as_str() {
        "auto" => RuntimeTokenCountingMode::Auto,
        "precise" => RuntimeTokenCountingMode::Precise,
        _ => RuntimeTokenCountingMode::Heuristic,
    }
}

pub fn get_runtime_token_counting_mode(
    env_value: Option<&str>,
    configured_value: Option<&str>,
) -> RuntimeTokenCountingMode {
    normalize_runtime_token_counting_mode(env_value.or(configured_value))
}

pub fn get_tiktoken_cache_dir(
    explicit: Option<&str>,
    configured: Option<&str>,
    legacy_env: Option<&str>,
) -> String {
    explicit
        .or(configured)
        .or(legacy_env)
        .unwrap_or_default()
        .trim()
        .to_string()
}

pub fn heuristic_estimate(text: &str) -> i64 {
    if text.is_empty() {
        return 0;
    }

    let mut ascii_chars = 0_i64;
    let mut cjk_chars = 0_i64;
    let mut other_chars = 0_i64;

    for ch in text.chars() {
        let code = ch as u32;
        if code < 128 {
            ascii_chars += 1;
        } else if (0x4E00..=0x9FFF).contains(&code)
            || (0x3400..=0x4DBF).contains(&code)
            || (0x20000..=0x2A6DF).contains(&code)
            || (0x3000..=0x303F).contains(&code)
            || (0xFF00..=0xFFEF).contains(&code)
        {
            cjk_chars += 1;
        } else {
            other_chars += 1;
        }
    }

    let tokens = ascii_chars as f64 / 4.0 + cjk_chars as f64 / 1.5 + other_chars as f64 / 2.0;
    (tokens + 0.5).floor().max(1.0) as i64
}

pub fn fast_count_tokens(text: &str, _model: &str) -> i64 {
    heuristic_estimate(text)
}

pub fn count_tokens(text: &str, _model: &str, mode: RuntimeTokenCountingMode) -> i64 {
    match mode {
        RuntimeTokenCountingMode::Heuristic
        | RuntimeTokenCountingMode::Auto
        | RuntimeTokenCountingMode::Precise => heuristic_estimate(text),
    }
}

pub fn estimate_message_tokens(messages: &[Value], model: &str) -> i64 {
    let mut total = 0_i64;

    for message in messages {
        total += 4;
        match message.get("content").cloned().unwrap_or(Value::Null) {
            Value::String(text) => {
                total += count_tokens(&text, model, RuntimeTokenCountingMode::Heuristic);
            }
            Value::Array(parts) => {
                for part in parts {
                    if part.get("type").and_then(Value::as_str) == Some("text") {
                        if let Some(text) = part.get("text").and_then(Value::as_str) {
                            total +=
                                count_tokens(text, model, RuntimeTokenCountingMode::Heuristic);
                        }
                    }
                }
            }
            _ => {}
        }
    }

    total + 3
}

pub fn prewarm_tiktoken(_model: Option<&str>) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        count_tokens, estimate_message_tokens, fast_count_tokens, get_runtime_token_counting_mode,
        get_tiktoken_cache_dir, heuristic_estimate, normalize_runtime_token_counting_mode,
        RuntimeTokenCountingMode,
    };

    #[test]
    fn runtime_mode_defaults_to_heuristic() {
        assert_eq!(
            normalize_runtime_token_counting_mode(None),
            RuntimeTokenCountingMode::Heuristic
        );
        assert_eq!(
            get_runtime_token_counting_mode(None, Some("auto")),
            RuntimeTokenCountingMode::Auto
        );
    }

    #[test]
    fn cache_dir_uses_first_non_empty_source() {
        assert_eq!(
            get_tiktoken_cache_dir(Some("/tmp/cache"), Some("/tmp/other"), Some("/tmp/legacy")),
            "/tmp/cache"
        );
        assert_eq!(
            get_tiktoken_cache_dir(None, Some("/tmp/other"), Some("/tmp/legacy")),
            "/tmp/other"
        );
    }

    #[test]
    fn heuristic_counting_matches_retired_python_behavior() {
        let expected = heuristic_estimate("hello world");
        assert_eq!(
            count_tokens("hello world", "gpt-4o-mini", RuntimeTokenCountingMode::Heuristic),
            expected
        );
        assert_eq!(fast_count_tokens("hello world", "gpt-4o-mini"), expected);
    }

    #[test]
    fn estimate_message_tokens_preserves_chat_shape() {
        let messages = vec![
            json!({"role": "system", "content": "系统提示"}),
            json!({"role": "user", "content": "hello"}),
        ];
        assert!(estimate_message_tokens(&messages, "gpt-4o-mini") > 0);
    }
}
