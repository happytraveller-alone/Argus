use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde_json::Value;
use tokio::fs;

use crate::{db::scan_rule_assets, state::AppState};

const BANDIT_ASSET_PATH: &str = "bandit_builtin/bandit_builtin_rules.json";
const BANDIT_ASSET_ENGINE: &str = "bandit";
const BANDIT_ASSET_SOURCE_KIND: &str = "builtin";

pub async fn load_builtin_snapshot(state: &AppState) -> Result<Option<Value>> {
    let Some(content) = scan_rule_assets::load_asset_content(
        state,
        BANDIT_ASSET_ENGINE,
        BANDIT_ASSET_SOURCE_KIND,
        BANDIT_ASSET_PATH,
    )
    .await? else {
        return Ok(None);
    };

    let payload = serde_json::from_str::<Value>(&content)
        .with_context(|| "failed to parse bandit builtin snapshot".to_string())?;
    Ok(Some(payload))
}

pub async fn materialize_builtin_snapshot(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<Option<PathBuf>> {
    let Some(content) = scan_rule_assets::load_asset_content(
        state,
        BANDIT_ASSET_ENGINE,
        BANDIT_ASSET_SOURCE_KIND,
        BANDIT_ASSET_PATH,
    )
    .await? else {
        return Ok(None);
    };

    fs::create_dir_all(workspace_dir).await?;
    let snapshot_path = workspace_dir.join("bandit-rules.json");
    fs::write(&snapshot_path, content).await?;
    Ok(Some(snapshot_path))
}

pub fn select_preflight_test_ids(snapshot: &Value, limit: usize) -> Vec<String> {
    snapshot
        .get("rules")
        .and_then(|rules| rules.as_array())
        .into_iter()
        .flatten()
        .filter_map(|rule| rule.get("test_id").and_then(|value| value.as_str()))
        .take(limit.max(1))
        .map(|value| value.to_string())
        .collect()
}

pub fn build_scan_command(source_dir: &str, report_path: &str, test_ids: &[String]) -> Vec<String> {
    let mut command = vec![
        "bandit".to_string(),
        "-r".to_string(),
        source_dir.to_string(),
        "-f".to_string(),
        "json".to_string(),
        "-o".to_string(),
        report_path.to_string(),
    ];
    if !test_ids.is_empty() {
        command.push("-t".to_string());
        command.push(test_ids.join(","));
    }
    command
}

#[cfg(test)]
mod tests {
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{build_scan_command, load_builtin_snapshot, materialize_builtin_snapshot, select_preflight_test_ids};

    #[tokio::test]
    async fn loads_bandit_builtin_snapshot_from_rule_assets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let snapshot = load_builtin_snapshot(&state)
            .await
            .expect("snapshot should load")
            .expect("bandit snapshot should exist");
        assert_eq!(snapshot["schema_version"], "1.0");
        assert!(snapshot["rules"].as_array().map(|rules| rules.len()).unwrap_or_default() > 10);
    }

    #[tokio::test]
    async fn materializes_bandit_snapshot_to_workspace() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace = std::env::temp_dir().join(format!("bandit-materialize-{}", uuid::Uuid::new_v4()));
        let path = materialize_builtin_snapshot(&state, &workspace)
            .await
            .expect("materialize should succeed")
            .expect("snapshot path should exist");
        let content = fs::read_to_string(&path).await.expect("snapshot should be readable");
        assert!(content.contains("\"test_id\": \"B101\""));
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn selects_preflight_test_ids_and_builds_command() {
        let snapshot = serde_json::json!({
            "rules": [
                {"test_id": "B101"},
                {"test_id": "B102"},
                {"test_id": "B103"}
            ]
        });
        let selected = select_preflight_test_ids(&snapshot, 2);
        assert_eq!(selected, vec!["B101", "B102"]);
        assert_eq!(
            build_scan_command("/work/source", "/work/report.json", &selected),
            vec![
                "bandit",
                "-r",
                "/work/source",
                "-f",
                "json",
                "-o",
                "/work/report.json",
                "-t",
                "B101,B102"
            ]
        );
    }
}
