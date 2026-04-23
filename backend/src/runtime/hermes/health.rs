use anyhow::Result;
use tokio::process::Command;

use super::contracts::AgentManifest;

#[derive(Debug, PartialEq, Eq)]
pub enum HealthStatus {
    Healthy,
    Unhealthy(String),
    Unavailable,
}

pub async fn check_health(manifest: &AgentManifest) -> Result<HealthStatus> {
    let output = Command::new("docker")
        .args([
            "exec",
            &manifest.container_name,
            "sh",
            "-c",
            &manifest.healthcheck.command,
        ])
        .output()
        .await;

    match output {
        Ok(out) if out.status.success() => Ok(HealthStatus::Healthy),
        Ok(out) => {
            let stderr = String::from_utf8_lossy(&out.stderr).to_string();
            Ok(HealthStatus::Unhealthy(stderr))
        }
        Err(e) => {
            let msg = e.to_string();
            if msg.contains("No such container") || msg.contains("is not running") {
                Ok(HealthStatus::Unavailable)
            } else {
                Err(e.into())
            }
        }
    }
}
