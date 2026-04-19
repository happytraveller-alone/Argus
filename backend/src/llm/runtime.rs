use serde::{Deserialize, Serialize};

use super::{normalize_provider_id, LlmUsage};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AdapterMode {
    OpenAiCompatible,
    Anthropic,
    NativeOnly,
}

pub fn adapter_mode_for_provider(provider: &str) -> AdapterMode {
    match normalize_provider_id(provider).as_str() {
        "anthropic" => AdapterMode::Anthropic,
        "baidu" | "minimax" | "doubao" => AdapterMode::NativeOnly,
        _ => AdapterMode::OpenAiCompatible,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StreamEventKind {
    Token,
    Done,
    Error,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct StreamEvent {
    pub kind: StreamEventKind,
    pub content: Option<String>,
    pub accumulated: Option<String>,
    pub finish_reason: Option<String>,
    pub error_type: Option<String>,
    pub error: Option<String>,
    pub usage: Option<LlmUsage>,
}

#[derive(Debug, Default, Clone)]
pub struct StreamAccumulator {
    accumulated: String,
    saw_any_delta: bool,
}

impl StreamAccumulator {
    pub fn push_delta(
        &mut self,
        content: Option<&str>,
        reasoning_content: Option<&str>,
        text: Option<&str>,
    ) -> Option<StreamEvent> {
        let delta = content
            .filter(|value| !value.is_empty())
            .or(reasoning_content.filter(|value| !value.is_empty()))
            .or(text.filter(|value| !value.is_empty()))?;

        self.saw_any_delta = true;
        self.accumulated.push_str(delta);
        Some(StreamEvent {
            kind: StreamEventKind::Token,
            content: Some(delta.to_string()),
            accumulated: Some(self.accumulated.clone()),
            finish_reason: None,
            error_type: None,
            error: None,
            usage: None,
        })
    }

    pub fn finish(
        &self,
        finish_reason: Option<&str>,
        usage: Option<LlmUsage>,
    ) -> StreamEvent {
        if !self.saw_any_delta {
            if let Some(reason) = finish_reason {
                return StreamEvent {
                    kind: StreamEventKind::Error,
                    content: None,
                    accumulated: None,
                    finish_reason: Some(reason.to_string()),
                    error_type: Some("empty_response".to_string()),
                    error: Some(format!(
                        "API returned empty response (finish_reason={reason})"
                    )),
                    usage,
                };
            }

            return StreamEvent {
                kind: StreamEventKind::Error,
                content: None,
                accumulated: None,
                finish_reason: None,
                error_type: Some("empty_stream".to_string()),
                error: Some("API returned empty stream".to_string()),
                usage,
            };
        }

        StreamEvent {
            kind: StreamEventKind::Done,
            content: Some(self.accumulated.clone()),
            accumulated: Some(self.accumulated.clone()),
            finish_reason: Some(finish_reason.unwrap_or("stop").to_string()),
            error_type: None,
            error: None,
            usage,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{adapter_mode_for_provider, AdapterMode, StreamAccumulator, StreamEventKind};
    use crate::llm::LlmUsage;

    #[test]
    fn adapter_mode_matches_retired_python_runtime_split() {
        assert_eq!(adapter_mode_for_provider("claude"), AdapterMode::Anthropic);
        assert_eq!(adapter_mode_for_provider("baidu"), AdapterMode::NativeOnly);
        assert_eq!(adapter_mode_for_provider("custom"), AdapterMode::OpenAiCompatible);
    }

    #[test]
    fn finish_without_content_and_with_finish_reason_emits_empty_response_error() {
        let accumulator = StreamAccumulator::default();
        let event = accumulator.finish(
            Some("content_filter"),
            Some(LlmUsage {
                prompt_tokens: 12,
                completion_tokens: 0,
                total_tokens: 12,
            }),
        );

        assert_eq!(event.kind, StreamEventKind::Error);
        assert_eq!(event.error_type.as_deref(), Some("empty_response"));
        assert!(
            event
                .error
                .as_deref()
                .unwrap_or_default()
                .contains("finish_reason=content_filter")
        );
    }

    #[test]
    fn finish_without_any_delta_emits_empty_stream_error() {
        let accumulator = StreamAccumulator::default();
        let event = accumulator.finish(None, None);

        assert_eq!(event.kind, StreamEventKind::Error);
        assert_eq!(event.error_type.as_deref(), Some("empty_stream"));
    }

    #[test]
    fn token_then_done_matches_stream_shell_contract() {
        let mut accumulator = StreamAccumulator::default();
        let token = accumulator
            .push_delta(Some("hi"), None, None)
            .expect("token event should exist");
        let done = accumulator.finish(Some("stop"), None);

        assert_eq!(token.kind, StreamEventKind::Token);
        assert_eq!(token.accumulated.as_deref(), Some("hi"));
        assert_eq!(done.kind, StreamEventKind::Done);
        assert_eq!(done.content.as_deref(), Some("hi"));
    }
}
