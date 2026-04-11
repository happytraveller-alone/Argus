use std::{io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use serde_json::{json, Value};
use sqlx::Row;
use tokio::fs;

use crate::state::{AppState, StoredSystemConfig};

const SYSTEM_CONFIG_SINGLETON_ID: &str = "default";
const SYSTEM_CONFIG_FILE_NAME: &str = "rust-system-config.json";

pub async fn load_current(state: &AppState) -> Result<Option<StoredSystemConfig>> {
    if let Some(pool) = &state.db_pool {
        let row = sqlx::query(
            r#"
            select llm_config_json, other_config_json
            from system_configs
            where id = $1
            "#,
        )
        .bind(SYSTEM_CONFIG_SINGLETON_ID)
        .fetch_optional(pool)
        .await?;

        return Ok(row.map(|row| StoredSystemConfig {
            llm_config_json: row.try_get("llm_config_json").unwrap_or_else(|_| json!({})),
            other_config_json: row
                .try_get("other_config_json")
                .unwrap_or_else(|_| json!({})),
        }));
    }

    load_current_from_file(state).await
}

pub async fn save_current(
    state: &AppState,
    llm_config_json: Value,
    other_config_json: Value,
) -> Result<StoredSystemConfig> {
    let stored = StoredSystemConfig {
        llm_config_json,
        other_config_json,
    };

    if let Some(pool) = &state.db_pool {
        sqlx::query(
            r#"
            insert into system_configs (id, llm_config_json, other_config_json)
            values ($1, $2, $3)
            on conflict (id) do update
            set llm_config_json = excluded.llm_config_json,
                other_config_json = excluded.other_config_json,
                updated_at = now()
            "#,
        )
        .bind(SYSTEM_CONFIG_SINGLETON_ID)
        .bind(&stored.llm_config_json)
        .bind(&stored.other_config_json)
        .execute(pool)
        .await?;
    } else {
        save_current_to_file(state, &stored).await?;
    }

    Ok(stored)
}

pub async fn clear_current(state: &AppState) -> Result<()> {
    if let Some(pool) = &state.db_pool {
        sqlx::query("delete from system_configs where id = $1")
            .bind(SYSTEM_CONFIG_SINGLETON_ID)
            .execute(pool)
            .await?;
    } else {
        clear_current_file(state).await?;
    }
    Ok(())
}

async fn load_current_from_file(state: &AppState) -> Result<Option<StoredSystemConfig>> {
    let _guard = state.file_store_lock.lock().await;
    let path = system_config_file_path(state);
    let raw = match fs::read_to_string(&path).await {
        Ok(raw) => raw,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let parsed = serde_json::from_str::<StoredSystemConfig>(&raw).with_context(|| {
        format!(
            "failed to parse file-backed system config: {}",
            path.display()
        )
    })?;
    Ok(Some(parsed))
}

async fn save_current_to_file(state: &AppState, stored: &StoredSystemConfig) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    ensure_file_storage_root(state).await?;
    let path = system_config_file_path(state);
    let tmp_path = path.with_extension("tmp");
    let bytes = serde_json::to_vec(stored)?;
    fs::write(&tmp_path, bytes).await?;
    fs::rename(tmp_path, path).await?;
    Ok(())
}

async fn clear_current_file(state: &AppState) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    let path = system_config_file_path(state);
    match fs::remove_file(path).await {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

fn system_config_file_path(state: &AppState) -> PathBuf {
    state.config.zip_storage_path.join(SYSTEM_CONFIG_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<()> {
    fs::create_dir_all(&state.config.zip_storage_path).await?;
    Ok(())
}
