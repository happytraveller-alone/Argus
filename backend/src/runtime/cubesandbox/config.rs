use anyhow::{bail, Result};
use reqwest::Url;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{config::AppConfig, db::system_config, state::AppState};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CubeSandboxConfig {
    pub enabled: bool,
    pub api_base_url: String,
    pub data_plane_base_url: String,
    pub template_id: String,
    pub helper_path: String,
    pub work_dir: String,
    pub auto_start: bool,
    pub auto_install: bool,
    pub helper_timeout_seconds: u64,
    pub execution_timeout_seconds: u64,
    pub sandbox_cleanup_timeout_seconds: u64,
    pub stdout_limit_bytes: usize,
    pub stderr_limit_bytes: usize,
}

impl CubeSandboxConfig {
    pub fn defaults(config: &AppConfig) -> Self {
        Self {
            enabled: config.cubesandbox_enabled,
            api_base_url: config.cubesandbox_api_base_url.clone(),
            data_plane_base_url: config.cubesandbox_data_plane_base_url.clone(),
            template_id: config.cubesandbox_template_id.clone(),
            helper_path: config.cubesandbox_helper_path.clone(),
            work_dir: config.cubesandbox_work_dir.clone(),
            auto_start: config.cubesandbox_auto_start,
            auto_install: config.cubesandbox_auto_install,
            helper_timeout_seconds: config.cubesandbox_helper_timeout_seconds,
            execution_timeout_seconds: config.cubesandbox_execution_timeout_seconds,
            sandbox_cleanup_timeout_seconds: config.cubesandbox_cleanup_timeout_seconds,
            stdout_limit_bytes: config.cubesandbox_stdout_limit_bytes,
            stderr_limit_bytes: config.cubesandbox_stderr_limit_bytes,
        }
    }

    pub async fn load_runtime(state: &AppState) -> Result<Self> {
        let stored = system_config::load_current(state).await?;
        let defaults = Self::defaults(state.config.as_ref());
        let Some(stored) = stored else {
            return Ok(defaults);
        };
        Ok(defaults.merge_json(stored.other_config_json.get("cubeSandbox")))
    }

    pub fn validate_for_execution(&self) -> Result<()> {
        if !self.enabled {
            bail!("CubeSandbox is disabled in system config");
        }
        if self.template_id.trim().is_empty() {
            bail!("CubeSandbox templateId is required");
        }
        parse_url(&self.api_base_url, "apiBaseUrl")?;
        parse_url(&self.data_plane_base_url, "dataPlaneBaseUrl")?;
        Ok(())
    }

    fn merge_json(mut self, value: Option<&Value>) -> Self {
        let Some(Value::Object(map)) = value else {
            return self;
        };
        if let Some(value) = map.get("enabled").and_then(Value::as_bool) {
            self.enabled = value;
        }
        if let Some(value) = read_string(map.get("apiBaseUrl")) {
            self.api_base_url = value;
        }
        if let Some(value) = read_string(map.get("dataPlaneBaseUrl")) {
            self.data_plane_base_url = value;
        }
        if let Some(value) = read_string(map.get("templateId")) {
            self.template_id = value;
        }
        if let Some(value) = read_string(map.get("helperPath")) {
            self.helper_path = value;
        }
        if let Some(value) = read_string(map.get("workDir")) {
            self.work_dir = value;
        }
        if let Some(value) = map.get("autoStart").and_then(Value::as_bool) {
            self.auto_start = value;
        }
        if let Some(value) = map.get("autoInstall").and_then(Value::as_bool) {
            self.auto_install = value;
        }
        if let Some(value) = read_u64(map.get("helperTimeoutSeconds")) {
            self.helper_timeout_seconds = value;
        }
        if let Some(value) = read_u64(map.get("executionTimeoutSeconds")) {
            self.execution_timeout_seconds = value;
        }
        if let Some(value) = read_u64(map.get("sandboxCleanupTimeoutSeconds")) {
            self.sandbox_cleanup_timeout_seconds = value;
        }
        if let Some(value) = read_usize(map.get("stdoutLimitBytes")) {
            self.stdout_limit_bytes = value;
        }
        if let Some(value) = read_usize(map.get("stderrLimitBytes")) {
            self.stderr_limit_bytes = value;
        }
        self
    }

    pub fn to_public_json(&self) -> Value {
        serde_json::json!({
            "enabled": self.enabled,
            "apiBaseUrl": self.api_base_url,
            "dataPlaneBaseUrl": self.data_plane_base_url,
            "templateId": self.template_id,
            "helperPath": self.helper_path,
            "workDir": self.work_dir,
            "autoStart": self.auto_start,
            "autoInstall": self.auto_install,
            "helperTimeoutSeconds": self.helper_timeout_seconds,
            "executionTimeoutSeconds": self.execution_timeout_seconds,
            "sandboxCleanupTimeoutSeconds": self.sandbox_cleanup_timeout_seconds,
            "stdoutLimitBytes": self.stdout_limit_bytes,
            "stderrLimitBytes": self.stderr_limit_bytes
        })
    }
}

pub fn parse_url(value: &str, label: &str) -> Result<Url> {
    let parsed =
        Url::parse(value).map_err(|error| anyhow::anyhow!("{label} is invalid: {error}"))?;
    match parsed.scheme() {
        "http" | "https" if parsed.has_host() => Ok(parsed),
        _ => bail!("{label} must be an absolute http(s) URL"),
    }
}

fn read_string(value: Option<&Value>) -> Option<String> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn read_u64(value: Option<&Value>) -> Option<u64> {
    value.and_then(Value::as_u64)
}

fn read_usize(value: Option<&Value>) -> Option<usize> {
    value
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
}
