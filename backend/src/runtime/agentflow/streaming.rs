use std::collections::HashMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::{broadcast, Mutex};

pub const BROADCAST_CHANNEL_BUFFER: usize = 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StreamingEvent {
    pub event_type: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node_id: Option<String>,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub sequence: i64,
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub message: String,
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub data: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_input: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_output: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_duration_ms: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub accumulated: Option<String>,
}

pub enum AdapterLine {
    StreamEvent(StreamingEvent),
    FinalContract(Value),
    Diagnostic(String),
}

pub fn classify_adapter_line(line: &str) -> AdapterLine {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return AdapterLine::Diagnostic(String::new());
    }
    let Ok(value) = serde_json::from_str::<Value>(trimmed) else {
        return AdapterLine::Diagnostic(trimmed.to_string());
    };
    if value.get("stream").and_then(Value::as_bool) == Some(true) {
        let event_type = value
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("info")
            .to_string();
        return AdapterLine::StreamEvent(StreamingEvent {
            event_type,
            node_id: value.get("node_id").and_then(Value::as_str).map(str::to_string),
            role: value
                .get("role")
                .and_then(Value::as_str)
                .unwrap_or("runner")
                .to_string(),
            sequence: value.get("sequence").and_then(Value::as_i64).unwrap_or(0),
            timestamp: value
                .get("timestamp")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            message: value
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            data: value.get("data").cloned().unwrap_or(Value::Null),
            tool_name: value.get("tool_name").and_then(Value::as_str).map(str::to_string),
            tool_input: value.get("tool_input").cloned(),
            tool_output: value.get("tool_output").cloned(),
            tool_duration_ms: value.get("tool_duration_ms").and_then(Value::as_i64),
            token: value.get("token").and_then(Value::as_str).map(str::to_string),
            accumulated: value.get("accumulated").and_then(Value::as_str).map(str::to_string),
        });
    }
    if value.get("contract_version").is_some() {
        return AdapterLine::FinalContract(value);
    }
    AdapterLine::Diagnostic(trimmed.to_string())
}

pub fn should_persist_event(event_type: &str) -> bool {
    !matches!(event_type, "thinking_token" | "heartbeat")
}

pub type TaskEventChannels =
    Arc<Mutex<HashMap<String, broadcast::Sender<StreamingEvent>>>>;

pub fn get_or_create_channel(
    channels: &mut HashMap<String, broadcast::Sender<StreamingEvent>>,
    task_id: &str,
) -> broadcast::Sender<StreamingEvent> {
    channels
        .entry(task_id.to_string())
        .or_insert_with(|| {
            let (tx, _) = broadcast::channel(BROADCAST_CHANNEL_BUFFER);
            tx
        })
        .clone()
}

pub fn remove_channel(
    channels: &mut HashMap<String, broadcast::Sender<StreamingEvent>>,
    task_id: &str,
) {
    channels.remove(task_id);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_stream_event() {
        let line = r#"{"stream":true,"type":"thinking_token","node_id":"env-inter","role":"env-inter","sequence":1,"timestamp":"2026-01-01T00:00:00Z","message":"","token":"hello"}"#;
        match classify_adapter_line(line) {
            AdapterLine::StreamEvent(event) => {
                assert_eq!(event.event_type, "thinking_token");
                assert_eq!(event.node_id.as_deref(), Some("env-inter"));
                assert_eq!(event.token.as_deref(), Some("hello"));
            }
            _ => panic!("expected StreamEvent"),
        }
    }

    #[test]
    fn classify_final_contract() {
        let line = r#"{"contract_version":"argus-agentflow-p1/v1","task_id":"t1","run":{}}"#;
        match classify_adapter_line(line) {
            AdapterLine::FinalContract(value) => {
                assert_eq!(
                    value.get("contract_version").unwrap().as_str().unwrap(),
                    "argus-agentflow-p1/v1"
                );
            }
            _ => panic!("expected FinalContract"),
        }
    }

    #[test]
    fn classify_diagnostic() {
        match classify_adapter_line("some plain text log line") {
            AdapterLine::Diagnostic(text) => assert_eq!(text, "some plain text log line"),
            _ => panic!("expected Diagnostic"),
        }
    }

    #[test]
    fn classify_empty() {
        match classify_adapter_line("") {
            AdapterLine::Diagnostic(text) => assert!(text.is_empty()),
            _ => panic!("expected Diagnostic"),
        }
    }

    #[test]
    fn should_persist_filters_transient_events() {
        assert!(!should_persist_event("thinking_token"));
        assert!(!should_persist_event("heartbeat"));
        assert!(should_persist_event("thinking_end"));
        assert!(should_persist_event("tool_call"));
        assert!(should_persist_event("node_start"));
        assert!(should_persist_event("info"));
    }
}
