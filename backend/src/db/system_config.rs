use anyhow::Result;
use serde_json::{json, Value};
use sqlx::Row;

use crate::state::{AppState, StoredSystemConfig};

const SYSTEM_CONFIG_SINGLETON_ID: &str = "default";

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

    Ok(state.memory_store.system_config.read().await.clone())
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
        *state.memory_store.system_config.write().await = Some(stored.clone());
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
        *state.memory_store.system_config.write().await = None;
    }
    Ok(())
}
