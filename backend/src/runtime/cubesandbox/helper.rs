use std::{collections::BTreeMap, str::FromStr, time::Duration};

use anyhow::{bail, Result};
use reqwest::Url;
use tokio::{process::Command, time::timeout};

use super::config::CubeSandboxConfig;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CubeSandboxHelperCommand {
    Doctor,
    Status,
    RunVmBackground,
    Install,
    CreateTemplate,
    WatchTemplate,
}

impl CubeSandboxHelperCommand {
    fn as_str(self) -> &'static str {
        match self {
            Self::Doctor => "doctor",
            Self::Status => "status",
            Self::RunVmBackground => "run-vm-background",
            Self::Install => "install",
            Self::CreateTemplate => "create-template",
            Self::WatchTemplate => "watch-template",
        }
    }
}

impl TryFrom<&str> for CubeSandboxHelperCommand {
    type Error = anyhow::Error;

    fn try_from(value: &str) -> Result<Self> {
        match value {
            "doctor" => Ok(Self::Doctor),
            "status" => Ok(Self::Status),
            "run-vm-background" => Ok(Self::RunVmBackground),
            "install" => Ok(Self::Install),
            "create-template" => Ok(Self::CreateTemplate),
            "watch-template" => Ok(Self::WatchTemplate),
            _ => bail!("unsupported CubeSandbox helper command: {value}"),
        }
    }
}

impl FromStr for CubeSandboxHelperCommand {
    type Err = anyhow::Error;

    fn from_str(value: &str) -> Result<Self> {
        Self::try_from(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CubeSandboxHelperInvocation {
    pub command: String,
    pub args: Vec<String>,
    pub env: BTreeMap<String, String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CubeSandboxHelperOutput {
    pub success: bool,
    pub exit_code: Option<i32>,
    pub stdout_tail: String,
    pub stderr_tail: String,
}

pub fn build_helper_invocation(
    config: &CubeSandboxConfig,
    helper_command: CubeSandboxHelperCommand,
) -> Result<CubeSandboxHelperInvocation> {
    let mut env = BTreeMap::from([
        ("CUBE_WORK_DIR".to_string(), config.work_dir.clone()),
        ("CUBE_TEMPLATE_ID".to_string(), config.template_id.clone()),
    ]);

    if let Some(port) = local_url_port(&config.api_base_url, false)? {
        env.insert("CUBE_API_PORT".to_string(), port.to_string());
    }
    if let Some(port) = local_url_port(&config.data_plane_base_url, true)? {
        env.insert("CUBE_PROXY_HTTPS_PORT".to_string(), port.to_string());
    }

    Ok(CubeSandboxHelperInvocation {
        command: config.helper_path.clone(),
        args: vec![helper_command.as_str().to_string()],
        env,
    })
}

pub async fn run_helper_command(
    config: &CubeSandboxConfig,
    helper_command: CubeSandboxHelperCommand,
) -> Result<CubeSandboxHelperOutput> {
    let invocation = build_helper_invocation(config, helper_command)?;
    let mut command = Command::new(&invocation.command);
    command.args(&invocation.args);
    command.env_clear();
    command.envs(&invocation.env);
    command.env("PATH", std::env::var("PATH").unwrap_or_default());
    command.env("HOME", std::env::var("HOME").unwrap_or_default());

    let timeout_result = timeout(
        Duration::from_secs(config.helper_timeout_seconds.max(1)),
        command.output(),
    )
    .await;
    let output = match timeout_result {
        Ok(output) => output?,
        Err(_) => bail!(
            "CubeSandbox helper command timed out: {}",
            helper_command.as_str()
        ),
    };

    Ok(CubeSandboxHelperOutput {
        success: output.status.success(),
        exit_code: output.status.code(),
        stdout_tail: bounded_tail(&String::from_utf8_lossy(&output.stdout), 8192),
        stderr_tail: bounded_tail(&String::from_utf8_lossy(&output.stderr), 8192),
    })
}

fn local_url_port(value: &str, require_https: bool) -> Result<Option<u16>> {
    let parsed = Url::parse(value)?;
    let Some(host) = parsed.host_str() else {
        return Ok(None);
    };
    if host != "127.0.0.1" && host != "localhost" {
        bail!("remote_lifecycle_not_supported: lifecycle URLs must target localhost");
    }
    if require_https && parsed.scheme() != "https" {
        return Ok(None);
    }
    Ok(parsed.port())
}

fn bounded_tail(value: &str, limit: usize) -> String {
    if value.len() <= limit {
        return value.to_string();
    }
    let mut start = value.len().saturating_sub(limit);
    while !value.is_char_boundary(start) {
        start += 1;
    }
    value[start..].to_string()
}
