use std::time::Duration;

use anyhow::{bail, Result};
use tokio::process::Command;
use tokio::time::timeout;

use super::contracts::{AgentManifest, HandoffRequest, HandoffResult, HandoffStatus};
use super::parser::parse_hermes_output;

pub async fn execute_handoff(
    manifest: &AgentManifest,
    handoff: &HandoffRequest,
) -> Result<HandoffResult> {
    let payload_json = serde_json::to_string(&handoff.payload)?;

    let dispatch_timeout = Duration::from_secs(manifest.dispatch_timeout_seconds);

    let result = timeout(dispatch_timeout, run_docker_exec(manifest, &payload_json)).await;

    match result {
        Ok(Ok(output)) => parse_hermes_output(&output),
        Ok(Err(e)) => {
            let msg = e.to_string();
            if msg.contains("No such container") || msg.contains("is not running") {
                Ok(HandoffResult {
                    status: HandoffStatus::Error,
                    summary: format!(
                        "container {} is not running: {}",
                        manifest.container_name, msg
                    ),
                    structured_outputs: vec![],
                    diagnostics: None,
                })
            } else {
                Err(e)
            }
        }
        Err(_) => Ok(HandoffResult {
            status: HandoffStatus::Timeout,
            summary: format!(
                "handoff timed out after {}s",
                manifest.dispatch_timeout_seconds
            ),
            structured_outputs: vec![],
            diagnostics: None,
        }),
    }
}

async fn run_docker_exec(manifest: &AgentManifest, payload_json: &str) -> Result<String> {
    let output = Command::new("docker")
        .args([
            "exec",
            &manifest.container_name,
            "hermes",
            "chat",
            "-Q",
            "-q",
            payload_json,
            "--source",
            "tool",
        ])
        .output()
        .await?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("docker exec failed: {}", stderr);
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}
