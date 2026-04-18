use anyhow::Result;
use serde_json::json;

use crate::{
    bootstrap::legacy_mirror_schema,
    db::{projects, prompt_skills, scan_rule_assets, system_config},
    state::{AppState, BootstrapStatus, StartupInitPolicy, StartupInitStatus},
};

fn startup_init_policy() -> StartupInitPolicy {
    StartupInitPolicy {
        allowed_at_startup: vec![
            "default_rust_system_config".to_string(),
            "empty_rust_project_store".to_string(),
            "rust_prompt_skill_compat_backfill".to_string(),
            "rust_scan_rule_asset_sync".to_string(),
            "legacy_control_plane_mirror_schema_sync".to_string(),
        ],
        forbidden_at_startup: vec![
            "demo_user_bootstrap".to_string(),
            "demo_project_seed".to_string(),
            "legacy_user_table_mutation".to_string(),
            "legacy_project_seed_download".to_string(),
            "legacy_rule_table_import".to_string(),
            "legacy_prompt_template_seed".to_string(),
        ],
        deferred_until_rust_owned: vec![
            "agent_task_seed_data".to_string(),
            "static_scan_task_seed_data".to_string(),
            "legacy_rule_projection_tables".to_string(),
            "legacy_prompt_template_projection".to_string(),
            "seed_project_archive_download".to_string(),
            "legacy_user_config_backfill".to_string(),
        ],
    }
}

pub async fn run(state: &AppState, rust_db_ready: bool) -> Result<StartupInitStatus> {
    if !state.config.startup_init_enabled {
        return Ok(StartupInitStatus {
            status: "skipped".to_string(),
            policy: startup_init_policy(),
            actions: Vec::new(),
            error: None,
        });
    }

    if state.db_pool.is_some() && !rust_db_ready {
        return Ok(StartupInitStatus {
            status: "skipped".to_string(),
            policy: startup_init_policy(),
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

    if projects::ensure_initialized(state).await? {
        actions.push("created empty rust project store".to_string());
    } else {
        actions.push("rust project store already present".to_string());
    }

    if state.db_pool.is_some() {
        let ensured = legacy_mirror_schema::ensure_initialized(
            state.db_pool.as_ref().expect("db pool checked"),
        )
        .await?;
        actions.push(format!(
            "legacy control-plane mirror schema synced: {}",
            ensured.join(", ")
        ));

        let backfill = prompt_skills::compat_backfill_from_legacy_if_empty(
            state,
            &[
                "recon",
                "business_logic_recon",
                "analysis",
                "business_logic_analysis",
                "verification",
            ],
        )
        .await?;
        actions.push(format!(
            "prompt skill compat backfill: imported_custom={} imported_builtin_state={}",
            backfill.imported_prompt_skill_count, backfill.imported_builtin_state_count
        ));

        let summary = scan_rule_assets::ensure_initialized(state).await?;
        actions.push(format!(
            "scan rule assets synced: discovered={} inserted={} updated={} skipped={}",
            summary.discovered, summary.inserted, summary.updated, summary.skipped
        ));
    } else {
        actions.push("scan rule asset import skipped without rust db".to_string());
    }

    Ok(StartupInitStatus {
        status: BootstrapStatus::Ok.as_str().to_string(),
        policy: startup_init_policy(),
        actions,
        error: None,
    })
}

#[cfg(test)]
mod tests {
    use super::startup_init_policy;
    use crate::bootstrap::legacy_mirror_schema;

    #[test]
    fn startup_policy_allows_only_rust_control_plane_seeds() {
        let policy = startup_init_policy();
        assert_eq!(
            policy.allowed_at_startup,
            vec![
                "default_rust_system_config",
                "empty_rust_project_store",
                "rust_prompt_skill_compat_backfill",
                "rust_scan_rule_asset_sync",
                "legacy_control_plane_mirror_schema_sync"
            ]
        );
        assert!(policy
            .forbidden_at_startup
            .contains(&"demo_user_bootstrap".to_string()));
        assert!(policy
            .forbidden_at_startup
            .contains(&"legacy_prompt_template_seed".to_string()));
        assert!(policy
            .deferred_until_rust_owned
            .contains(&"agent_task_seed_data".to_string()));
        assert!(policy
            .deferred_until_rust_owned
            .contains(&"legacy_rule_projection_tables".to_string()));
    }

    #[test]
    fn legacy_mirror_schema_specs_cover_current_rust_owned_bridges() {
        assert_eq!(
            legacy_mirror_schema::ensured_table_names(),
            vec![
                "users",
                "user_configs",
                "projects",
                "project_info",
                "project_management_metrics",
                "prompt_skills",
            ]
        );
    }
}
