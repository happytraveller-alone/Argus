use anyhow::Result;

use super::contracts::{AgentRole, HandoffRequest};

pub fn build_handoff(
    role: &AgentRole,
    task_id: &str,
    project_id: &str,
    correlation_id: &str,
    payload: serde_json::Value,
) -> HandoffRequest {
    HandoffRequest {
        role: role.clone(),
        task_id: task_id.to_string(),
        project_id: project_id.to_string(),
        correlation_id: correlation_id.to_string(),
        payload,
    }
}

pub fn serialize_handoff(req: &HandoffRequest) -> Result<String> {
    Ok(serde_json::to_string(req)?)
}
