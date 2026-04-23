use anyhow::Result;

use super::contracts::{HandoffResult, HandoffStatus};

pub fn parse_hermes_output(raw: &str) -> Result<HandoffResult> {
    if let Ok(val) = serde_json::from_str::<serde_json::Value>(raw) {
        let status = val
            .get("status")
            .and_then(|s| s.as_str())
            .and_then(|s| match s {
                "success" => Some(HandoffStatus::Success),
                "failure" => Some(HandoffStatus::Failure),
                "timeout" => Some(HandoffStatus::Timeout),
                "error" => Some(HandoffStatus::Error),
                _ => None,
            })
            .unwrap_or(HandoffStatus::Success);

        let summary = val
            .get("summary")
            .and_then(|s| s.as_str())
            .unwrap_or("")
            .to_string();

        let structured_outputs = val
            .get("structured_outputs")
            .and_then(|a| a.as_array())
            .cloned()
            .unwrap_or_default();

        let diagnostics = val.get("diagnostics").cloned();

        return Ok(HandoffResult {
            status,
            summary,
            structured_outputs,
            diagnostics,
        });
    }

    Ok(HandoffResult {
        status: HandoffStatus::Error,
        summary: raw.to_string(),
        structured_outputs: vec![],
        diagnostics: None,
    })
}
