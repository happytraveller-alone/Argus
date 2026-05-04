use anyhow::{bail, Result};
use reqwest::Url;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    config::AppConfig,
    db::{cubesandbox_templates::TemplateKind, system_config},
    state::AppState,
};

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
    /// Base URL of the CubeMaster control-plane service used to delete templates
    /// on provision failure. Sourced from env `CUBE_MASTER_BASE_URL`; if unset,
    /// defaults to `api_base_url` because CubeMaster and CubeAPI share the same
    /// host/port (http://127.0.0.1:23000) in the default single-node deployment.
    pub cubemaster_base_url: String,
    /// Timeout in seconds for cubemaster template-deletion HTTP requests.
    pub cubemaster_cleanup_timeout_seconds: u64,
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
            // Default: same host as api_base_url (CubeMaster co-located with CubeAPI on port 23000).
            // Override with CUBE_MASTER_BASE_URL env var or system_config JSON if deployed
            // separately. AppConfig holds the env-resolved value; an empty string means
            // "fall back to api_base_url".
            cubemaster_base_url: if config.cubesandbox_cubemaster_base_url.trim().is_empty() {
                config.cubesandbox_api_base_url.clone()
            } else {
                config.cubesandbox_cubemaster_base_url.clone()
            },
            cubemaster_cleanup_timeout_seconds: config
                .cubesandbox_cubemaster_cleanup_timeout_seconds,
        }
    }

    pub fn for_template_kind(&self, kind: TemplateKind, app_config: &AppConfig) -> Self {
        let mut next = self.clone();
        // Exhaustive match: adding a new TemplateKind variant becomes a compile
        // error here, forcing the author to decide which template_id to thread.
        match kind {
            TemplateKind::CodeqlCpp => {
                // The default `template_id` already carries the codeql template;
                // no override needed.
            }
            TemplateKind::Opengrep => {
                next.template_id = app_config
                    .cubesandbox_opengrep_template_id
                    .trim()
                    .to_string();
            }
            TemplateKind::OpengrepDedicated => {
                next.template_id = app_config
                    .cubesandbox_opengrep_template_id
                    .trim()
                    .to_string();
            }
        }
        next
    }

    pub async fn load_runtime(state: &AppState) -> Result<Self> {
        let stored = system_config::load_current(state).await?;
        let defaults = Self::defaults(state.config.as_ref());
        let Some(stored) = stored else {
            return Ok(defaults);
        };
        Ok(defaults.merge_json(stored.other_config_json.get("cubeSandbox")))
    }

    /// Validate the runtime CubeSandbox configuration excluding `template_id`.
    ///
    /// `template_id` is intentionally not enforced here: when empty, the backend
    /// auto-provisions a template via the provisioner state machine. Callers
    /// that need a concrete template id must resolve it through the provisioner.
    pub fn validate_for_execution(&self) -> Result<()> {
        if !self.enabled {
            bail!("CubeSandbox 未启用：请前往「系统配置 -> CubeSandbox」开启后再运行 CodeQL 扫描");
        }
        if self.api_base_url.trim().is_empty() {
            bail!("CubeSandbox apiBaseUrl 未配置：请在「系统配置 -> CubeSandbox -> API Base URL」填写完整 http(s) 地址");
        }
        if self.data_plane_base_url.trim().is_empty() {
            bail!("CubeSandbox dataPlaneBaseUrl 未配置：请在「系统配置 -> CubeSandbox -> Data Plane Base URL」填写完整 http(s) 地址");
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
        if let Some(value) = read_string(map.get("workDir")) {
            self.work_dir = value;
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
        if let Some(value) = read_string(map.get("cubemasterBaseUrl")) {
            self.cubemaster_base_url = value;
        }
        if let Some(value) = read_u64(map.get("cubemasterCleanupTimeoutSeconds")) {
            self.cubemaster_cleanup_timeout_seconds = value;
        }
        self
    }

    pub fn to_public_json(&self) -> Value {
        serde_json::json!({
            "enabled": self.enabled,
            "apiBaseUrl": self.api_base_url,
            "dataPlaneBaseUrl": self.data_plane_base_url,
            "workDir": self.work_dir,
            "autoInstall": self.auto_install,
            "helperTimeoutSeconds": self.helper_timeout_seconds,
            "executionTimeoutSeconds": self.execution_timeout_seconds,
            "sandboxCleanupTimeoutSeconds": self.sandbox_cleanup_timeout_seconds,
            "stdoutLimitBytes": self.stdout_limit_bytes,
            "stderrLimitBytes": self.stderr_limit_bytes,
            "cubemasterBaseUrl": self.cubemaster_base_url,
            "cubemasterCleanupTimeoutSeconds": self.cubemaster_cleanup_timeout_seconds
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn for_template_kind_preserves_codeql_and_maps_dedicated_opengrep_override() {
        let app_config = AppConfig::for_tests();
        let base = CubeSandboxConfig::defaults(&app_config);

        assert_eq!(
            base.for_template_kind(TemplateKind::CodeqlCpp, &app_config)
                .template_id,
            app_config.cubesandbox_template_id
        );
        assert_eq!(
            base.for_template_kind(TemplateKind::current_opengrep(), &app_config)
                .template_id,
            app_config.cubesandbox_opengrep_template_id
        );
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
