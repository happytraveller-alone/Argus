use std::path::{Path, PathBuf};

use anyhow::Result;
use serde_json::Value;
use tokio::fs;
use uuid::Uuid;

use crate::{
    db::{scan_rule_assets, task_state},
    scan::path_utils,
    state::{AppState, ScanRuleAsset},
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

pub fn build_scan_command(config_dir: &str, target_dir: &str) -> Vec<String> {
    vec![
        "opengrep".to_string(),
        "--config".to_string(),
        config_dir.to_string(),
        "--json".to_string(),
        target_dir.to_string(),
    ]
}

pub fn parse_scan_output(
    json_text: &str,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&std::collections::BTreeSet<String>>,
) -> Vec<task_state::StaticFindingRecord> {
    let parsed: Value = match serde_json::from_str(json_text) {
        Ok(v) => v,
        Err(_) => return Vec::new(),
    };

    let results = match parsed.get("results").and_then(Value::as_array) {
        Some(arr) => arr,
        None => return Vec::new(),
    };

    results
        .iter()
        .filter_map(|result| parse_single_result(result, task_id, project_root, known_paths))
        .collect()
}

fn parse_single_result(
    result: &Value,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&std::collections::BTreeSet<String>>,
) -> Option<task_state::StaticFindingRecord> {
    let check_id = result
        .get("check_id")
        .and_then(Value::as_str)
        .unwrap_or("unknown-rule");
    let raw_path = result.get("path").and_then(Value::as_str).unwrap_or("");
    if raw_path.is_empty() {
        return None;
    }

    let start_line = result
        .get("start")
        .and_then(|s| s.get("line"))
        .and_then(Value::as_u64)
        .unwrap_or(1);
    let end_line = result
        .get("end")
        .and_then(|e| e.get("line"))
        .and_then(Value::as_u64)
        .unwrap_or(start_line);

    let extra = result.get("extra");
    let message = extra
        .and_then(|e| e.get("message"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let severity = extra
        .and_then(|e| e.get("severity"))
        .and_then(Value::as_str)
        .unwrap_or("WARNING");
    let metadata = extra.and_then(|e| e.get("metadata"));
    let confidence = metadata
        .and_then(|m| m.get("confidence"))
        .and_then(Value::as_str)
        .unwrap_or("MEDIUM");
    let cwe: Vec<String> = metadata
        .and_then(|m| m.get("cwe"))
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let (resolved_path, resolved_line) = path_utils::resolve_scan_finding_location(
        Some(raw_path),
        result.get("start").and_then(|s| s.get("line")),
        project_root,
        known_paths,
    );

    let lines = extra
        .and_then(|e| e.get("lines"))
        .and_then(Value::as_str)
        .unwrap_or("");

    let finding_id = format!("opengrep-finding-{}", Uuid::new_v4());
    let payload = serde_json::json!({
        "id": finding_id,
        "scan_task_id": task_id,
        "rule": { "id": check_id },
        "rule_name": check_id,
        "cwe": cwe,
        "description": message,
        "file_path": raw_path,
        "start_line": start_line,
        "end_line": end_line,
        "resolved_file_path": resolved_path,
        "resolved_line_start": resolved_line,
        "code_snippet": lines,
        "severity": severity,
        "status": "open",
        "confidence": confidence,
    });

    Some(task_state::StaticFindingRecord {
        id: finding_id,
        scan_task_id: task_id.to_string(),
        status: "open".to_string(),
        payload,
    })
}

fn relative_rule_path(asset_path: &str) -> PathBuf {
    if let Some(rest) = asset_path.strip_prefix("rules_opengrep/") {
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
        assert!(assets.len() > 2000);
        assert!(assets
            .iter()
            .any(|asset| asset.asset_path == "rules_opengrep/X509-subject-name-validation.yaml"));
        assert!(assets
            .iter()
            .any(|asset| asset.asset_path.starts_with("rules_from_patches/")));
        assert!(assets
            .iter()
            .all(|asset| asset.source_kind != "patch_artifact"));
        assert!(assets.iter().all(|asset| asset.content.lines().all(|line| {
            let Some(value) = line.trim().strip_prefix("severity:") else {
                return true;
            };
            value.trim().trim_matches('"').trim_matches('\'') == "ERROR"
        })));
    }

    #[tokio::test]
    async fn materializes_opengrep_rule_directory_with_internal_and_patch_buckets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let workspace =
            std::env::temp_dir().join(format!("opengrep-materialize-{}", uuid::Uuid::new_v4()));
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
