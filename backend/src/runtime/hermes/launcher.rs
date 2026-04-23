use anyhow::Result;
use tokio::process::Command;

use super::contracts::AgentManifest;

#[derive(Debug, PartialEq, Eq)]
pub enum ContainerStatus {
    Running,
    Stopped,
    NotFound,
}

pub async fn ensure_container_running(manifest: &AgentManifest) -> Result<ContainerStatus> {
    let status = inspect_container(&manifest.container_name).await?;
    Ok(status)
}

pub async fn stop_container(manifest: &AgentManifest) -> Result<()> {
    Command::new("docker")
        .args(["stop", &manifest.container_name])
        .output()
        .await?;
    Ok(())
}

async fn inspect_container(container_name: &str) -> Result<ContainerStatus> {
    let output = Command::new("docker")
        .args([
            "inspect",
            "--format",
            "{{.State.Status}}",
            container_name,
        ])
        .output()
        .await?;

    if !output.status.success() {
        return Ok(ContainerStatus::NotFound);
    }

    let state = String::from_utf8_lossy(&output.stdout).trim().to_string();
    match state.as_str() {
        "running" => Ok(ContainerStatus::Running),
        _ => Ok(ContainerStatus::Stopped),
    }
}
