use std::path::{Path, PathBuf};

use anyhow::Result;
use tokio::fs;

use crate::{
    db::scan_rule_assets,
    state::{AppState, ScanRuleAsset},
};

const PHPSTAN_ENGINE: &str = "phpstan";
const PHPSTAN_SOURCE_KIND: &str = "builtin";

pub async fn load_builtin_assets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, PHPSTAN_ENGINE, &[PHPSTAN_SOURCE_KIND]).await
}

pub async fn materialize_rules_directory(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<Option<PathBuf>> {
    let assets = load_builtin_assets(state).await?;
    if assets.is_empty() {
        return Ok(None);
    }

    let rules_dir = workspace_dir.join("phpstan-rules");
    for asset in assets {
        let relative_path = asset
            .asset_path
            .strip_prefix("rules_phpstan/")
            .unwrap_or(asset.asset_path.as_str());
        let target = rules_dir.join(relative_path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).await?;
        }
        fs::write(target, asset.content).await?;
    }

    Ok(Some(rules_dir))
}

pub fn build_preflight_command() -> Vec<String> {
    vec![
        "python3".to_string(),
        "-c".to_string(),
        "from pathlib import Path; import subprocess, sys; snapshot = Path('/work/phpstan-rules/phpstan_rules_combined.json'); sources = Path('/work/phpstan-rules/rule_sources'); assert snapshot.exists(), 'missing phpstan snapshot'; assert sources.exists(), 'missing phpstan rule_sources'; sys.exit(subprocess.run(['php', '/opt/phpstan/phpstan', '--version']).returncode)".to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{build_preflight_command, load_builtin_assets, materialize_rules_directory};

    #[tokio::test]
    async fn loads_phpstan_builtin_assets_from_rule_store() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let assets = load_builtin_assets(&state)
            .await
            .expect("phpstan assets should load");
        assert!(assets.len() >= 6);
        assert!(assets
            .iter()
            .any(|asset| asset.asset_path == "rules_phpstan/phpstan_rules_combined.json"));
        assert!(assets
            .iter()
            .any(|asset| asset.asset_path.contains("rules_phpstan/rule_sources/")));
    }

    #[tokio::test]
    async fn materializes_phpstan_rules_and_sources_directory() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace =
            std::env::temp_dir().join(format!("phpstan-materialize-{}", uuid::Uuid::new_v4()));
        let path = materialize_rules_directory(&state, &workspace)
            .await
            .expect("materialize should succeed")
            .expect("rules directory should exist");

        assert!(path.join("phpstan_rules_combined.json").exists());
        assert!(path
            .join("rule_sources/phpstan-src/src/Rules/Variables/UnsetRule.php")
            .exists());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn builds_preflight_command_that_checks_assets_and_runner() {
        let command = build_preflight_command();
        assert_eq!(command[0], "python3");
        assert!(command[2].contains("phpstan_rules_combined.json"));
        assert!(command[2].contains("rule_sources"));
        assert!(command[2].contains("/opt/phpstan/phpstan"));
    }
}
