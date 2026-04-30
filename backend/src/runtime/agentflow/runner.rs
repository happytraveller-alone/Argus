use std::{path::PathBuf, process::Stdio, time::Duration};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::Command,
    sync::broadcast,
    time,
};

use super::importer::redact_text;
use super::streaming::{self, StreamingEvent};

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
        Self {
            reason_code,
            message: message.into(),
        }
    }
}

pub async fn run_controlled_command(command: RunnerCommand) -> Result<RunnerOutcome, RunnerError> {
    if command.program.trim().is_empty() {
        return Err(RunnerError::new(
            "runner_missing",
            "AgentFlow runner command is empty",
        ));
    }
    let mut child = Command::new(&command.program);
    child
        .args(&command.args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(cwd) = &command.cwd {
        child.current_dir(cwd);
    }
    if command.stdin_json.is_some() {
        child.stdin(Stdio::piped());
    }
    let mut child = child.spawn().map_err(|error| {
        RunnerError::new(
            "runner_missing",
            format!(
                "failed to spawn AgentFlow runner `{}`: {error}",
                command.program
            ),
        )
    })?;
    if let Some(stdin_json) = command.stdin_json {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| RunnerError::new("runner_failed", "runner stdin unavailable"))?;
        let bytes = serde_json::to_vec(&stdin_json)
            .map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
        stdin
            .write_all(&bytes)
            .await
            .map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
    }

    let timeout = Duration::from_secs(command.timeout_seconds.max(1));
    let output = match time::timeout(timeout, child.wait_with_output()).await {
        Ok(result) => {
            result.map_err(|error| RunnerError::new("runner_failed", error.to_string()))?
        }
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

pub async fn run_streaming_command(
    command: RunnerCommand,
    event_tx: broadcast::Sender<StreamingEvent>,
) -> Result<RunnerOutcome, RunnerError> {
    if command.program.trim().is_empty() {
        return Err(RunnerError::new(
            "runner_missing",
            "AgentFlow runner command is empty",
        ));
    }
    let mut child_cmd = Command::new(&command.program);
    child_cmd
        .args(&command.args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(cwd) = &command.cwd {
        child_cmd.current_dir(cwd);
    }
    if command.stdin_json.is_some() {
        child_cmd.stdin(Stdio::piped());
    }
    let mut child = child_cmd.spawn().map_err(|error| {
        RunnerError::new(
            "runner_missing",
            format!(
                "failed to spawn AgentFlow runner `{}`: {error}",
                command.program
            ),
        )
    })?;

    if let Some(stdin_json) = command.stdin_json {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| RunnerError::new("runner_failed", "runner stdin unavailable"))?;
        let bytes = serde_json::to_vec(&stdin_json)
            .map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
        stdin
            .write_all(&bytes)
            .await
            .map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;
        drop(stdin);
    }

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| RunnerError::new("runner_failed", "runner stdout unavailable"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| RunnerError::new("runner_failed", "runner stderr unavailable"))?;

    let timeout = Duration::from_secs(command.timeout_seconds.max(1));

    let stderr_handle = tokio::spawn(async move {
        let mut buf = String::new();
        let mut reader = BufReader::new(stderr);
        let _ = tokio::io::AsyncReadExt::read_to_string(&mut reader, &mut buf).await;
        buf
    });

    let mut stdout_reader = BufReader::new(stdout).lines();
    let mut contract_json: Option<Value> = None;
    let mut stdout_tail = String::new();

    let stream_result = time::timeout(timeout, async {
        while let Some(line) = stdout_reader
            .next_line()
            .await
            .map_err(|e| RunnerError::new("runner_failed", e.to_string()))?
        {
            if stdout_tail.len() < DEFAULT_TAIL_LIMIT {
                stdout_tail.push_str(&line);
                stdout_tail.push('\n');
            }

            match streaming::classify_adapter_line(&line) {
                streaming::AdapterLine::StreamEvent(event) => {
                    let _ = event_tx.send(event);
                }
                streaming::AdapterLine::FinalContract(value) => {
                    contract_json = Some(value);
                }
                streaming::AdapterLine::Diagnostic(_) => {}
            }
        }
        Ok::<(), RunnerError>(())
    })
    .await;

    match stream_result {
        Ok(Ok(())) => {}
        Ok(Err(error)) => return Err(error),
        Err(_) => {
            let _ = child.kill().await;
            return Ok(RunnerOutcome {
                exit_code: None,
                timed_out: true,
                stdout_tail: String::new(),
                stderr_tail: format!(
                    "AgentFlow runner timed out after {}s",
                    timeout.as_secs()
                ),
                output_json: None,
            });
        }
    }

    let status = child
        .wait()
        .await
        .map_err(|error| RunnerError::new("runner_failed", error.to_string()))?;

    let stderr_raw = stderr_handle.await.unwrap_or_default();
    let stderr_tail = redact_text(&tail_utf8(stderr_raw.as_bytes(), DEFAULT_TAIL_LIMIT));
    let stdout_tail = redact_text(&tail_utf8(stdout_tail.as_bytes(), DEFAULT_TAIL_LIMIT));

    if contract_json.is_none() {
        contract_json = serde_json::from_str::<Value>(&stdout_tail).ok();
    }

    Ok(RunnerOutcome {
        exit_code: status.code(),
        timed_out: false,
        stdout_tail,
        stderr_tail,
        output_json: contract_json,
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
        assert_eq!(
            tail_utf8(&bytes, DEFAULT_TAIL_LIMIT).len(),
            DEFAULT_TAIL_LIMIT
        );
    }

    #[tokio::test]
    async fn agentflow_runner_collects_fake_process_json_and_redacts_logs() {
        let outcome = run_controlled_command(RunnerCommand {
            program: "sh".to_string(),
            args: vec![
                "-c".to_string(),
                "printf '{\"runtime\":\"agentflow\"}'; printf 'Authorization: secret' >&2"
                    .to_string(),
            ],
            cwd: None,
            timeout_seconds: 5,
            stdin_json: None,
        })
        .await
        .unwrap();
        assert_eq!(outcome.exit_code, Some(0));
        assert_eq!(outcome.output_json.unwrap()["runtime"], "agentflow");
        assert!(!outcome.stderr_tail.contains("secret"));
        assert!(outcome.stderr_tail.contains("[REDACTED]"));
    }
}
