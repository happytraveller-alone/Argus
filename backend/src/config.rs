use std::{env, net::SocketAddr, path::PathBuf, str::FromStr};

use anyhow::{Context, Result};

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub bind_addr: SocketAddr,
    pub database_url: Option<String>,
    pub python_upstream_base_url: Option<String>,
    pub zip_storage_path: PathBuf,
    pub startup_init_enabled: bool,
    pub startup_recovery_enabled: bool,
    pub runner_preflight_enabled: bool,
    pub runner_preflight_strict: bool,
    pub runner_preflight_timeout_seconds: u64,
    pub runner_preflight_max_concurrency: usize,
    pub scanner_yasa_image: String,
    pub scanner_opengrep_image: String,
    pub scanner_bandit_image: String,
    pub scanner_gitleaks_image: String,
    pub scanner_phpstan_image: String,
    pub scanner_pmd_image: String,
    pub flow_parser_runner_image: String,
    pub sandbox_runner_image: String,
}

impl AppConfig {
    pub fn from_env() -> Result<Self> {
        let bind_addr = env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:8000".to_string());
        let bind_addr = SocketAddr::from_str(&bind_addr)
            .with_context(|| format!("invalid BIND_ADDR: {bind_addr}"))?;

        Ok(Self {
            bind_addr,
            database_url: env::var("DATABASE_URL")
                .ok()
                .filter(|value| !value.trim().is_empty()),
            python_upstream_base_url: env::var("PYTHON_UPSTREAM_BASE_URL")
                .ok()
                .filter(|value| !value.trim().is_empty()),
            zip_storage_path: env::var("ZIP_STORAGE_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("./uploads/zip_files")),
            startup_init_enabled: parse_bool_env("STARTUP_INIT_ENABLED", true),
            startup_recovery_enabled: parse_bool_env("STARTUP_RECOVERY_ENABLED", true),
            runner_preflight_enabled: parse_bool_env("RUNNER_PREFLIGHT_ENABLED", true),
            runner_preflight_strict: parse_bool_env("RUNNER_PREFLIGHT_STRICT", false),
            runner_preflight_timeout_seconds: parse_u64_env("RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30),
            runner_preflight_max_concurrency: parse_usize_env("RUNNER_PREFLIGHT_MAX_CONCURRENCY", 2),
            scanner_yasa_image: env::var("SCANNER_YASA_IMAGE")
                .unwrap_or_else(|_| "vulhunter/yasa-runner:latest".to_string()),
            scanner_opengrep_image: env::var("SCANNER_OPENGREP_IMAGE")
                .unwrap_or_else(|_| "vulhunter/opengrep-runner:latest".to_string()),
            scanner_bandit_image: env::var("SCANNER_BANDIT_IMAGE")
                .unwrap_or_else(|_| "vulhunter/bandit-runner:latest".to_string()),
            scanner_gitleaks_image: env::var("SCANNER_GITLEAKS_IMAGE")
                .unwrap_or_else(|_| "vulhunter/gitleaks-runner:latest".to_string()),
            scanner_phpstan_image: env::var("SCANNER_PHPSTAN_IMAGE")
                .unwrap_or_else(|_| "vulhunter/phpstan-runner:latest".to_string()),
            scanner_pmd_image: env::var("SCANNER_PMD_IMAGE")
                .unwrap_or_else(|_| "vulhunter/pmd-runner:latest".to_string()),
            flow_parser_runner_image: env::var("FLOW_PARSER_RUNNER_IMAGE")
                .unwrap_or_else(|_| "vulhunter/flow-parser-runner:latest".to_string()),
            sandbox_runner_image: env::var("SANDBOX_RUNNER_IMAGE")
                .unwrap_or_else(|_| "vulhunter/sandbox-runner:latest".to_string()),
        })
    }

    pub fn for_tests() -> Self {
        Self {
            bind_addr: SocketAddr::from(([127, 0, 0, 1], 0)),
            database_url: None,
            python_upstream_base_url: None,
            zip_storage_path: PathBuf::from("./tmp/test-zips"),
            startup_init_enabled: true,
            startup_recovery_enabled: true,
            runner_preflight_enabled: false,
            runner_preflight_strict: false,
            runner_preflight_timeout_seconds: 1,
            runner_preflight_max_concurrency: 1,
            scanner_yasa_image: "vulhunter/yasa-runner:test".to_string(),
            scanner_opengrep_image: "vulhunter/opengrep-runner:test".to_string(),
            scanner_bandit_image: "vulhunter/bandit-runner:test".to_string(),
            scanner_gitleaks_image: "vulhunter/gitleaks-runner:test".to_string(),
            scanner_phpstan_image: "vulhunter/phpstan-runner:test".to_string(),
            scanner_pmd_image: "vulhunter/pmd-runner:test".to_string(),
            flow_parser_runner_image: "vulhunter/flow-parser-runner:test".to_string(),
            sandbox_runner_image: "vulhunter/sandbox-runner:test".to_string(),
        }
    }

    pub fn with_python_upstream(mut self, python_upstream_base_url: impl Into<String>) -> Self {
        self.python_upstream_base_url = Some(python_upstream_base_url.into());
        self
    }
}

fn parse_bool_env(key: &str, default: bool) -> bool {
    env::var(key)
        .ok()
        .map(|value| matches!(value.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(default)
}

fn parse_u64_env(key: &str, default: u64) -> u64 {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

fn parse_usize_env(key: &str, default: usize) -> usize {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}
