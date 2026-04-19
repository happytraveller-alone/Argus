use serde_json::{json, Value};

use super::fast_count_tokens;

pub const MAX_TOTAL_TOKENS: i64 = 100_000;
pub const MIN_RECENT_MESSAGES: usize = 15;
pub const COMPRESSION_THRESHOLD: f64 = 0.9;

#[derive(Debug, Clone)]
pub struct MemoryCompressor {
    pub max_total_tokens: i64,
    pub min_recent_messages: usize,
}

impl Default for MemoryCompressor {
    fn default() -> Self {
        Self {
            max_total_tokens: MAX_TOTAL_TOKENS,
            min_recent_messages: MIN_RECENT_MESSAGES,
        }
    }
}

impl MemoryCompressor {
    pub fn new(max_total_tokens: Option<i64>, min_recent_messages: Option<usize>) -> Self {
        Self {
            max_total_tokens: max_total_tokens.unwrap_or(MAX_TOTAL_TOKENS),
            min_recent_messages: min_recent_messages.unwrap_or(MIN_RECENT_MESSAGES),
        }
    }

    pub fn should_compress(&self, messages: &[Value]) -> bool {
        total_tokens(messages) > (self.max_total_tokens as f64 * COMPRESSION_THRESHOLD) as i64
    }

    pub fn compress_history(&self, messages: &[Value]) -> Vec<Value> {
        if !self.should_compress(messages) {
            return messages.to_vec();
        }

        let mut system_messages = Vec::new();
        let mut regular_messages = Vec::new();
        for message in messages {
            if message.get("role").and_then(Value::as_str) == Some("system") {
                system_messages.push(message.clone());
            } else {
                regular_messages.push(message.clone());
            }
        }

        let split_point = regular_messages.len().saturating_sub(self.min_recent_messages);
        let (old_messages, recent_messages) = regular_messages.split_at(split_point);
        if old_messages.is_empty() {
            return messages.to_vec();
        }

        let mut compressed = Vec::new();
        for chunk in old_messages.chunks(10) {
            compressed.push(summarize_chunk(chunk));
        }

        system_messages
            .into_iter()
            .chain(compressed)
            .chain(recent_messages.iter().cloned())
            .collect()
    }
}

pub fn compress_conversation(messages: &[Value], max_tokens: Option<i64>) -> Vec<Value> {
    MemoryCompressor::new(max_tokens, None).compress_history(messages)
}

fn total_tokens(messages: &[Value]) -> i64 {
    messages.iter().map(message_tokens).sum()
}

fn message_tokens(message: &Value) -> i64 {
    match message.get("content").cloned().unwrap_or(Value::Null) {
        Value::String(text) => fast_count_tokens(&text, "gpt-4"),
        Value::Array(parts) => parts
            .iter()
            .filter(|part| part.get("type").and_then(Value::as_str) == Some("text"))
            .map(|part| {
                fast_count_tokens(
                    part.get("text").and_then(Value::as_str).unwrap_or_default(),
                    "gpt-4",
                )
            })
            .sum(),
        other => fast_count_tokens(&other.to_string(), "gpt-4"),
    }
}

fn summarize_chunk(messages: &[Value]) -> Value {
    let message_count = messages.len();
    json!({
        "role": "assistant",
        "content": format!(
            "<context_summary message_count='{message_count}'>[已压缩 {message_count} 条历史消息]</context_summary>"
        )
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{compress_conversation, MemoryCompressor};

    fn long_messages() -> Vec<serde_json::Value> {
        vec![
            json!({"role": "system", "content": "系统提示".repeat(20)}),
            json!({"role": "user", "content": "A".repeat(120)}),
            json!({"role": "assistant", "content": "B".repeat(120)}),
            json!({"role": "user", "content": "C".repeat(120)}),
        ]
    }

    #[test]
    fn memory_compressor_uses_heuristic_estimation_path() {
        let compressor = MemoryCompressor::new(Some(40), Some(1));
        let messages = long_messages();
        assert!(compressor.should_compress(&messages));
        let compressed = compressor.compress_history(&messages);
        assert!(!compressed.is_empty());
        assert!(compressed.len() < messages.len());
    }

    #[test]
    fn compress_conversation_preserves_short_histories() {
        let messages = vec![json!({"role": "user", "content": "hello"})];
        assert_eq!(compress_conversation(&messages, Some(100)), messages);
    }
}
