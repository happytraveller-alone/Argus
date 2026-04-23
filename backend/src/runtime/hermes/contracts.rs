use std::fmt;
use std::str::FromStr;

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentRole {
    Recon,
    Analysis,
    Verification,
    Report,
}

impl fmt::Display for AgentRole {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AgentRole::Recon => write!(f, "recon"),
            AgentRole::Analysis => write!(f, "analysis"),
            AgentRole::Verification => write!(f, "verification"),
            AgentRole::Report => write!(f, "report"),
        }
    }
}

impl FromStr for AgentRole {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self> {
        match s {
            "recon" => Ok(AgentRole::Recon),
            "analysis" => Ok(AgentRole::Analysis),
            "verification" => Ok(AgentRole::Verification),
            "report" => Ok(AgentRole::Report),
            _ => bail!("unknown agent role: {}", s),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct InputContract {
    pub fields: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OutputContract {
    pub fields: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HealthcheckConfig {
    pub command: String,
    pub interval_seconds: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AgentManifest {
    pub id: String,
    pub role: AgentRole,
    pub image: String,
    pub container_name: String,
    pub enabled: bool,
    pub dispatch_timeout_seconds: u64,
    pub terminal_cwd: String,
    pub project_mount: String,
    pub artifacts_dir: String,
    pub runtime_home_dir: String,
    pub input_contract: InputContract,
    pub output_contract: OutputContract,
    pub healthcheck: HealthcheckConfig,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HandoffRequest {
    pub role: AgentRole,
    pub task_id: String,
    pub project_id: String,
    pub correlation_id: String,
    pub payload: serde_json::Value,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HandoffStatus {
    Success,
    Failure,
    Timeout,
    Error,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HandoffResult {
    pub status: HandoffStatus,
    pub summary: String,
    pub structured_outputs: Vec<serde_json::Value>,
    pub diagnostics: Option<serde_json::Value>,
}
