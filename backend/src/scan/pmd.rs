use std::path::{Path, PathBuf};

use anyhow::Result;
use tokio::fs;

use crate::{db::scan_rule_assets, state::{AppState, ScanRuleAsset}};

const PMD_ENGINE: &str = "pmd";
const PMD_SOURCE_KIND: &str = "builtin";

pub async fn load_builtin_rulesets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, PMD_ENGINE, &[PMD_SOURCE_KIND]).await
}

pub async fn materialize_ruleset_directory(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<Option<PathBuf>> {
    let assets = load_builtin_rulesets(state).await?;
    if assets.is_empty() {
        return Ok(None);
    }

    let rules_dir = workspace_dir.join("pmd-rules");
    fs::create_dir_all(&rules_dir).await?;
    for asset in assets {
        let file_name = asset
            .asset_path
            .strip_prefix("rules_pmd/")
            .unwrap_or(asset.asset_path.as_str());
        let target = rules_dir.join(file_name);
        fs::write(target, asset.content).await?;
    }

    Ok(Some(rules_dir))
}

pub fn select_preflight_ruleset(assets: &[ScanRuleAsset]) -> Option<String> {
    assets
        .iter()
        .find(|asset| asset.asset_path.ends_with("JavaErrorProneEmptyCatchBlock.xml"))
        .or_else(|| assets.first())
        .map(|asset| {
            asset
                .asset_path
                .strip_prefix("rules_pmd/")
                .unwrap_or(asset.asset_path.as_str())
                .to_string()
        })
}

pub fn build_check_command(source_dir: &str, ruleset_path: &str) -> Vec<String> {
    vec![
        "pmd".to_string(),
        "check".to_string(),
        "-d".to_string(),
        source_dir.to_string(),
        "-R".to_string(),
        ruleset_path.to_string(),
        "-f".to_string(),
        "text".to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{build_check_command, load_builtin_rulesets, materialize_ruleset_directory, select_preflight_ruleset};

    #[tokio::test]
    async fn loads_pmd_builtin_rulesets_from_rule_assets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let assets = load_builtin_rulesets(&state)
            .await
            .expect("pmd assets should load");
        assert!(assets.len() > 100);
        assert!(assets.iter().any(|asset| asset.asset_path == "rules_pmd/ApexBadCrypto.xml"));
    }

    #[tokio::test]
    async fn materializes_pmd_ruleset_directory() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace = std::env::temp_dir().join(format!("pmd-materialize-{}", uuid::Uuid::new_v4()));
        let path = materialize_ruleset_directory(&state, &workspace)
            .await
            .expect("materialize should succeed")
            .expect("rules directory should exist");
        assert!(path.join("ApexBadCrypto.xml").exists());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn selects_preflight_ruleset_and_builds_command() {
        let assets = vec![
            crate::state::ScanRuleAsset {
                engine: "pmd".to_string(),
                source_kind: "builtin".to_string(),
                asset_path: "rules_pmd/ApexBadCrypto.xml".to_string(),
                file_format: "xml".to_string(),
                sha256: "a".to_string(),
                content: "<ruleset />".to_string(),
                metadata_json: serde_json::json!({}),
            },
            crate::state::ScanRuleAsset {
                engine: "pmd".to_string(),
                source_kind: "builtin".to_string(),
                asset_path: "rules_pmd/JavaErrorProneEmptyCatchBlock.xml".to_string(),
                file_format: "xml".to_string(),
                sha256: "b".to_string(),
                content: "<ruleset />".to_string(),
                metadata_json: serde_json::json!({}),
            },
        ];
        let selected = select_preflight_ruleset(&assets).expect("ruleset should be selected");
        assert_eq!(selected, "JavaErrorProneEmptyCatchBlock.xml");
        assert_eq!(
            build_check_command("/work/source", "/work/pmd-rules/JavaErrorProneEmptyCatchBlock.xml"),
            vec![
                "pmd",
                "check",
                "-d",
                "/work/source",
                "-R",
                "/work/pmd-rules/JavaErrorProneEmptyCatchBlock.xml",
                "-f",
                "text"
            ]
        );
    }
}
