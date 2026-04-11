use std::{env, net::SocketAddr, path::PathBuf, str::FromStr};

use anyhow::{Context, Result};

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub bind_addr: SocketAddr,
    pub database_url: Option<String>,
    pub python_upstream_base_url: Option<String>,
    pub zip_storage_path: PathBuf,
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
        })
    }

    pub fn for_tests() -> Self {
        Self {
            bind_addr: SocketAddr::from(([127, 0, 0, 1], 0)),
            database_url: None,
            python_upstream_base_url: None,
            zip_storage_path: PathBuf::from("./tmp/test-zips"),
        }
    }

    pub fn with_python_upstream(mut self, python_upstream_base_url: impl Into<String>) -> Self {
        self.python_upstream_base_url = Some(python_upstream_base_url.into());
        self
    }
}
