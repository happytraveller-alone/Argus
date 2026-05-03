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
    ConfigureDockerMirror,
    StartLocalRegistry,
    BuildCodeqlCppImage,
    CreateCodeqlCppTemplate,
    ProvisionCodeqlCppTemplate,
}

impl CubeSandboxHelperCommand {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Doctor => "doctor",
            Self::Status => "status",
            Self::RunVmBackground => "run-vm-background",
            Self::Install => "install",
            Self::CreateTemplate => "create-template",
            Self::WatchTemplate => "watch-template",
            Self::ConfigureDockerMirror => "configure-docker-mirror",
            Self::StartLocalRegistry => "start-local-registry",
            Self::BuildCodeqlCppImage => "build-codeql-cpp-image",
            Self::CreateCodeqlCppTemplate => "create-codeql-cpp-template",
            Self::ProvisionCodeqlCppTemplate => "provision-codeql-cpp-template",
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
            "configure-docker-mirror" => Ok(Self::ConfigureDockerMirror),
            "start-local-registry" => Ok(Self::StartLocalRegistry),
            "build-codeql-cpp-image" => Ok(Self::BuildCodeqlCppImage),
            "create-codeql-cpp-template" => Ok(Self::CreateCodeqlCppTemplate),
            "provision-codeql-cpp-template" => Ok(Self::ProvisionCodeqlCppTemplate),
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
    if let Some(host) = url_lifecycle_host(&config.api_base_url)? {
        env.insert("CUBE_SSH_HOST".to_string(), host);
    }

    Ok(CubeSandboxHelperInvocation {
        command: config.helper_path.clone(),
        args: vec![helper_command.as_str().to_string()],
        env,
    })
}

pub fn should_run_local_lifecycle(config: &CubeSandboxConfig) -> Result<bool> {
    Ok(url_targets_localhost(&config.api_base_url)?
        && url_targets_localhost(&config.data_plane_base_url)?)
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

fn is_lifecycle_eligible_host(host: &str) -> bool {
    matches!(
        host,
        "127.0.0.1" | "localhost" | "::1" | "host.docker.internal"
    )
}

fn local_url_port(value: &str, require_https: bool) -> Result<Option<u16>> {
    let parsed = Url::parse(value)?;
    let Some(host) = parsed.host_str() else {
        return Ok(None);
    };
    if !is_lifecycle_eligible_host(host) {
        bail!(
            "remote_lifecycle_not_supported: lifecycle URLs must target localhost or host.docker.internal"
        );
    }
    if require_https && parsed.scheme() != "https" {
        return Ok(None);
    }
    Ok(parsed.port())
}

fn url_targets_localhost(value: &str) -> Result<bool> {
    let parsed = Url::parse(value)?;
    let Some(host) = parsed.host_str() else {
        return Ok(false);
    };
    Ok(is_lifecycle_eligible_host(host))
}

fn url_lifecycle_host(value: &str) -> Result<Option<String>> {
    let parsed = Url::parse(value)?;
    let Some(host) = parsed.host_str() else {
        return Ok(None);
    };
    if !is_lifecycle_eligible_host(host) {
        return Ok(None);
    }
    if host == "host.docker.internal" {
        Ok(Some(host.to_string()))
    } else {
        Ok(None)
    }
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

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_config() -> CubeSandboxConfig {
        CubeSandboxConfig {
            enabled: true,
            api_base_url: "http://127.0.0.1:23000".to_string(),
            data_plane_base_url: "https://127.0.0.1:21443".to_string(),
            template_id: "tpl-test".to_string(),
            helper_path: "/app/scripts/cubesandbox-quickstart.sh".to_string(),
            work_dir: ".cubesandbox".to_string(),
            auto_start: true,
            auto_install: true,
            helper_timeout_seconds: 600,
            execution_timeout_seconds: 120,
            sandbox_cleanup_timeout_seconds: 30,
            stdout_limit_bytes: 65_536,
            stderr_limit_bytes: 65_536,
        }
    }

    #[test]
    fn helper_command_round_trip_covers_codeql_cpp_chain() {
        let cases = [
            ("doctor", CubeSandboxHelperCommand::Doctor),
            ("status", CubeSandboxHelperCommand::Status),
            (
                "run-vm-background",
                CubeSandboxHelperCommand::RunVmBackground,
            ),
            ("install", CubeSandboxHelperCommand::Install),
            ("create-template", CubeSandboxHelperCommand::CreateTemplate),
            ("watch-template", CubeSandboxHelperCommand::WatchTemplate),
            (
                "configure-docker-mirror",
                CubeSandboxHelperCommand::ConfigureDockerMirror,
            ),
            (
                "start-local-registry",
                CubeSandboxHelperCommand::StartLocalRegistry,
            ),
            (
                "build-codeql-cpp-image",
                CubeSandboxHelperCommand::BuildCodeqlCppImage,
            ),
            (
                "create-codeql-cpp-template",
                CubeSandboxHelperCommand::CreateCodeqlCppTemplate,
            ),
            (
                "provision-codeql-cpp-template",
                CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
            ),
        ];
        for (text, variant) in cases {
            assert_eq!(variant.as_str(), text);
            assert_eq!(CubeSandboxHelperCommand::try_from(text).unwrap(), variant);
            assert_eq!(text.parse::<CubeSandboxHelperCommand>().unwrap(), variant);
        }
    }

    #[test]
    fn build_helper_invocation_includes_codeql_cpp_commands() {
        let config = sample_config();
        for variant in [
            CubeSandboxHelperCommand::ConfigureDockerMirror,
            CubeSandboxHelperCommand::StartLocalRegistry,
            CubeSandboxHelperCommand::BuildCodeqlCppImage,
            CubeSandboxHelperCommand::CreateCodeqlCppTemplate,
            CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
        ] {
            let invocation = build_helper_invocation(&config, variant).expect("should build");
            assert_eq!(invocation.command, config.helper_path);
            assert_eq!(invocation.args, vec![variant.as_str().to_string()]);
            assert_eq!(invocation.env.get("CUBE_WORK_DIR"), Some(&config.work_dir));
            assert_eq!(
                invocation.env.get("CUBE_TEMPLATE_ID"),
                Some(&config.template_id)
            );
            assert_eq!(
                invocation.env.get("CUBE_API_PORT"),
                Some(&"23000".to_string())
            );
            assert_eq!(
                invocation.env.get("CUBE_PROXY_HTTPS_PORT"),
                Some(&"21443".to_string())
            );
        }
    }

    #[test]
    fn unknown_helper_command_rejected() {
        assert!(CubeSandboxHelperCommand::try_from("nope").is_err());
    }

    #[test]
    fn build_helper_invocation_injects_cube_ssh_host_for_host_docker_internal() {
        let mut config = sample_config();
        config.api_base_url = "http://host.docker.internal:23000".to_string();
        config.data_plane_base_url = "https://host.docker.internal:21443".to_string();
        let invocation = build_helper_invocation(
            &config,
            CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
        )
        .expect("should build");
        assert_eq!(
            invocation.env.get("CUBE_SSH_HOST"),
            Some(&"host.docker.internal".to_string())
        );
        assert_eq!(
            invocation.env.get("CUBE_API_PORT"),
            Some(&"23000".to_string())
        );
    }

    #[test]
    fn build_helper_invocation_omits_ssh_host_for_localhost() {
        let config = sample_config();
        let invocation = build_helper_invocation(
            &config,
            CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
        )
        .expect("should build");
        assert!(invocation.env.get("CUBE_SSH_HOST").is_none());
    }

    #[test]
    fn lifecycle_check_rejects_remote_hosts() {
        let mut config = sample_config();
        config.api_base_url = "http://example.com:23000".to_string();
        let result = build_helper_invocation(
            &config,
            CubeSandboxHelperCommand::ProvisionCodeqlCppTemplate,
        );
        assert!(result.is_err());
    }
}
