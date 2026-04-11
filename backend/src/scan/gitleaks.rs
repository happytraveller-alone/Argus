use std::path::{Path, PathBuf};

use anyhow::Result;
use tokio::fs;

use crate::{db::scan_rule_assets, state::AppState};

const GITLEAKS_ASSET_PATH: &str = "gitleaks_builtin/gitleaks-default.toml";
const GITLEAKS_ASSET_ENGINE: &str = "gitleaks";
const GITLEAKS_ASSET_SOURCE_KIND: &str = "builtin";

pub async fn load_builtin_config(state: &AppState) -> Result<Option<String>> {
    scan_rule_assets::load_asset_content(
        state,
        GITLEAKS_ASSET_ENGINE,
        GITLEAKS_ASSET_SOURCE_KIND,
        GITLEAKS_ASSET_PATH,
    )
    .await
}

pub async fn materialize_builtin_config(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<Option<PathBuf>> {
    let Some(content) = load_builtin_config(state).await? else {
        return Ok(None);
    };

    fs::create_dir_all(workspace_dir).await?;
    let config_path = workspace_dir.join("gitleaks.toml");
    fs::write(&config_path, content).await?;
    Ok(Some(config_path))
}

pub fn build_detect_command(
    source_dir: &str,
    report_path: &str,
    config_path: Option<&str>,
) -> Vec<String> {
    let mut cmd = vec![
        "gitleaks".to_string(),
        "detect".to_string(),
        "--source".to_string(),
        source_dir.to_string(),
        "--report-format".to_string(),
        "json".to_string(),
        "--report-path".to_string(),
        report_path.to_string(),
        "--exit-code".to_string(),
        "0".to_string(),
        "--no-git".to_string(),
    ];
    if let Some(config_path) = config_path {
        cmd.push("--config".to_string());
        cmd.push(config_path.to_string());
    }
    cmd
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{build_detect_command, load_builtin_config, materialize_builtin_config};

    #[tokio::test]
    async fn loads_builtin_gitleaks_config_from_rule_assets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let config = load_builtin_config(&state)
            .await
            .expect("config should load")
            .expect("builtin gitleaks config should exist");
        assert!(config.contains("[[rules]]"));
        assert!(config.contains("1password-secret-key"));
    }

    #[tokio::test]
    async fn materializes_builtin_gitleaks_config_to_workspace() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace = std::env::temp_dir().join(format!("gitleaks-materialize-{}", uuid::Uuid::new_v4()));
        let path = materialize_builtin_config(&state, &workspace)
            .await
            .expect("materialize should succeed")
            .expect("config path should exist");
        let content = fs::read_to_string(&path).await.expect("materialized config should be readable");
        assert!(content.contains("1password-secret-key"));
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn builds_detect_command_with_optional_config() {
        let with_config = build_detect_command("/work/source", "/work/report.json", Some("/work/gitleaks.toml"));
        assert_eq!(
            with_config,
            vec![
                "gitleaks",
                "detect",
                "--source",
                "/work/source",
                "--report-format",
                "json",
                "--report-path",
                "/work/report.json",
                "--exit-code",
                "0",
                "--no-git",
                "--config",
                "/work/gitleaks.toml",
            ]
        );

        let without_config = build_detect_command("/work/source", "/work/report.json", None);
        assert!(!without_config.iter().any(|part| part == "--config"));
        assert!(Path::new("/work/source").is_absolute());
    }
}
