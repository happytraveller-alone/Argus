use std::sync::Arc;

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sqlx::{postgres::PgPoolOptions, PgPool};
use tokio::sync::{Mutex, RwLock};

use crate::config::AppConfig;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum BootstrapStatus {
    NotRun,
    Ok,
    Degraded,
    Error,
}

impl BootstrapStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::NotRun => "not_run",
            Self::Ok => "ok",
            Self::Degraded => "degraded",
            Self::Error => "error",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FileStoreBootstrapStatus {
    pub status: String,
    pub root: String,
    pub error: Option<String>,
}

impl Default for FileStoreBootstrapStatus {
    fn default() -> Self {
        Self {
            status: BootstrapStatus::NotRun.as_str().to_string(),
            root: String::new(),
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DatabaseBootstrapStatus {
    pub mode: String,
    pub status: String,
    pub alembic_version_table: Option<bool>,
    pub alembic_version: Option<String>,
    pub error: Option<String>,
}

impl DatabaseBootstrapStatus {
    pub fn file_mode() -> Self {
        Self {
            mode: "file".to_string(),
            status: "skipped".to_string(),
            alembic_version_table: None,
            alembic_version: None,
            error: None,
        }
    }

    pub fn db_mode() -> Self {
        Self {
            mode: "db".to_string(),
            status: BootstrapStatus::NotRun.as_str().to_string(),
            alembic_version_table: None,
            alembic_version: None,
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BootstrapReport {
    pub overall: String,
    pub file_store: FileStoreBootstrapStatus,
    pub database: DatabaseBootstrapStatus,
}

impl BootstrapReport {
    pub fn new() -> Self {
        Self {
            overall: BootstrapStatus::Ok.as_str().to_string(),
            file_store: FileStoreBootstrapStatus::default(),
            database: DatabaseBootstrapStatus::file_mode(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StoredSystemConfig {
    pub llm_config_json: serde_json::Value,
    pub other_config_json: serde_json::Value,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StoredProject {
    pub id: String,
    pub name: String,
    pub description: String,
    pub source_type: String,
    pub repository_type: String,
    pub default_branch: String,
    pub programming_languages_json: String,
    pub is_active: bool,
    pub created_at: String,
    pub updated_at: String,
    pub language_info: String,
    pub info_status: String,
    pub archive: Option<StoredProjectArchive>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StoredProjectArchive {
    pub original_filename: String,
    pub storage_path: String,
    pub sha256: String,
    pub file_size: i64,
    pub uploaded_at: String,
}

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>,
    pub http_client: Client,
    pub db_pool: Option<PgPool>,
    pub file_store_lock: Arc<Mutex<()>>,
    pub bootstrap: Arc<RwLock<BootstrapReport>>,
}

impl AppState {
    pub async fn from_config(config: AppConfig) -> Result<Self> {
        let http_client = Client::builder().build()?;
        let db_pool = config
            .database_url
            .as_ref()
            .map(|database_url| {
                PgPoolOptions::new()
                    .max_connections(5)
                    .connect_lazy(database_url)
            })
            .transpose()?;

        Ok(Self {
            config: Arc::new(config),
            http_client,
            db_pool,
            file_store_lock: Arc::new(Mutex::new(())),
            bootstrap: Arc::new(RwLock::new(BootstrapReport {
                overall: BootstrapStatus::NotRun.as_str().to_string(),
                file_store: FileStoreBootstrapStatus::default(),
                database: DatabaseBootstrapStatus {
                    mode: "unknown".to_string(),
                    status: BootstrapStatus::NotRun.as_str().to_string(),
                    alembic_version_table: None,
                    alembic_version: None,
                    error: None,
                },
            })),
        })
    }

    pub async fn set_bootstrap(&self, report: BootstrapReport) {
        let mut guard = self.bootstrap.write().await;
        *guard = report;
    }
}
