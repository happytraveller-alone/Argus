use std::{io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use reqwest::Url;
use serde_json::{json, Value};
use sqlx::Row;
use tokio::fs;

use crate::{
    config::AppConfig,
    llm::{is_supported_protocol_provider, normalize_base_url},
    routes::llm_config_set,
    state::{AppState, StoredSystemConfig},
};

const SYSTEM_CONFIG_SINGLETON_ID: &str = "default";
const SYSTEM_CONFIG_FILE_NAME: &str = "rust-system-config.json";

impl StoredSystemConfig {
    pub fn is_llm_configured(&self, config: &AppConfig) -> bool {
        self.llm_provider(config).is_some()
            && self.llm_api_key(config).is_some()
            && self.llm_base_url(config).is_some()
    }

    pub fn llm_provider(&self, config: &AppConfig) -> Option<String> {
        selected_row(&self.llm_config_json, config).and_then(|row| {
            read_string(&row, "provider").and_then(|value| {
                if is_supported_protocol_provider(&value) {
                    Some(value)
                } else {
                    None
                }
            })
        })
    }

    pub fn llm_api_key(&self, config: &AppConfig) -> Option<String> {
        selected_row(&self.llm_config_json, config).and_then(|row| {
            read_string(&row, "apiKey").and_then(|value| {
                if value.trim().is_empty() {
                    None
                } else {
                    Some(value)
                }
            })
        })
    }

    pub fn llm_base_url(&self, config: &AppConfig) -> Option<Url> {
        selected_row(&self.llm_config_json, config).and_then(|row| {
            read_string(&row, "baseUrl").and_then(|value| parse_absolute_base_url(&value))
        })
    }

    pub fn llm_model_default(&self, config: &AppConfig) -> Option<String> {
        selected_row(&self.llm_config_json, config).and_then(|row| {
            read_string(&row, "model").and_then(|value| {
                if value.trim().is_empty() {
                    None
                } else {
                    Some(value)
                }
            })
        })
    }
}

pub async fn load_current(state: &AppState) -> Result<Option<StoredSystemConfig>> {
    if let Some(pool) = &state.db_pool {
        let row = sqlx::query(
            r#"
            select llm_config_json, other_config_json, llm_test_metadata_json
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
            llm_test_metadata_json: row
                .try_get("llm_test_metadata_json")
                .unwrap_or_else(|_| json!({})),
        }));
    }

    load_current_from_file(state).await
}

pub async fn save_current(
    state: &AppState,
    llm_config_json: Value,
    other_config_json: Value,
    llm_test_metadata_json: Value,
) -> Result<StoredSystemConfig> {
    let stored = StoredSystemConfig {
        llm_config_json,
        other_config_json,
        llm_test_metadata_json,
    };

    if let Some(pool) = &state.db_pool {
        sqlx::query(
            r#"
            insert into system_configs (id, llm_config_json, other_config_json, llm_test_metadata_json)
            values ($1, $2, $3, $4)
            on conflict (id) do update
            set llm_config_json = excluded.llm_config_json,
                other_config_json = excluded.other_config_json,
                llm_test_metadata_json = excluded.llm_test_metadata_json,
                updated_at = now()
            "#,
        )
        .bind(SYSTEM_CONFIG_SINGLETON_ID)
        .bind(&stored.llm_config_json)
        .bind(&stored.other_config_json)
        .bind(&stored.llm_test_metadata_json)
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

fn selected_row(llm_config_json: &Value, config: &AppConfig) -> Option<Value> {
    let (envelope, _) = llm_config_set::normalize_envelope(llm_config_json, config);
    envelope
        .get("rows")
        .and_then(Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .find(|row| row.get("enabled").and_then(Value::as_bool).unwrap_or(true))
                .cloned()
        })
}

fn read_string(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn parse_absolute_base_url(value: &str) -> Option<Url> {
    let normalized = normalize_base_url(value);
    let parsed = Url::parse(&normalized).ok()?;
    match parsed.scheme() {
        "http" | "https" if parsed.has_host() => Some(parsed),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::config::AppConfig;

    #[test]
    fn llm_helpers_read_first_enabled_row_without_requiring_model() {
        let config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [
                    {
                        "id": "disabled",
                        "priority": 1,
                        "enabled": false,
                        "provider": "openai_compatible",
                        "baseUrl": "https://disabled.example/v1",
                        "model": "gpt-disabled",
                        "apiKey": "sk-disabled",
                        "advanced": {}
                    },
                    {
                        "id": "enabled",
                        "priority": 2,
                        "enabled": true,
                        "provider": "anthropic_compatible",
                        "baseUrl": "https://api.anthropic.example/v1/messages",
                        "model": "",
                        "apiKey": "sk-enabled",
                        "advanced": {}
                    }
                ]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };

        assert!(stored.is_llm_configured(&config));
        assert_eq!(
            stored.llm_provider(&config).as_deref(),
            Some("anthropic_compatible")
        );
        assert_eq!(stored.llm_api_key(&config).as_deref(), Some("sk-enabled"));
        assert_eq!(
            stored.llm_base_url(&config).map(|url| url.to_string()),
            Some("https://api.anthropic.example/v1/messages".to_string())
        );
        assert!(stored.llm_model_default(&config).is_none());
    }

    #[test]
    fn llm_helpers_reject_empty_or_malformed_config() {
        let config = AppConfig::for_tests();
        let stored = StoredSystemConfig {
            llm_config_json: json!({
                "schemaVersion": 2,
                "rows": [{
                    "id": "bad",
                    "priority": 1,
                    "enabled": true,
                    "provider": "openai_compatible",
                    "baseUrl": "/relative/v1",
                    "model": "gpt-5",
                    "apiKey": "",
                    "advanced": {}
                }]
            }),
            other_config_json: json!({}),
            llm_test_metadata_json: json!({}),
        };

        assert!(!stored.is_llm_configured(&config));
        assert_eq!(
            stored.llm_provider(&config).as_deref(),
            Some("openai_compatible")
        );
        assert!(stored.llm_api_key(&config).is_none());
        assert!(stored.llm_base_url(&config).is_none());
        assert_eq!(stored.llm_model_default(&config).as_deref(), Some("gpt-5"));
    }
}
