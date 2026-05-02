use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio::fs;
use uuid::Uuid;

use crate::{
    db::{scan_rule_assets, task_state},
    scan::path_utils,
    state::{AppState, ScanRuleAsset},
};

pub const CODEQL_ENGINE: &str = "codeql";
const CODEQL_QUERY_SOURCE_KINDS: &[&str] = &["internal_query_pack", "user_query_pack"];

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum CodeqlBuildMode {
    None,
    Autobuild,
    Manual,
}

impl CodeqlBuildMode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Autobuild => "autobuild",
            Self::Manual => "manual",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CodeqlBuildPlan {
    pub language: String,
    pub target_path: String,
    pub build_mode: CodeqlBuildMode,
    pub commands: Vec<String>,
    pub working_directory: String,
    pub allow_network: bool,
    pub query_suite: Option<String>,
    pub source_fingerprint: String,
    pub dependency_fingerprint: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CommandValidationResult {
    pub valid: bool,
    pub reason: Option<String>,
}

#[derive(Clone, Debug)]
pub struct ScanCommandArgs<'a> {
    pub source_dir: &'a str,
    pub queries_dir: &'a str,
    pub database_dir: &'a str,
    pub sarif_path: &'a str,
    pub summary_path: &'a str,
    pub events_path: &'a str,
    pub build_plan_path: Option<&'a str>,
    pub build_mode: Option<&'a str>,
    pub language: &'a str,
    pub threads: usize,
    pub ram_mb: u64,
    pub allow_network: bool,
}

#[derive(Clone, Debug)]
pub struct CompileSandboxCommandArgs<'a> {
    pub source_dir: &'a str,
    pub summary_path: &'a str,
    pub events_path: &'a str,
    pub plan_path: &'a str,
    pub evidence_dir: &'a str,
    pub language: &'a str,
    pub allow_network: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CompileSandboxPlan {
    pub language: String,
    pub target_path: String,
    pub build_mode: String,
    pub commands: Vec<String>,
    pub working_directory: String,
    pub allow_network: bool,
    pub query_suite: Option<String>,
    pub source_fingerprint: String,
    pub dependency_fingerprint: String,
    pub status: String,
    pub evidence_json: Value,
}

pub async fn load_query_assets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, CODEQL_ENGINE, CODEQL_QUERY_SOURCE_KINDS).await
}

pub async fn load_query_assets_for_languages(
    state: &AppState,
    languages: &[String],
) -> Result<Vec<ScanRuleAsset>> {
    let all = load_query_assets(state).await?;
    if languages.is_empty() {
        return Ok(all);
    }
    let requested = languages
        .iter()
        .map(|language| normalize_language(language))
        .collect::<BTreeSet<_>>();
    let filtered = all
        .into_iter()
        .filter(|asset| {
            extract_language_from_asset_path(&asset.asset_path)
                .is_some_and(|language| requested.contains(&language))
        })
        .collect::<Vec<_>>();
    Ok(filtered)
}

pub async fn materialize_query_assets(
    workspace_dir: &Path,
    assets: Vec<ScanRuleAsset>,
) -> Result<Option<PathBuf>> {
    if assets.is_empty() {
        return Ok(None);
    }

    let queries_root = workspace_dir.join("codeql-queries");
    for asset in assets {
        let relative_path = relative_query_path(&asset.asset_path);
        let target = queries_root.join(relative_path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).await?;
        }
        fs::write(target, asset.content).await?;
    }

    Ok(Some(queries_root))
}

pub async fn materialize_query_directory_for_languages(
    state: &AppState,
    workspace_dir: &Path,
    languages: &[String],
) -> Result<Option<PathBuf>> {
    let assets = load_query_assets_for_languages(state, languages).await?;
    materialize_query_assets(workspace_dir, assets).await
}

pub fn build_scan_command(args: &ScanCommandArgs<'_>) -> Vec<String> {
    let mut command = vec![
        "codeql-scan".to_string(),
        "--source".to_string(),
        args.source_dir.to_string(),
        "--queries".to_string(),
        args.queries_dir.to_string(),
        "--database".to_string(),
        args.database_dir.to_string(),
        "--sarif".to_string(),
        args.sarif_path.to_string(),
        "--summary".to_string(),
        args.summary_path.to_string(),
        "--events".to_string(),
        args.events_path.to_string(),
        "--language".to_string(),
        normalize_language(args.language),
        "--threads".to_string(),
        args.threads.to_string(),
        "--ram".to_string(),
        args.ram_mb.to_string(),
    ];
    if let Some(build_plan_path) = args.build_plan_path {
        command.push("--build-plan".to_string());
        command.push(build_plan_path.to_string());
    }
    if let Some(build_mode) = args.build_mode {
        command.push("--build-mode".to_string());
        command.push(build_mode.to_string());
    }
    if args.allow_network {
        command.push("--allow-network".to_string());
    }
    command
}

pub fn build_compile_sandbox_command(args: &CompileSandboxCommandArgs<'_>) -> Vec<String> {
    let mut command = vec![
        "codeql-compile-sandbox".to_string(),
        "--source".to_string(),
        args.source_dir.to_string(),
        "--summary".to_string(),
        args.summary_path.to_string(),
        "--events".to_string(),
        args.events_path.to_string(),
        "--plan".to_string(),
        args.plan_path.to_string(),
        "--evidence".to_string(),
        args.evidence_dir.to_string(),
        "--language".to_string(),
        normalize_language(args.language),
    ];
    if args.allow_network {
        command.push("--allow-network".to_string());
    }
    command
}

pub fn parse_compile_sandbox_plan(plan_text: &str) -> Result<CompileSandboxPlan> {
    let payload = serde_json::from_str::<Value>(plan_text)?;
    let language = normalize_language(
        payload
            .get("language")
            .and_then(Value::as_str)
            .unwrap_or("cpp"),
    );
    let commands = payload
        .get("commands")
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let build_mode = payload
        .get("build_mode")
        .and_then(Value::as_str)
        .unwrap_or("manual")
        .to_string();
    let working_directory = normalize_relative_target(
        payload
            .get("working_directory")
            .and_then(Value::as_str)
            .unwrap_or("."),
    );
    if build_mode == "manual" {
        if commands.is_empty() {
            anyhow::bail!("manual compile sandbox plan requires at least one command");
        }
        for command in &commands {
            let validation = validate_build_command(command, &working_directory);
            if !validation.valid {
                anyhow::bail!(
                    "compile sandbox plan command rejected: {}",
                    validation
                        .reason
                        .unwrap_or_else(|| "invalid command".to_string())
                );
            }
        }
    }
    Ok(CompileSandboxPlan {
        language,
        target_path: normalize_relative_target(
            payload
                .get("target_path")
                .and_then(Value::as_str)
                .unwrap_or("."),
        ),
        build_mode,
        commands,
        working_directory,
        allow_network: payload
            .get("allow_network")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        query_suite: payload
            .get("query_suite")
            .and_then(Value::as_str)
            .map(str::to_string),
        source_fingerprint: payload
            .get("source_fingerprint")
            .and_then(Value::as_str)
            .unwrap_or("sha256:unknown-source")
            .to_string(),
        dependency_fingerprint: payload
            .get("dependency_fingerprint")
            .and_then(Value::as_str)
            .unwrap_or("sha256:unknown-deps")
            .to_string(),
        status: payload
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or("accepted")
            .to_string(),
        evidence_json: payload
            .get("evidence_json")
            .cloned()
            .or_else(|| payload.get("evidence").cloned())
            .unwrap_or_else(|| json!({})),
    })
}

pub fn compile_sandbox_plan_to_build_plan(plan: &CompileSandboxPlan) -> CodeqlBuildPlan {
    CodeqlBuildPlan {
        language: plan.language.clone(),
        target_path: plan.target_path.clone(),
        build_mode: match plan.build_mode.as_str() {
            "none" => CodeqlBuildMode::None,
            "autobuild" => CodeqlBuildMode::Autobuild,
            _ => CodeqlBuildMode::Manual,
        },
        commands: plan.commands.clone(),
        working_directory: plan.working_directory.clone(),
        allow_network: plan.allow_network,
        query_suite: plan.query_suite.clone(),
        source_fingerprint: plan.source_fingerprint.clone(),
        dependency_fingerprint: plan.dependency_fingerprint.clone(),
    }
}

pub fn build_plan_json_from_compile_plan(plan: &CompileSandboxPlan) -> Value {
    json!({
        "language": plan.language,
        "target_path": plan.target_path,
        "build_mode": plan.build_mode,
        "commands": plan.commands,
        "working_directory": plan.working_directory,
        "allow_network": plan.allow_network,
        "query_suite": plan.query_suite,
        "source_fingerprint": plan.source_fingerprint,
        "dependency_fingerprint": plan.dependency_fingerprint,
        "status": "accepted",
        "evidence_role": "evidence_only",
    })
}

pub fn build_plan_json_from_record(record: &task_state::CodeqlBuildPlanRecord) -> Value {
    json!({
        "language": record.language.clone(),
        "target_path": record.target_path.clone(),
        "build_mode": record.build_mode.clone(),
        "commands": record.commands.clone(),
        "working_directory": record.working_directory.clone(),
        "allow_network": record
            .evidence_json
            .get("allow_network")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        "query_suite": record.query_suite.clone(),
        "source_fingerprint": record.source_fingerprint.clone(),
        "dependency_fingerprint": record.dependency_fingerprint.clone(),
        "status": record.status.clone(),
        "evidence_role": "evidence_only",
        "evidence_index": record.evidence_json.clone(),
    })
}

pub fn build_plan_record_from_compile_plan(
    id: String,
    project_id: String,
    plan: &CompileSandboxPlan,
    now: String,
) -> task_state::CodeqlBuildPlanRecord {
    let build_plan = compile_sandbox_plan_to_build_plan(plan);
    task_state::CodeqlBuildPlanRecord {
        id,
        project_id,
        language: plan.language.clone(),
        target_path: plan.target_path.clone(),
        source_fingerprint: plan.source_fingerprint.clone(),
        dependency_fingerprint: plan.dependency_fingerprint.clone(),
        build_mode: plan.build_mode.clone(),
        commands: plan.commands.clone(),
        working_directory: plan.working_directory.clone(),
        query_suite: plan.query_suite.clone(),
        status: "accepted".to_string(),
        llm_model: None,
        evidence_json: json!({
            "role": "evidence_only",
            "source": "compile_sandbox",
            "fingerprint": build_plan_fingerprint(&build_plan),
            "allow_network": plan.allow_network,
            "artifact_missing": false,
            "details": plan.evidence_json,
        }),
        created_at: now,
        updated_at: None,
    }
}

pub fn compile_sandbox_evidence_is_truth(evidence_json: &Value) -> bool {
    evidence_json
        .get("role")
        .and_then(Value::as_str)
        .is_some_and(|role| role == "truth")
        || evidence_json
            .get("artifacts_role")
            .and_then(Value::as_str)
            .is_some_and(|role| role == "truth")
}

pub fn parse_sarif_output(
    sarif_text: &str,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&BTreeSet<String>>,
) -> Vec<task_state::StaticFindingRecord> {
    let Ok(document) = serde_json::from_str::<Value>(sarif_text) else {
        return Vec::new();
    };
    let Some(runs) = document.get("runs").and_then(Value::as_array) else {
        return Vec::new();
    };

    let mut findings = Vec::new();
    for run in runs {
        let rules = collect_rule_metadata(run);
        let Some(results) = run.get("results").and_then(Value::as_array) else {
            continue;
        };
        for result in results {
            if let Some(finding) =
                parse_sarif_result(result, &rules, task_id, project_root, known_paths)
            {
                findings.push(finding);
            }
        }
    }
    findings
}

pub fn build_plan_fingerprint(plan: &CodeqlBuildPlan) -> String {
    let payload = json!({
        "language": normalize_language(&plan.language),
        "target_path": normalize_relative_target(&plan.target_path),
        "build_mode": plan.build_mode.as_str(),
        "commands": plan.commands,
        "working_directory": normalize_relative_target(&plan.working_directory),
        "allow_network": plan.allow_network,
        "query_suite": plan.query_suite,
        "source_fingerprint": plan.source_fingerprint,
        "dependency_fingerprint": plan.dependency_fingerprint,
    });
    sha256_json(&payload)
}

pub fn validate_build_command(
    command: &str,
    workspace_relative_dir: &str,
) -> CommandValidationResult {
    let command = command.trim();
    if command.is_empty() {
        return invalid("empty build command");
    }
    if command.len() > 1_000 {
        return invalid("build command is too long");
    }
    if !is_safe_relative_dir(workspace_relative_dir) {
        return invalid("working directory escapes the scan workspace");
    }
    let lowered = command.to_ascii_lowercase();
    let denied_tokens = [
        "docker",
        "podman",
        "kubectl",
        "sudo",
        "su ",
        "ssh ",
        "scp ",
        "rsync ",
        "/var/run/docker.sock",
        "/etc/passwd",
        "/etc/shadow",
        "~/.ssh",
        "id_rsa",
        "aws_secret",
        "github_token",
        "argus_reset_import_token",
    ];
    if let Some(token) = denied_tokens.iter().find(|token| lowered.contains(**token)) {
        return invalid(format!("denied token in build command: {token}"));
    }
    let denied_patterns = [
        "../", "> /", ">/", " 2>/", " >/", "rm -rf /", "mkfs", ":(){",
    ];
    if let Some(pattern) = denied_patterns
        .iter()
        .find(|pattern| lowered.contains(**pattern))
    {
        return invalid(format!(
            "unsafe filesystem pattern in build command: {pattern}"
        ));
    }

    CommandValidationResult {
        valid: true,
        reason: None,
    }
}

pub fn normalize_language(language: &str) -> String {
    match language.trim().to_ascii_lowercase().as_str() {
        "javascript" | "typescript" | "javascript-typescript" | "js" | "ts" => {
            "javascript-typescript".to_string()
        }
        "c" | "c++" | "cpp" | "c-cpp" => "cpp".to_string(),
        "py" => "python".to_string(),
        other => other.to_string(),
    }
}

fn parse_sarif_result(
    result: &Value,
    rules: &std::collections::BTreeMap<String, Value>,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&BTreeSet<String>>,
) -> Option<task_state::StaticFindingRecord> {
    let rule_id = result
        .get("ruleId")
        .and_then(Value::as_str)
        .unwrap_or("unknown-codeql-rule");
    let rule_metadata = rules.get(rule_id);
    let location = result
        .get("locations")
        .and_then(Value::as_array)
        .and_then(|locations| locations.first())?;
    let physical = location.get("physicalLocation")?;
    let raw_uri = physical
        .get("artifactLocation")
        .and_then(|artifact| artifact.get("uri"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    if raw_uri.is_empty() {
        return None;
    }
    let decoded_uri = decode_sarif_uri(raw_uri);
    let region = physical.get("region").unwrap_or(&Value::Null);
    let start_line = region.get("startLine").and_then(Value::as_u64).unwrap_or(1);
    let end_line = region
        .get("endLine")
        .and_then(Value::as_u64)
        .unwrap_or(start_line);
    let (resolved_path, resolved_line) = path_utils::resolve_scan_finding_location(
        Some(&decoded_uri),
        region.get("startLine"),
        project_root,
        known_paths,
    );
    let display_path = resolved_path.as_deref().unwrap_or(decoded_uri.as_str());
    let message = result
        .get("message")
        .and_then(|message| message.get("text").or_else(|| message.get("markdown")))
        .and_then(Value::as_str)
        .or_else(|| {
            rule_metadata
                .and_then(|rule| rule.get("shortDescription"))
                .and_then(|description| description.get("text"))
                .and_then(Value::as_str)
        })
        .unwrap_or(rule_id);
    let properties = rule_metadata
        .and_then(|rule| rule.get("properties"))
        .unwrap_or(&Value::Null);
    let severity = map_sarif_severity(result, properties);
    let tags = properties
        .get("tags")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let cwe = tags
        .iter()
        .filter_map(Value::as_str)
        .filter(|tag| tag.to_ascii_lowercase().starts_with("external/cwe/"))
        .map(|tag| tag.rsplit('/').next().unwrap_or(tag).to_ascii_uppercase())
        .collect::<Vec<_>>();

    let finding_id = format!("codeql-finding-{}", Uuid::new_v4());
    let payload = json!({
        "id": finding_id,
        "scan_task_id": task_id,
        "engine": CODEQL_ENGINE,
        "rule": { "id": rule_id },
        "rule_name": rule_metadata
            .and_then(|rule| rule.get("name"))
            .and_then(Value::as_str)
            .unwrap_or(rule_id),
        "cwe": cwe,
        "description": message,
        "file_path": display_path,
        "raw_file_path": raw_uri,
        "start_line": start_line,
        "end_line": end_line,
        "resolved_file_path": resolved_path,
        "resolved_line_start": resolved_line,
        "severity": severity,
        "status": "open",
        "confidence": "MEDIUM",
        "security_severity": properties.get("security-severity").cloned().unwrap_or(Value::Null),
        "precision": properties.get("precision").cloned().unwrap_or(Value::Null),
        "tags": tags,
        "raw_payload": {
            "result": result,
            "rule": rule_metadata,
        },
    });

    Some(task_state::StaticFindingRecord {
        id: finding_id,
        scan_task_id: task_id.to_string(),
        status: "open".to_string(),
        payload,
    })
}

fn collect_rule_metadata(run: &Value) -> std::collections::BTreeMap<String, Value> {
    let mut rules = std::collections::BTreeMap::new();
    if let Some(driver_rules) = run
        .get("tool")
        .and_then(|tool| tool.get("driver"))
        .and_then(|driver| driver.get("rules"))
        .and_then(Value::as_array)
    {
        for rule in driver_rules {
            if let Some(id) = rule.get("id").and_then(Value::as_str) {
                rules.insert(id.to_string(), rule.clone());
            }
        }
    }
    rules
}

fn map_sarif_severity(result: &Value, properties: &Value) -> &'static str {
    if let Some(security_severity) = properties
        .get("security-severity")
        .and_then(Value::as_str)
        .and_then(|value| value.parse::<f64>().ok())
    {
        if security_severity >= 9.0 {
            return "CRITICAL";
        }
        if security_severity >= 7.0 {
            return "HIGH";
        }
        if security_severity >= 4.0 {
            return "MEDIUM";
        }
        return "LOW";
    }

    match properties
        .get("problem.severity")
        .and_then(Value::as_str)
        .or_else(|| result.get("level").and_then(Value::as_str))
        .unwrap_or("warning")
        .to_ascii_lowercase()
        .as_str()
    {
        "error" => "HIGH",
        "warning" => "MEDIUM",
        "note" | "recommendation" => "LOW",
        _ => "MEDIUM",
    }
}

fn relative_query_path(asset_path: &str) -> PathBuf {
    if let Some(rest) = asset_path.strip_prefix("rules_codeql/") {
        return PathBuf::from(rest);
    }
    PathBuf::from(asset_path)
}

fn extract_language_from_asset_path(asset_path: &str) -> Option<String> {
    let rest = asset_path.strip_prefix("rules_codeql/")?;
    let (language, _) = rest.split_once('/')?;
    Some(normalize_language(language))
}

fn normalize_relative_target(value: &str) -> String {
    let normalized = value.trim().replace('\\', "/");
    if normalized.is_empty() || normalized == "." {
        return ".".to_string();
    }
    normalized
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect::<Vec<_>>()
        .join("/")
}

fn is_safe_relative_dir(value: &str) -> bool {
    let normalized = normalize_relative_target(value);
    if normalized.starts_with('/') || normalized.contains('\0') {
        return false;
    }
    !normalized.split('/').any(|part| part == "..")
}

fn invalid(reason: impl Into<String>) -> CommandValidationResult {
    CommandValidationResult {
        valid: false,
        reason: Some(reason.into()),
    }
}

fn sha256_json(value: &Value) -> String {
    let bytes = serde_json::to_vec(value).unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("sha256:{:x}", hasher.finalize())
}

fn decode_sarif_uri(uri: &str) -> String {
    let without_scheme = uri.strip_prefix("file://").unwrap_or(uri);
    percent_decode_lossy(without_scheme)
}

fn percent_decode_lossy(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            if let Ok(hex) = std::str::from_utf8(&bytes[index + 1..index + 3]) {
                if let Ok(decoded) = u8::from_str_radix(hex, 16) {
                    output.push(decoded);
                    index += 3;
                    continue;
                }
            }
        }
        output.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&output).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{config::AppConfig, state::AppState};

    #[tokio::test]
    async fn loads_and_materializes_codeql_query_assets() {
        let state = AppState::from_config(AppConfig::for_tests())
            .await
            .expect("state");
        let assets = load_query_assets_for_languages(&state, &["Python".to_string()])
            .await
            .expect("assets");
        assert!(!assets.is_empty());
        assert!(assets.iter().all(|asset| asset.engine == CODEQL_ENGINE));
        assert!(assets
            .iter()
            .all(|asset| asset.asset_path.starts_with("rules_codeql/python/")));

        let workspace = std::env::temp_dir().join(format!("codeql-materialize-{}", Uuid::new_v4()));
        let query_dir = materialize_query_assets(&workspace, assets)
            .await
            .expect("materialize")
            .expect("query dir");
        assert!(query_dir.join("python/qlpack.yml").exists());
        let _ = fs::remove_dir_all(&workspace).await;
    }

    #[test]
    fn builds_codeql_scan_command_with_events_and_build_plan() {
        let command = build_scan_command(&ScanCommandArgs {
            source_dir: "/scan/source",
            queries_dir: "/scan/codeql-queries",
            database_dir: "/scan/output/db",
            sarif_path: "/scan/output/results.sarif",
            summary_path: "/scan/output/summary.json",
            events_path: "/scan/output/events.jsonl",
            build_plan_path: Some("/scan/build-plan/build-plan.json"),
            build_mode: None,
            language: "TypeScript",
            threads: 0,
            ram_mb: 6144,
            allow_network: true,
        });
        assert_eq!(command[0], "codeql-scan");
        assert!(command.contains(&"javascript-typescript".to_string()));
        assert!(command.contains(&"--events".to_string()));
        assert!(command.contains(&"--allow-network".to_string()));
    }

    #[test]
    fn parses_codeql_sarif_into_static_findings() {
        let sarif = r#"{
          "version": "2.1.0",
          "runs": [{
            "tool": {"driver": {"rules": [{
              "id": "js/sql-injection",
              "name": "SQL injection",
              "properties": {"security-severity": "8.8", "precision": "high", "tags": ["security", "external/cwe/cwe-089"]}
            }]}},
            "results": [{
              "ruleId": "js/sql-injection",
              "level": "error",
              "message": {"text": "user input reaches SQL"},
              "locations": [{"physicalLocation": {"artifactLocation": {"uri": "src/app%20main.ts"}, "region": {"startLine": 12, "endLine": 14}}}]
            }]
          }]
        }"#;
        let findings = parse_sarif_output(sarif, "task-1", None, None);
        assert_eq!(findings.len(), 1);
        let payload = &findings[0].payload;
        assert_eq!(payload["engine"], "codeql");
        assert_eq!(payload["rule_name"], "SQL injection");
        assert_eq!(payload["file_path"], "src/app main.ts");
        assert_eq!(payload["severity"], "HIGH");
        assert_eq!(payload["cwe"][0], "CWE-089");
    }

    #[test]
    fn builds_compile_sandbox_command_for_cpp_only_recipe_discovery() {
        let command = build_compile_sandbox_command(&CompileSandboxCommandArgs {
            source_dir: "/scan/source",
            summary_path: "/scan/output/compile-summary.json",
            events_path: "/scan/output/compile-events.jsonl",
            plan_path: "/scan/build-plan/compile-sandbox-plan.json",
            evidence_dir: "/scan/evidence",
            language: "C++",
            allow_network: true,
        });
        assert_eq!(command[0], "codeql-compile-sandbox");
        assert!(command.contains(&"cpp".to_string()));
        assert!(command.contains(&"--plan".to_string()));
        assert!(command.contains(&"/scan/build-plan/compile-sandbox-plan.json".to_string()));
        assert!(command.contains(&"--allow-network".to_string()));
    }

    #[test]
    fn compile_sandbox_plan_becomes_db_backed_build_plan_without_evidence_truth() {
        let plan = parse_compile_sandbox_plan(
            r#"{
              "language":"cpp",
              "target_path":".",
              "build_mode":"manual",
              "commands":["make -j2"],
              "working_directory":".",
              "allow_network":false,
              "source_fingerprint":"sha256:source",
              "dependency_fingerprint":"sha256:deps",
              "status":"accepted",
              "evidence_json":{"artifacts_role":"evidence_only","stdout_path":"/scan/evidence/stdout.txt"}
            }"#,
        )
        .expect("compile sandbox plan should parse");

        assert_eq!(plan.language, "cpp");
        assert!(!compile_sandbox_evidence_is_truth(&plan.evidence_json));
        let build_plan = build_plan_json_from_compile_plan(&plan);
        assert_eq!(build_plan["build_mode"], "manual");
        assert_eq!(build_plan["commands"][0], "make -j2");
        assert_eq!(build_plan["evidence_role"], "evidence_only");
        let record = build_plan_record_from_compile_plan(
            "plan-1".to_string(),
            "project-1".to_string(),
            &plan,
            "2026-05-01T00:00:00Z".to_string(),
        );
        assert_eq!(record.status, "accepted");
        assert_eq!(record.evidence_json["role"], "evidence_only");
        assert!(record.evidence_json["fingerprint"]
            .as_str()
            .expect("fingerprint")
            .starts_with("sha256:"));
    }

    #[test]
    fn db_build_plan_json_survives_missing_evidence_artifacts() {
        let plan = parse_compile_sandbox_plan(
            r#"{
              "language":"cpp",
              "target_path":".",
              "build_mode":"manual",
              "commands":["make -j2"],
              "working_directory":".",
              "allow_network":false,
              "source_fingerprint":"sha256:source",
              "dependency_fingerprint":"sha256:deps",
              "status":"accepted",
              "evidence_json":{"artifacts_role":"evidence_only","stdout_path":"/scan/evidence/deleted-stdout.txt"}
            }"#,
        )
        .expect("compile sandbox plan should parse");
        let mut record = build_plan_record_from_compile_plan(
            "plan-1".to_string(),
            "project-1".to_string(),
            &plan,
            "2026-05-01T00:00:00Z".to_string(),
        );
        record.evidence_json["artifact_missing"] = json!(true);

        let replay_plan = build_plan_json_from_record(&record);

        assert_eq!(replay_plan["commands"], json!(["make -j2"]));
        assert_eq!(replay_plan["source_fingerprint"], "sha256:source");
        assert_eq!(replay_plan["dependency_fingerprint"], "sha256:deps");
        assert_eq!(replay_plan["evidence_index"]["artifact_missing"], true);
    }

    #[test]
    fn compile_sandbox_plan_rejects_unvalidated_commands() {
        let error = parse_compile_sandbox_plan(
            r#"{
              "language":"cpp",
              "build_mode":"manual",
              "commands":["docker run -v /:/host alpine"],
              "working_directory":".",
              "source_fingerprint":"sha256:source",
              "dependency_fingerprint":"sha256:deps"
            }"#,
        )
        .expect_err("dangerous compile command must be rejected")
        .to_string();

        assert!(error.contains("denied token"), "{error}");
    }

    #[test]
    fn compile_sandbox_evidence_truth_marker_is_detected() {
        assert!(compile_sandbox_evidence_is_truth(&json!({"role":"truth"})));
        assert!(compile_sandbox_evidence_is_truth(
            &json!({"artifacts_role":"truth"})
        ));
        assert!(!compile_sandbox_evidence_is_truth(
            &json!({"artifacts_role":"evidence_only"})
        ));
    }

    #[test]
    fn validates_build_commands_before_sandbox_execution() {
        assert!(validate_build_command("mvn -B -DskipTests package", ".").valid);
        let denied = validate_build_command("docker run -v /:/host alpine", ".");
        assert!(!denied.valid);
        assert!(denied.reason.unwrap().contains("denied token"));
        assert!(!validate_build_command("npm install", "../outside").valid);
    }

    #[test]
    fn build_plan_fingerprint_changes_when_dependency_fingerprint_changes() {
        let mut plan = CodeqlBuildPlan {
            language: "go".to_string(),
            target_path: ".".to_string(),
            build_mode: CodeqlBuildMode::Manual,
            commands: vec!["go build ./...".to_string()],
            working_directory: ".".to_string(),
            allow_network: true,
            query_suite: Some("security-extended".to_string()),
            source_fingerprint: "source-a".to_string(),
            dependency_fingerprint: "deps-a".to_string(),
        };
        let first = build_plan_fingerprint(&plan);
        plan.dependency_fingerprint = "deps-b".to_string();
        let second = build_plan_fingerprint(&plan);
        assert_ne!(first, second);
        assert!(first.starts_with("sha256:"));
    }
}
