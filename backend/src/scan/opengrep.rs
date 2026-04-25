use std::collections::BTreeSet;
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

    materialize_rule_assets(workspace_dir, assets).await
}

pub async fn materialize_rule_assets(
    workspace_dir: &Path,
    assets: Vec<ScanRuleAsset>,
) -> Result<Option<PathBuf>> {
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

pub struct ScanCommandArgs<'a> {
    pub manifest_path: Option<&'a str>,
    pub config_dir: Option<&'a str>,
    pub target_dir: &'a str,
    pub output_path: &'a str,
    pub summary_path: &'a str,
    pub log_path: &'a str,
    pub jobs: usize,
    pub max_memory_mb: u64,
}

pub fn build_scan_command(args: &ScanCommandArgs<'_>) -> Vec<String> {
    let mut command = vec![
        "opengrep-scan".to_string(),
        "--target".to_string(),
        args.target_dir.to_string(),
        "--output".to_string(),
        args.output_path.to_string(),
        "--summary".to_string(),
        args.summary_path.to_string(),
        "--log".to_string(),
        args.log_path.to_string(),
        "--jobs".to_string(),
        args.jobs.to_string(),
        "--max-memory".to_string(),
        args.max_memory_mb.to_string(),
    ];
    if let Some(manifest_path) = args.manifest_path {
        command.push("--manifest".to_string());
        command.push(manifest_path.to_string());
    }
    if let Some(config_dir) = args.config_dir {
        command.push("--config".to_string());
        command.push(config_dir.to_string());
    }
    command
}

pub fn parse_scan_output(
    json_text: &str,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&std::collections::BTreeSet<String>>,
) -> Vec<task_state::StaticFindingRecord> {
    let parsed = match parse_scan_output_document(json_text) {
        Some(value) => value,
        None => return Vec::new(),
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

pub fn scan_output_has_results_array(json_text: &str) -> bool {
    match parse_scan_output_document(json_text) {
        Some(parsed) => parsed.get("results").and_then(Value::as_array).is_some(),
        None => false,
    }
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
    let display_path = resolved_path.as_deref().unwrap_or(raw_path);

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
        "file_path": display_path,
        "raw_file_path": raw_path,
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

fn parse_scan_output_document(text: &str) -> Option<Value> {
    serde_json::from_str(text)
        .ok()
        .or_else(|| extract_json_object(text))
}

fn extract_json_object(text: &str) -> Option<Value> {
    let start = text.find('{')?;
    let candidate = &text[start..];
    let mut depth = 0i32;
    let mut end_pos = None;
    for (i, ch) in candidate.char_indices() {
        match ch {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    end_pos = Some(i + 1);
                    break;
                }
            }
            _ => {}
        }
    }
    let json_str = &candidate[..end_pos?];
    serde_json::from_str(json_str).ok()
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

fn normalize_language(lang: &str) -> String {
    match lang.to_lowercase().as_str() {
        "c#" => "csharp".to_string(),
        "c++" => "cpp".to_string(),
        other => other.to_string(),
    }
}

fn extract_language_from_asset_path(asset_path: &str) -> Option<String> {
    let rest = asset_path.strip_prefix("rules_from_patches/")?;
    let lang = rest.split('/').next()?;
    if lang.is_empty() {
        return None;
    }
    Some(normalize_language(lang))
}

fn extract_rule_languages(content: &str) -> BTreeSet<String> {
    let mut languages = BTreeSet::new();
    let mut in_languages_block = false;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("languages:") {
            in_languages_block = true;
            continue;
        }
        if in_languages_block {
            if let Some(lang) = trimmed.strip_prefix("- ") {
                let lang = lang.trim().trim_matches('"').trim_matches('\'');
                if !lang.is_empty() {
                    languages.insert(normalize_language(lang));
                }
            } else {
                in_languages_block = false;
            }
        }
    }
    languages
}

fn rule_matches_languages(asset: &ScanRuleAsset, project_languages: &BTreeSet<String>) -> bool {
    if let Some(lang) = extract_language_from_asset_path(&asset.asset_path) {
        return project_languages.contains(&lang);
    }
    let rule_langs = extract_rule_languages(&asset.content);
    if rule_langs.is_empty() {
        return true;
    }
    if rule_langs.contains("generic") || rule_langs.contains("regex") {
        return true;
    }
    rule_langs.iter().any(|l| project_languages.contains(l))
}

pub async fn load_rule_assets_for_languages(
    state: &AppState,
    languages: &[String],
) -> Result<Vec<ScanRuleAsset>> {
    let all = load_rule_assets(state).await?;
    if languages.is_empty() {
        return Ok(all);
    }
    let mut normalized: BTreeSet<String> =
        languages.iter().map(|l| normalize_language(l)).collect();
    if normalized.contains("c") {
        normalized.insert("cpp".to_string());
    }
    let filtered: Vec<ScanRuleAsset> = all
        .into_iter()
        .filter(|asset| rule_matches_languages(asset, &normalized))
        .collect();
    if filtered.is_empty() {
        return load_rule_assets(state).await;
    }
    Ok(filtered)
}

pub async fn materialize_rule_directory_for_languages(
    state: &AppState,
    workspace_dir: &Path,
    languages: &[String],
) -> Result<Option<PathBuf>> {
    let assets = load_rule_assets_for_languages(state, languages).await?;
    if assets.is_empty() {
        return Ok(None);
    }

    materialize_rule_assets(workspace_dir, assets).await
}

#[cfg(test)]
mod tests {
    use tokio::fs;

    use crate::{config::AppConfig, state::AppState};

    use super::{
        build_scan_command, build_validate_command, extract_language_from_asset_path,
        extract_rule_languages, load_rule_assets, load_rule_assets_for_languages,
        materialize_rule_assets, materialize_rule_directory, normalize_language, ScanCommandArgs,
    };

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
            .any(|asset| asset.asset_path == "rules_opengrep/aes_ecb_mode.yaml"));
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

        let internal_rule = path.join("internal/aes_ecb_mode.yaml");
        assert!(internal_rule.exists());
        let patch_rules_dir = path.join("patch");
        assert!(patch_rules_dir.exists());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[tokio::test]
    async fn materializes_selected_rule_assets_without_image_manifest_dependency() {
        let workspace = std::env::temp_dir().join(format!(
            "opengrep-selected-materialize-{}",
            uuid::Uuid::new_v4()
        ));
        let selected = vec![crate::state::ScanRuleAsset {
            engine: "opengrep".to_string(),
            source_kind: "internal_rule".to_string(),
            asset_path: "rules_opengrep/demo-rule.yaml".to_string(),
            file_format: "yaml".to_string(),
            sha256: "sha".to_string(),
            content: "rules:\n  - id: demo\n    languages: [python]\n    message: demo\n    severity: ERROR\n    pattern: print($X)\n".to_string(),
            metadata_json: serde_json::json!({}),
        }];

        let path = materialize_rule_assets(&workspace, selected)
            .await
            .expect("materialize selected assets")
            .expect("rules directory should exist");

        let materialized = path.join("internal/demo-rule.yaml");
        assert!(materialized.exists(), "{}", materialized.display());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn builds_validate_command_for_materialized_rule_directory() {
        assert_eq!(
            build_validate_command("/work/opengrep-rules"),
            vec!["opengrep", "--config", "/work/opengrep-rules", "--validate"]
        );
    }

    #[test]
    fn builds_scan_command_with_bounded_resources_and_stdout_output() {
        assert_eq!(
            build_scan_command(&ScanCommandArgs {
                manifest_path: Some("/work/rules.manifest"),
                config_dir: None,
                target_dir: "/work/source",
                output_path: "/work/output/results.json",
                summary_path: "/work/output/summary.json",
                log_path: "/work/output/opengrep.log",
                jobs: 4,
                max_memory_mb: 1536,
            }),
            vec![
                "opengrep-scan",
                "--target",
                "/work/source",
                "--output",
                "/work/output/results.json",
                "--summary",
                "/work/output/summary.json",
                "--log",
                "/work/output/opengrep.log",
                "--jobs",
                "4",
                "--max-memory",
                "1536",
                "--manifest",
                "/work/rules.manifest",
            ]
        );
    }

    #[test]
    fn normalizes_language_names() {
        assert_eq!(normalize_language("Java"), "java");
        assert_eq!(normalize_language("C#"), "csharp");
        assert_eq!(normalize_language("C++"), "cpp");
        assert_eq!(normalize_language("python"), "python");
        assert_eq!(normalize_language("TypeScript"), "typescript");
    }

    #[test]
    fn extracts_language_from_patch_rule_path() {
        assert_eq!(
            extract_language_from_asset_path("rules_from_patches/java/vuln-cxf.yml"),
            Some("java".to_string())
        );
        assert_eq!(
            extract_language_from_asset_path("rules_from_patches/cpp/vuln-test.yml"),
            Some("cpp".to_string())
        );
        assert_eq!(
            extract_language_from_asset_path("rules_opengrep/some-rule.yaml"),
            None
        );
    }

    #[test]
    fn extracts_languages_from_rule_yaml() {
        let yaml = r#"rules:
- id: test-rule
  languages:
  - java
  - kotlin
  severity: ERROR
"#;
        let langs = extract_rule_languages(yaml);
        assert!(langs.contains("java"));
        assert!(langs.contains("kotlin"));
        assert_eq!(langs.len(), 2);
    }

    #[test]
    fn extracts_languages_handles_generic() {
        let yaml = r#"rules:
- id: generic-rule
  languages:
  - generic
  severity: ERROR
"#;
        let langs = extract_rule_languages(yaml);
        assert!(langs.contains("generic"));
    }

    #[test]
    fn extracts_languages_empty_when_no_languages_field() {
        let yaml = r#"rules:
- id: test-rule
  severity: ERROR
"#;
        let langs = extract_rule_languages(yaml);
        assert!(langs.is_empty());
    }

    #[tokio::test]
    async fn loads_filtered_rules_for_java_project() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let all = load_rule_assets(&state).await.expect("should load all");
        let java_only = load_rule_assets_for_languages(&state, &["Java".to_string()])
            .await
            .expect("should load java rules");
        assert!(
            java_only.len() < all.len(),
            "filtered should be fewer than all"
        );
        assert!(!java_only.is_empty(), "java rules should not be empty");
        for asset in &java_only {
            if let Some(lang) = extract_language_from_asset_path(&asset.asset_path) {
                assert_eq!(
                    lang, "java",
                    "patch rule should be java: {}",
                    asset.asset_path
                );
            }
        }
    }

    #[tokio::test]
    async fn empty_languages_returns_all_rules() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let all = load_rule_assets(&state).await.expect("should load all");
        let unfiltered = load_rule_assets_for_languages(&state, &[])
            .await
            .expect("should load all when empty");
        assert_eq!(all.len(), unfiltered.len());
    }

    #[tokio::test]
    async fn c_project_also_includes_cpp_rules() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state should build");
        let c_rules = load_rule_assets_for_languages(&state, &["C".to_string()])
            .await
            .expect("should load c rules");
        assert!(
            c_rules.iter().any(|a| {
                extract_language_from_asset_path(&a.asset_path) == Some("cpp".to_string())
            }),
            "C project should also include cpp patch rules"
        );
    }

    #[test]
    fn parses_findings_from_mixed_stdout() {
        let mixed = r#"
┌─────────────┐
│ Scan Status │
└─────────────┘
  Scanning 1 file with 2182 rules:

{"version":"1.15.1","results":[{"check_id":"test-rule","path":"src/main.c","start":{"line":10,"col":1,"offset":0},"end":{"line":10,"col":50,"offset":49},"extra":{"message":"test finding","severity":"ERROR","metadata":{},"lines":"int x = 0;","is_ignored":false,"validation_state":"NO_VALIDATOR","engine_kind":"OSS"}}],"errors":[],"paths":{"scanned":["src/main.c"]}}

┌──────────────┐
│ Scan Summary │
└──────────────┘
  Ran 1168 rules on 1 file: 1 finding.
"#;
        let findings = super::parse_scan_output(mixed, "task-1", None, None);
        assert_eq!(
            findings.len(),
            1,
            "should extract finding from mixed stdout"
        );
        assert_eq!(findings[0].payload["rule_name"], "test-rule");
    }

    #[test]
    fn parses_findings_from_pure_json() {
        let json = r#"{"version":"1.15.1","results":[{"check_id":"pure-rule","path":"app.py","start":{"line":5,"col":1,"offset":0},"end":{"line":5,"col":20,"offset":19},"extra":{"message":"pure test","severity":"ERROR","metadata":{},"lines":"x = eval(input())","is_ignored":false,"validation_state":"NO_VALIDATOR","engine_kind":"OSS"}}],"errors":[]}"#;
        let findings = super::parse_scan_output(json, "task-2", None, None);
        assert_eq!(findings.len(), 1);
    }

    #[test]
    fn parses_container_absolute_paths_as_project_relative_for_frontend_rows() {
        let json = r#"{"version":"1.15.1","results":[{"check_id":"path-rule","path":"/tmp/Argus/scans/opengrep-runtime/abc/source/src/main.py","start":{"line":5,"col":1,"offset":0},"end":{"line":5,"col":20,"offset":19},"extra":{"message":"path test","severity":"ERROR","metadata":{},"lines":"dangerous_call()"}}],"errors":[]}"#;
        let known_paths = std::collections::BTreeSet::from(["src/main.py".to_string()]);
        let findings = super::parse_scan_output(
            json,
            "task-3",
            Some("/tmp/Argus/scans/opengrep-runtime/abc/source"),
            Some(&known_paths),
        );

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].payload["file_path"], "src/main.py");
        assert_eq!(
            findings[0].payload["raw_file_path"],
            "/tmp/Argus/scans/opengrep-runtime/abc/source/src/main.py"
        );
        assert_eq!(findings[0].payload["resolved_file_path"], "src/main.py");
    }

    #[test]
    fn retains_warning_and_info_severity_findings() {
        let json = r#"{"version":"1.15.1","results":[
            {"check_id":"err-rule","path":"app.c","start":{"line":1,"col":1,"offset":0},"end":{"line":1,"col":10,"offset":9},"extra":{"message":"error","severity":"ERROR","metadata":{},"lines":"x()"}},
            {"check_id":"warn-rule","path":"app.c","start":{"line":2,"col":1,"offset":0},"end":{"line":2,"col":10,"offset":9},"extra":{"message":"warning","severity":"WARNING","metadata":{},"lines":"y()"}},
            {"check_id":"info-rule","path":"app.c","start":{"line":3,"col":1,"offset":0},"end":{"line":3,"col":10,"offset":9},"extra":{"message":"info","severity":"INFO","metadata":{},"lines":"z()"}}
        ],"errors":[]}"#;
        let findings = super::parse_scan_output(json, "task-sev", None, None);
        assert_eq!(findings.len(), 3, "all severity levels must be retained");
        let severities: Vec<&str> = findings
            .iter()
            .map(|f| f.payload["severity"].as_str().unwrap())
            .collect();
        assert!(severities.contains(&"ERROR"));
        assert!(severities.contains(&"WARNING"));
        assert!(severities.contains(&"INFO"));
    }

    #[test]
    fn detects_when_scan_output_has_results_array() {
        assert!(super::scan_output_has_results_array(
            r#"{"version":"1.15.1","results":[]}"#
        ));
        assert!(!super::scan_output_has_results_array(""));
        assert!(!super::scan_output_has_results_array(
            r#"{"version":"1.15.1"}"#
        ));
        assert!(!super::scan_output_has_results_array("not-json"));
    }
}
