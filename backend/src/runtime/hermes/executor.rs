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
        bail!(
            "docker exec failed: {}",
            format_docker_exec_failure(&output)
        );
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn format_docker_exec_failure(output: &std::process::Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    match (stderr.is_empty(), stdout.is_empty()) {
        (false, false) => format!("stderr:\n{stderr}\nstdout:\n{stdout}"),
        (false, true) => stderr,
        (true, false) => stdout,
        (true, true) => "docker exec exited non-zero with no output".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::format_docker_exec_failure;

    fn output(stdout: &str, stderr: &str) -> std::process::Output {
        use std::os::unix::process::ExitStatusExt;
        std::process::Output {
            status: std::process::ExitStatus::from_raw(1 << 8),
            stdout: stdout.as_bytes().to_vec(),
            stderr: stderr.as_bytes().to_vec(),
        }
    }

    #[test]
    fn format_docker_exec_failure_prefers_both_streams_when_available() {
        let rendered = format_docker_exec_failure(&output("stdout line", "stderr line"));
        assert!(rendered.contains("stderr:\nstderr line"));
        assert!(rendered.contains("stdout:\nstdout line"));
    }

    #[test]
    fn format_docker_exec_failure_uses_stdout_when_stderr_is_empty() {
        let rendered = format_docker_exec_failure(&output("session_id: abc123", ""));
        assert_eq!(rendered, "session_id: abc123");
    }
}
