use std::sync::Arc;

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sqlx::{postgres::PgPoolOptions, PgPool};
use tokio::sync::Mutex;

use crate::config::AppConfig;

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
        })
    }
}
