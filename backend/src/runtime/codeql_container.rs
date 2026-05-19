use anyhow::{bail, Context, Result};
use std::path::Path;
use std::process::Command;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use uuid::Uuid;

use super::container_util;

/// Result of executing a command inside a container.
#[derive(Debug, Clone)]
pub struct ExecResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub truncated: bool,
}

/// RAII guard that removes the exploration container on drop.
pub struct ExplorationGuard {
    container_name: String,
    removed: bool,
}

impl ExplorationGuard {
    pub fn container_name(&self) -> &str {
        &self.container_name
    }
}

impl Drop for ExplorationGuard {
    fn drop(&mut self) {
        if !self.removed {
            let _ = stop_exploration_container(&self.container_name);
        }
    }
}

const MAX_OUTPUT_BYTES: usize = 2 * 1024 * 1024; // 2 MiB default

/// Start a long-running exploration container for interactive CodeQL build exploration.
pub fn start_exploration_container(
    task_id: &str,
    image: &str,
    workspace_dir: &Path,
    memory_mb: u64,
) -> Result<ExplorationGuard> {
    let runtime_bin = container_util::container_runtime_bin();
    let short_id = &Uuid::new_v4().to_string()[..8];
    let container_name = format!("codeql-explore-{task_id}-{short_id}");

    let workspace_mount = format!("{}:/scan/workspace:rw", workspace_dir.display());
    let memory_flag = format!("{}m", memory_mb);

    let output = Command::new(&runtime_bin)
        .args([
            "run",
            "-d",
            "--name",
            &container_name,
            "--memory",
            &memory_flag,
            "-v",
            &workspace_mount,
            image,
            "sleep",
            "infinity",
        ])
        .output()
        .context("failed to start exploration container")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("failed to start exploration container: {stderr}");
    }

    Ok(ExplorationGuard {
        container_name,
        removed: false,
    })
}

/// Execute a command inside the exploration container.
pub fn exec_in_container(
    container_name: &str,
    command: &str,
    timeout_secs: u64,
    max_output_bytes: Option<usize>,
) -> Result<ExecResult> {
    let runtime_bin = container_util::container_runtime_bin();
    let max_bytes = max_output_bytes.unwrap_or(MAX_OUTPUT_BYTES);

    let child = Command::new(&runtime_bin)
        .args(["exec", container_name, "sh", "-c", command])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .context("failed to exec in container")?;

    let output = wait_with_timeout(child, Duration::from_secs(timeout_secs))
        .with_context(|| format!("container exec timed out after {timeout_secs}s"))?;

    let mut stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let mut stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let mut truncated = false;

    if stdout.len() > max_bytes {
        stdout.truncate(max_bytes);
        stdout.push_str("\n... [output truncated]");
        truncated = true;
    }
    if stderr.len() > max_bytes {
        stderr.truncate(max_bytes);
        stderr.push_str("\n... [output truncated]");
        truncated = true;
    }

    Ok(ExecResult {
        exit_code: output.status.code().unwrap_or(-1),
        stdout,
        stderr,
        truncated,
    })
}

/// Stop and remove the exploration container.
pub fn stop_exploration_container(container_name: &str) -> Result<()> {
    let runtime_bin = container_util::container_runtime_bin();
    let _ = Command::new(&runtime_bin)
        .args(["rm", "-f", container_name])
        .output();
    Ok(())
}

fn wait_with_timeout(
    child: std::process::Child,
    timeout: Duration,
) -> Result<std::process::Output> {
    let (tx, rx) = mpsc::channel();
    let _handle = thread::spawn(move || {
        let result = child.wait_with_output();
        let _ = tx.send(result);
    });

    match rx.recv_timeout(timeout) {
        Ok(result) => result.context("child process failed"),
        Err(_) => bail!("process timed out"),
    }
}
