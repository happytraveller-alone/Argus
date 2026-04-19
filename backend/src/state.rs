use std::sync::Arc;

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, postgres::PgPoolOptions};
use tokio::sync::{Mutex, RwLock};

use crate::{config::AppConfig, project_file_cache::ProjectFileCache};

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
    pub checked_tables: Vec<String>,
    pub missing_tables: Vec<String>,
    pub error: Option<String>,
}

impl DatabaseBootstrapStatus {
    pub fn file_mode() -> Self {
        Self {
            mode: "file".to_string(),
            status: "skipped".to_string(),
            checked_tables: Vec::new(),
            missing_tables: Vec::new(),
            error: None,
        }
    }

    pub fn db_mode() -> Self {
        Self {
            mode: "db".to_string(),
            status: BootstrapStatus::NotRun.as_str().to_string(),
            checked_tables: Vec::new(),
            missing_tables: Vec::new(),
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StartupInitPolicy {
    pub allowed_at_startup: Vec<String>,
    pub forbidden_at_startup: Vec<String>,
    pub deferred_until_rust_owned: Vec<String>,
}

impl Default for StartupInitPolicy {
    fn default() -> Self {
        Self {
            allowed_at_startup: Vec::new(),
            forbidden_at_startup: Vec::new(),
            deferred_until_rust_owned: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StartupInitStatus {
    pub status: String,
    pub policy: StartupInitPolicy,
    pub actions: Vec<String>,
    pub error: Option<String>,
}

impl Default for StartupInitStatus {
    fn default() -> Self {
        Self {
            status: BootstrapStatus::NotRun.as_str().to_string(),
            policy: StartupInitPolicy::default(),
            actions: Vec::new(),
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RecoveryTaskStatus {
    pub name: String,
    pub table_present: bool,
    pub recovered: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StartupRecoveryStatus {
    pub status: String,
    pub tasks: Vec<RecoveryTaskStatus>,
    pub error: Option<String>,
}

impl Default for StartupRecoveryStatus {
    fn default() -> Self {
        Self {
            status: BootstrapStatus::NotRun.as_str().to_string(),
            tasks: Vec::new(),
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunnerPreflightCheckStatus {
    pub name: String,
    pub success: bool,
    pub exit_code: Option<i32>,
    pub error: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunnerPreflightStatus {
    pub status: String,
    pub enabled: bool,
    pub strict: bool,
    pub checks: Vec<RunnerPreflightCheckStatus>,
    pub error: Option<String>,
}

impl Default for RunnerPreflightStatus {
    fn default() -> Self {
        Self {
            status: BootstrapStatus::NotRun.as_str().to_string(),
            enabled: false,
            strict: false,
            checks: Vec::new(),
            error: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BootstrapReport {
    pub overall: String,
    pub file_store: FileStoreBootstrapStatus,
    pub database: DatabaseBootstrapStatus,
    pub init: StartupInitStatus,
    pub recovery: StartupRecoveryStatus,
    pub preflight: RunnerPreflightStatus,
}

impl BootstrapReport {
    pub fn new() -> Self {
        Self {
            overall: BootstrapStatus::Ok.as_str().to_string(),
            file_store: FileStoreBootstrapStatus::default(),
            database: DatabaseBootstrapStatus::file_mode(),
            init: StartupInitStatus::default(),
            recovery: StartupRecoveryStatus::default(),
            preflight: RunnerPreflightStatus::default(),
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

#[derive(Clone, Debug, PartialEq)]
pub struct ScanRuleAsset {
    pub engine: String,
    pub source_kind: String,
    pub asset_path: String,
    pub file_format: String,
    pub sha256: String,
    pub content: String,
    pub metadata_json: serde_json::Value,
}

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>,
    pub http_client: Client,
    pub db_pool: Option<PgPool>,
    pub file_store_lock: Arc<Mutex<()>>,
    pub project_file_cache: Arc<Mutex<ProjectFileCache>>,
    pub bootstrap: Arc<RwLock<BootstrapReport>>,
}

impl AppState {
    pub async fn from_config(config: AppConfig) -> Result<Self> {
        let http_client = Client::builder().build()?;
        let rust_database_url = config.resolved_rust_database_url();
        let db_pool = rust_database_url
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
            project_file_cache: Arc::new(Mutex::new(ProjectFileCache::new())),
            bootstrap: Arc::new(RwLock::new(BootstrapReport {
                overall: BootstrapStatus::NotRun.as_str().to_string(),
                file_store: FileStoreBootstrapStatus::default(),
                database: DatabaseBootstrapStatus {
                    mode: "unknown".to_string(),
                    status: BootstrapStatus::NotRun.as_str().to_string(),
                    checked_tables: Vec::new(),
                    missing_tables: Vec::new(),
                    error: None,
                },
                init: StartupInitStatus::default(),
                recovery: StartupRecoveryStatus::default(),
                preflight: RunnerPreflightStatus::default(),
            })),
        })
    }

    pub async fn set_bootstrap(&self, report: BootstrapReport) {
        let mut guard = self.bootstrap.write().await;
        *guard = report;
    }
}
