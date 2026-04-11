use anyhow::Result;
use serde_json::json;

use crate::{
    db::system_config,
    state::{AppState, BootstrapStatus, StartupInitStatus},
};

pub async fn run(state: &AppState, rust_db_ready: bool) -> Result<StartupInitStatus> {
    if !state.config.startup_init_enabled {
        return Ok(StartupInitStatus {
            status: "skipped".to_string(),
            actions: Vec::new(),
            error: None,
        });
    }

    if state.db_pool.is_none() {
        return Ok(StartupInitStatus {
            status: "skipped".to_string(),
            actions: vec!["file-mode startup init skipped".to_string()],
            error: None,
        });
    }

    if !rust_db_ready {
        return Ok(StartupInitStatus {
            status: "skipped".to_string(),
            actions: vec!["database not ready for rust startup init".to_string()],
            error: None,
        });
    }

    let mut actions = Vec::new();
    if system_config::load_current(state).await?.is_none() {
        system_config::save_current(state, json!({}), json!({})).await?;
        actions.push("created default rust system config".to_string());
    } else {
        actions.push("default rust system config already present".to_string());
    }

    Ok(StartupInitStatus {
        status: BootstrapStatus::Ok.as_str().to_string(),
        actions,
        error: None,
    })
}
