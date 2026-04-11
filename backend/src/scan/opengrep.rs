use std::path::{Path, PathBuf};

use anyhow::Result;
use tokio::fs;

use crate::{
    db::scan_rule_assets::{self, ScanRuleAsset},
    state::AppState,
};

const OPENGREP_ENGINE: &str = "opengrep";
const OPENGREP_RULE_SOURCE_KINDS: &[&str] = &["internal_rule", "patch_rule"];

pub async fn load_rule_assets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, OPENGREP_ENGINE, OPENGREP_RULE_SOURCE_KINDS)
        .await
}

pub async fn materialize_rule_directory(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<Option<PathBuf>> {
    let assets = load_rule_assets(state).await?;
    if assets.is_empty() {
        return Ok(None);
    }

    let rules_root = workspace_dir.join("opengrep-rules");
    for asset in assets {
        let relative_path = relative_rule_path(&asset.asset_path);
        let target = rules_root.join(relative_path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).await?;
        }
        fs::write(target, asset.content).await?;
    }

    Ok(Some(rules_root))
}

pub fn build_validate_command(config_dir: &str) -> Vec<String> {
    vec![
        "opengrep".to_string(),
        "--config".to_string(),
        config_dir.to_string(),
        "--validate".to_string(),
    ]
}

fn relative_rule_path(asset_path: &str) -> PathBuf {
    if let Some(rest) = asset_path.strip_prefix("rules/") {
        return PathBuf::from("internal").join(rest);
    }
    if let Some(rest) = asset_path.strip_prefix("rules_from_patches/") {
        return PathBuf::from("patch").join(rest);
    }
    PathBuf::from(asset_path)
}

#[cfg(test)]
mod tests {
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{build_validate_command, load_rule_assets, materialize_rule_directory};

    #[tokio::test]
    async fn loads_opengrep_internal_and_patch_rule_assets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let assets = load_rule_assets(&state)
            .await
            .expect("opengrep assets should load");
        assert!(assets.len() > 3000);
        assert!(assets.iter().any(|asset| asset.asset_path == "rules/X509-subject-name-validation.yaml"));
        assert!(assets.iter().any(|asset| asset.asset_path.starts_with("rules_from_patches/")));
        assert!(assets.iter().all(|asset| asset.source_kind != "patch_artifact"));
    }

    #[tokio::test]
    async fn materializes_opengrep_rule_directory_with_internal_and_patch_buckets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace = std::env::temp_dir().join(format!("opengrep-materialize-{}", uuid::Uuid::new_v4()));
        let path = materialize_rule_directory(&state, &workspace)
            .await
            .expect("materialize should succeed")
            .expect("rules directory should exist");

        let internal_rule = path.join("internal/X509-subject-name-validation.yaml");
        assert!(internal_rule.exists());
        let patch_rules_dir = path.join("patch");
        assert!(patch_rules_dir.exists());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn builds_validate_command_for_materialized_rule_directory() {
        assert_eq!(
            build_validate_command("/work/opengrep-rules"),
            vec!["opengrep", "--config", "/work/opengrep-rules", "--validate"]
        );
    }
}
