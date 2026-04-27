use std::{path::PathBuf, process::Stdio, time::Duration};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::{io::AsyncWriteExt, process::Command, time};

use super::importer::redact_text;

const DEFAULT_TAIL_LIMIT: usize = 64 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunnerCommand {
    pub program: String,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub timeout_seconds: u64,
    pub stdin_json: Option<Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunnerOutcome {
    pub exit_code: Option<i32>,
    pub timed_out: bool,
    pub stdout_tail: String,
    pub stderr_tail: String,
    pub output_json: Option<Value>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunnerError {
    pub reason_code: &'static str,
    pub message: String,
}

impl RunnerError {
    fn new(reason_code: &'static str, message: impl Into<String>) -> Self {
        Self { reason_code, message: message.into() }
    }
}

pub async fn run_controlled_command(command: RunnerCommand) -> Result<RunnerOutcome, RunnerError> {
    if command.program.trim().is_empty() {
        return Err(RunnerError::new("runner_missing", "AgentFlow runner command is empty"));
    }
    let mut child = Command::new(&command.program);
    child.args(&command.args).stdout(Stdio::piped()).stderr(Stdio::piped());
    if let Some(cwd) = &command.cwd {
        child.current_dir(cwd);
    }
    if command.stdin_json.is_some() {
        child.stdin(Stdio::piped());
    }
    let mut child = child.spawn().map_err(|error| {
        RunnerError::new("runner_missing", format!("failed to spawn AgentFlow runner `{}`: {error}", command.program))
    })?;
    if let Some(stdin_json) = command.stdin_json {
        let mut stdin = child.stdin.take().ok_or_else(|| RunnerError::new("runner_failed", "runner stdin unavailable"))?;
        let bytes = serde_json::to_vec(&stdin_json).map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
        stdin.write_all(&bytes).await.map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
    }

    let timeout = Duration::from_secs(command.timeout_seconds.max(1));
    let output = match time::timeout(timeout, child.wait_with_output()).await {
        Ok(result) => result.map_err(|error| RunnerError::new("runner_failed", error.to_string()))?,
        Err(_) => {
            return Ok(RunnerOutcome {
                exit_code: None,
                timed_out: true,
                stdout_tail: String::new(),
                stderr_tail: format!("AgentFlow runner timed out after {}s", timeout.as_secs()),
                output_json: None,
            });
        }
    };
    let stdout_tail = redact_text(&tail_utf8(&output.stdout, DEFAULT_TAIL_LIMIT));
    let stderr_tail = redact_text(&tail_utf8(&output.stderr, DEFAULT_TAIL_LIMIT));
    let output_json = serde_json::from_str::<Value>(&stdout_tail).ok();
    Ok(RunnerOutcome {
        exit_code: output.status.code(),
        timed_out: false,
        stdout_tail,
        stderr_tail,
        output_json,
    })
}

pub fn tail_utf8(bytes: &[u8], limit: usize) -> String {
    let start = bytes.len().saturating_sub(limit);
    String::from_utf8_lossy(&bytes[start..]).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn agentflow_runner_tails_are_bounded_and_utf8_lossy() {
        let bytes = vec![b'a'; DEFAULT_TAIL_LIMIT + 10];
        assert_eq!(tail_utf8(&bytes, DEFAULT_TAIL_LIMIT).len(), DEFAULT_TAIL_LIMIT);
    }

    #[tokio::test]
    async fn agentflow_runner_collects_fake_process_json_and_redacts_logs() {
        let outcome = run_controlled_command(RunnerCommand {
            program: "sh".to_string(),
            args: vec!["-c".to_string(), "printf '{\"runtime\":\"agentflow\"}'; printf 'Authorization: secret' >&2".to_string()],
            cwd: None,
            timeout_seconds: 5,
            stdin_json: None,
        }).await.unwrap();
        assert_eq!(outcome.exit_code, Some(0));
        assert_eq!(outcome.output_json.unwrap()["runtime"], "agentflow");
        assert!(!outcome.stderr_tail.contains("secret"));
        assert!(outcome.stderr_tail.contains("[REDACTED]"));
    }
}
