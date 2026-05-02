use std::time::Duration;

use anyhow::{bail, Result};
use reqwest::{header::HOST, Client, StatusCode, Url};
use serde::{Deserialize, Serialize};
use serde_json::json;

use super::config::parse_url;

const ENVD_PORT: u16 = 49_983;

#[derive(Clone, Debug)]
pub struct CubeSandboxClientConfig {
    pub api_base_url: String,
    pub data_plane_base_url: String,
    pub template_id: String,
    pub execution_timeout_seconds: u64,
    pub cleanup_timeout_seconds: u64,
    pub stdout_limit_bytes: usize,
    pub stderr_limit_bytes: usize,
}

#[derive(Clone)]
pub struct CubeSandboxClient {
    http_client: Client,
    api_base_url: Url,
    data_plane_base_url: Url,
    config: CubeSandboxClientConfig,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CubeSandboxSandbox {
    #[serde(rename = "sandboxID")]
    pub sandbox_id: String,
    #[serde(rename = "templateID")]
    pub template_id: String,
    #[serde(rename = "clientID")]
    pub client_id: String,
    #[serde(rename = "envdVersion")]
    pub envd_version: String,
    pub domain: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EnvdProcessRequest {
    pub cmd: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EnvdProcessOutput {
    pub stdout: String,
    pub stderr: String,
    pub stdout_truncated: bool,
    pub stderr_truncated: bool,
    pub exit_code: Option<i32>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EnvdProcessResponse {
    #[serde(default)]
    stdout: String,
    #[serde(default)]
    stderr: String,
    #[serde(default, alias = "exit_code")]
    exit_code: Option<i32>,
}

impl CubeSandboxClient {
    pub fn new(config: CubeSandboxClientConfig) -> Result<Self> {
        let api_base_url = parse_url(&config.api_base_url, "apiBaseUrl")?;
        let data_plane_base_url = parse_url(&config.data_plane_base_url, "dataPlaneBaseUrl")?;
        let http_client = Client::builder()
            .timeout(Duration::from_secs(config.execution_timeout_seconds.max(1)))
            .danger_accept_invalid_certs(true)
            .no_proxy()
            .build()?;
        Ok(Self {
            http_client,
            api_base_url,
            data_plane_base_url,
            config,
        })
    }

    pub async fn health(&self) -> Result<()> {
        let response = self
            .http_client
            .get(self.join_api("health")?)
            .send()
            .await?;
        if response.status().is_success() {
            Ok(())
        } else {
            bail!("CubeSandbox API health failed: {}", response.status())
        }
    }

    pub async fn create_sandbox(&self) -> Result<CubeSandboxSandbox> {
        let response = self
            .http_client
            .post(self.join_api("sandboxes")?)
            .json(&json!({
                "templateID": self.config.template_id,
                "timeout": self.config.execution_timeout_seconds
            }))
            .send()
            .await?;
        if !response.status().is_success() {
            bail!("CubeSandbox create failed: {}", response.status());
        }
        Ok(response.json().await?)
    }

    pub async fn connect_sandbox(&self, sandbox_id: &str) -> Result<()> {
        let response = self
            .http_client
            .post(self.join_api(&format!("sandboxes/{sandbox_id}/connect"))?)
            .json(&json!({
                "timeout": self.config.execution_timeout_seconds
            }))
            .send()
            .await?;
        if response.status().is_success() {
            Ok(())
        } else {
            bail!("CubeSandbox connect failed: {}", response.status())
        }
    }

    pub async fn get_sandbox(&self, sandbox_id: &str) -> Result<CubeSandboxSandbox> {
        let response = self
            .http_client
            .get(self.join_api(&format!("sandboxes/{sandbox_id}"))?)
            .send()
            .await?;
        if !response.status().is_success() {
            bail!("CubeSandbox diagnostics failed: {}", response.status());
        }
        Ok(response.json().await?)
    }

    pub async fn delete_sandbox(&self, sandbox_id: &str) -> Result<()> {
        let response = self
            .http_client
            .delete(self.join_api(&format!("sandboxes/{sandbox_id}"))?)
            .timeout(Duration::from_secs(
                self.config.cleanup_timeout_seconds.max(1),
            ))
            .send()
            .await?;
        if response.status().is_success() || response.status() == StatusCode::NOT_FOUND {
            Ok(())
        } else {
            bail!("CubeSandbox cleanup failed: {}", response.status())
        }
    }

    pub async fn run_python(
        &self,
        sandbox: &CubeSandboxSandbox,
        code: &str,
    ) -> Result<EnvdProcessOutput> {
        self.run_command(sandbox, &format!("python3 -c {}", shell_quote(code)))
            .await
    }

    pub async fn run_command(
        &self,
        sandbox: &CubeSandboxSandbox,
        command: &str,
    ) -> Result<EnvdProcessOutput> {
        let request = EnvdProcessRequest {
            cmd: command.to_string(),
        };
        let response = self
            .http_client
            .post(self.envd_url("process")?)
            .header(
                HOST,
                self.envd_host(&sandbox.sandbox_id, sandbox.domain.as_deref())?,
            )
            .json(&request)
            .send()
            .await?;
        if !response.status().is_success() {
            bail!("CubeSandbox envd process failed: {}", response.status());
        }
        let parsed: EnvdProcessResponse = response.json().await?;
        let (stdout, stdout_truncated) =
            truncate_utf8(parsed.stdout, self.config.stdout_limit_bytes);
        let (stderr, stderr_truncated) =
            truncate_utf8(parsed.stderr, self.config.stderr_limit_bytes);
        Ok(EnvdProcessOutput {
            stdout,
            stderr,
            stdout_truncated,
            stderr_truncated,
            exit_code: parsed.exit_code,
        })
    }

    fn join_api(&self, path: &str) -> Result<Url> {
        Ok(self.api_base_url.join(path)?)
    }

    fn envd_url(&self, tail: &str) -> Result<Url> {
        let tail = tail.trim_start_matches('/');
        Ok(self.data_plane_base_url.join(tail)?)
    }

    fn envd_host(&self, sandbox_id: &str, domain: Option<&str>) -> Result<String> {
        let Some(domain) = domain.filter(|value| !value.trim().is_empty()) else {
            bail!("CubeSandbox response missing sandbox domain");
        };
        Ok(format!("{ENVD_PORT}-{sandbox_id}.{domain}"))
    }
}

fn truncate_utf8(value: String, limit: usize) -> (String, bool) {
    if value.len() <= limit {
        return (value, false);
    }
    let mut end = limit;
    while !value.is_char_boundary(end) {
        end = end.saturating_sub(1);
    }
    (value[..end].to_string(), true)
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}
