use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::fs;
use uuid::Uuid;

use crate::{
    db::{scan_rule_assets, task_state},
    scan::path_utils,
    state::{AppState, ScanRuleAsset},
};

pub const JOERN_ENGINE: &str = "joern";
const JOERN_RULE_SOURCE_KINDS: &[&str] = &["internal_query"];

pub const DEFAULT_JOERN_IMAGE: &str = "ghcr.nju.edu.cn/joernio/joern:nightly";
pub const SUMMARY_REL_PATH: &str = "output/summary.json";
pub const GRAPH_PROOF_REL_PATH: &str = "output/graph-proof.json";
pub const FINDINGS_REL_PATH: &str = "output/findings.json";
pub const JOERN_LOG_REL_PATH: &str = "output/joern.log";
pub const STDOUT_REL_PATH: &str = "output/stdout.log";
pub const STDERR_REL_PATH: &str = "output/stderr.log";
pub const CPG_REL_PATH: &str = "output/cpg.bin";
pub const QUERY_SCRIPT_REL_PATH: &str = "c/argus-joern-scan.sc";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JoernOutputPaths {
    pub summary_rel_path: String,
    pub graph_proof_rel_path: String,
    pub findings_rel_path: String,
    pub log_rel_path: String,
    pub stdout_rel_path: String,
    pub stderr_rel_path: String,
    pub cpg_rel_path: String,
}

impl Default for JoernOutputPaths {
    fn default() -> Self {
        Self {
            summary_rel_path: SUMMARY_REL_PATH.to_string(),
            graph_proof_rel_path: GRAPH_PROOF_REL_PATH.to_string(),
            findings_rel_path: FINDINGS_REL_PATH.to_string(),
            log_rel_path: JOERN_LOG_REL_PATH.to_string(),
            stdout_rel_path: STDOUT_REL_PATH.to_string(),
            stderr_rel_path: STDERR_REL_PATH.to_string(),
            cpg_rel_path: CPG_REL_PATH.to_string(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct JoernDocsEvidence {
    pub image_source: &'static str,
    pub parse_command_source: &'static str,
    pub script_output_source: &'static str,
    pub scan_result_source: &'static str,
}

pub fn docs_evidence() -> JoernDocsEvidence {
    JoernDocsEvidence {
        image_source: "https://github.com/joernio/joern/pkgs/container/joern documents docker pull ghcr.nju.edu.cn/joernio/joern:nightly",
        parse_command_source: "https://docs.joern.io/export/ documents joern-parse /src/directory before joern-export",
        script_output_source: "https://docs.joern.io/interpreter/ documents joern --script with --param and the #> file-output operator",
        scan_result_source: "https://docs.joern.io/scan/ documents Joern Scan generating a CPG, executing queries, and printing Result: score/title/file/line/function",
    }
}

pub async fn load_rule_assets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, JOERN_ENGINE, JOERN_RULE_SOURCE_KINDS).await
}

pub async fn materialize_rule_assets(
    workspace_dir: &Path,
    assets: Vec<ScanRuleAsset>,
) -> Result<Option<PathBuf>> {
    if assets.is_empty() {
        return Ok(None);
    }

    let queries_root = workspace_dir.join("joern-queries");
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

pub async fn materialize_query_directory(
    state: &AppState,
    workspace_dir: &Path,
) -> Result<PathBuf> {
    let assets = load_rule_assets(state).await?;
    materialize_rule_assets(workspace_dir, assets)
        .await?
        .ok_or_else(|| anyhow!("no joern query assets available"))
}

fn relative_query_path(asset_path: &str) -> PathBuf {
    if let Some(rest) = asset_path.strip_prefix("rules_joern/") {
        return PathBuf::from(rest);
    }
    PathBuf::from(asset_path)
}

pub fn build_wrapper_script(paths: &JoernOutputPaths) -> String {
    format!(
        r#"#!/bin/sh
set -eu
SOURCE_DIR="${{JOERN_SOURCE_DIR:-/scan/source}}"
OUTPUT_DIR="${{JOERN_OUTPUT_DIR:-/scan/output}}"
QUERY_DIR="${{JOERN_QUERY_DIR:-/scan/joern-queries}}"
CPG_PATH="$OUTPUT_DIR/cpg.bin"
GRAPH_PROOF_PATH="$OUTPUT_DIR/graph-proof.json"
FINDINGS_PATH="$OUTPUT_DIR/findings.json"
SUMMARY_PATH="$OUTPUT_DIR/summary.json"
LOG_PATH="$OUTPUT_DIR/joern.log"
mkdir -p "$OUTPUT_DIR"
: > "$LOG_PATH"
printf 'Argus Joern wrapper starting\n' >> "$LOG_PATH"
joern-parse "$SOURCE_DIR" --out "$CPG_PATH" >> "$LOG_PATH" 2>&1
joern --script "$QUERY_DIR/{query_script}" \
  --param cpgFile="$CPG_PATH" \
  --param sourceDir="$SOURCE_DIR" \
  --param graphProofOut="$GRAPH_PROOF_PATH" \
  --param findingsOut="$FINDINGS_PATH" \
  >> "$LOG_PATH" 2>&1
python3 - <<'PY' "$SUMMARY_PATH" "$GRAPH_PROOF_PATH" "$FINDINGS_PATH"
import json, sys
summary, graph, findings = sys.argv[1:]
def count_findings(path):
    with open(path, 'r', encoding='utf-8') as fh:
        data=json.load(fh)
    items=data.get('findings', []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise ValueError('findings.json field "findings" must be an array')
    return len(items)
data={{
  "status":"scan_completed",
  "engine":"joern",
  "schema_version":"argus.joern.v1",
  "scanner":"joern",
  "cpg_path":"{cpg}",
  "graph_proof_path":"{graph}",
  "findings_path":"{findings}",
  "finding_count":count_findings(findings),
}}
with open(summary, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, sort_keys=True)
    fh.write("\n")
PY
"#,
        cpg = paths.cpg_rel_path,
        graph = paths.graph_proof_rel_path,
        findings = paths.findings_rel_path,
        query_script = QUERY_SCRIPT_REL_PATH,
    )
}

#[derive(Clone, Debug)]
pub struct ParsedJoernOutput {
    pub findings: Vec<task_state::StaticFindingRecord>,
    pub graph_proof: Value,
    pub summary: Value,
}

pub async fn parse_output_dir(
    output_dir: &Path,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&BTreeSet<String>>,
    limit_bytes: usize,
) -> Result<ParsedJoernOutput> {
    let summary = read_json_file(&output_dir.join("summary.json"), limit_bytes)
        .await
        .context("read joern summary.json")?;
    let graph_proof = read_json_file(&output_dir.join("graph-proof.json"), limit_bytes)
        .await
        .context("read joern graph-proof.json")?;
    validate_graph_proof(&graph_proof)?;
    let findings_doc = read_json_file(&output_dir.join("findings.json"), limit_bytes)
        .await
        .context("read joern findings.json")?;
    let findings = parse_findings_document(&findings_doc, task_id, project_root, known_paths)?;
    Ok(ParsedJoernOutput {
        findings,
        graph_proof,
        summary,
    })
}

pub async fn read_json_file(path: &Path, limit_bytes: usize) -> Result<Value> {
    let metadata = fs::metadata(path)
        .await
        .with_context(|| format!("missing required joern artifact: {}", path.display()))?;
    if metadata.len() > limit_bytes as u64 {
        bail!(
            "joern artifact {} size {} bytes exceeds JOERN_RESULTS_JSON_LIMIT_BYTES={}",
            path.display(),
            metadata.len(),
            limit_bytes
        );
    }
    let text = fs::read_to_string(path)
        .await
        .with_context(|| format!("read joern artifact: {}", path.display()))?;
    serde_json::from_str(&text)
        .with_context(|| format!("parse joern artifact JSON: {}", path.display()))
}

pub fn validate_graph_proof(graph_proof: &Value) -> Result<()> {
    let object = graph_proof
        .as_object()
        .ok_or_else(|| anyhow!("joern graph-proof.json must be an object"))?;
    let has_files = object
        .get("files")
        .and_then(Value::as_array)
        .is_some_and(|items| !items.is_empty());
    let has_functions = object
        .get("functions")
        .and_then(Value::as_array)
        .is_some_and(|items| !items.is_empty());
    if !has_files || !has_functions {
        bail!("joern graph proof must include non-empty files and functions arrays");
    }
    Ok(())
}

pub fn parse_findings_document(
    document: &Value,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&BTreeSet<String>>,
) -> Result<Vec<task_state::StaticFindingRecord>> {
    let findings = document
        .get("findings")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("joern findings.json must contain a findings array"))?;
    findings
        .iter()
        .map(|finding| parse_single_finding(finding, task_id, project_root, known_paths))
        .collect()
}

fn parse_single_finding(
    finding: &Value,
    task_id: &str,
    project_root: Option<&str>,
    known_paths: Option<&BTreeSet<String>>,
) -> Result<task_state::StaticFindingRecord> {
    let object = finding
        .as_object()
        .ok_or_else(|| anyhow!("joern finding must be an object"))?;
    let rule_id = required_str(finding, &["rule_id", "check_id", "ruleId"])?;
    let raw_file_path = required_str(finding, &["file_path", "path", "file"])?;
    let start_line_value = object
        .get("start_line")
        .or_else(|| object.get("line"))
        .or_else(|| object.get("line_number"))
        .unwrap_or(&Value::Null);
    let start_line = path_utils::normalize_scan_line_start(start_line_value).unwrap_or(1);
    let end_line = object
        .get("end_line")
        .and_then(path_utils::normalize_scan_line_start)
        .unwrap_or(start_line);
    let title = optional_str(finding, &["title", "name"])
        .unwrap_or(rule_id)
        .to_string();
    let message = optional_str(finding, &["message", "description"])
        .unwrap_or(&title)
        .to_string();
    let severity = normalize_severity(optional_str(finding, &["severity"]).unwrap_or("WARNING"));
    let confidence =
        normalize_confidence(optional_str(finding, &["confidence"]).unwrap_or("MEDIUM"));
    let cwe = string_list(finding.get("cwe"));
    let cve = string_list(finding.get("cve"));
    let function_name = optional_str(finding, &["function", "function_name"]).map(str::to_string);
    let (resolved_path, resolved_line) = path_utils::resolve_scan_finding_location(
        Some(raw_file_path),
        Some(start_line_value),
        project_root,
        known_paths,
    );
    let display_path = resolved_path.as_deref().unwrap_or(raw_file_path);
    let finding_id = optional_str(finding, &["id"])
        .filter(|value| !value.trim().is_empty())
        .map(|value| format!("joern-finding-{value}"))
        .unwrap_or_else(|| format!("joern-finding-{}", Uuid::new_v4()));

    let payload = json!({
        "id": finding_id,
        "scan_task_id": task_id,
        "engine": JOERN_ENGINE,
        "rule": { "id": rule_id },
        "rule_name": rule_id,
        "title": title,
        "description": message,
        "message": message,
        "file_path": display_path,
        "raw_file_path": raw_file_path,
        "start_line": start_line,
        "end_line": end_line,
        "resolved_file_path": resolved_path,
        "resolved_line_start": resolved_line,
        "function": function_name,
        "severity": severity,
        "confidence": confidence,
        "status": "open",
        "cwe": cwe,
        "cve": cve,
        "raw_joern": finding,
    });

    Ok(task_state::StaticFindingRecord {
        id: finding_id,
        scan_task_id: task_id.to_string(),
        status: "open".to_string(),
        payload,
    })
}

fn required_str<'a>(value: &'a Value, keys: &[&str]) -> Result<&'a str> {
    optional_str(value, keys)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| anyhow!("joern finding missing required field: {}", keys.join("/")))
}

fn optional_str<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .find_map(|key| value.get(*key).and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn string_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| item.as_str().map(str::trim))
            .filter(|item| !item.is_empty())
            .map(str::to_string)
            .collect(),
        Some(Value::String(item)) => {
            let trimmed = item.trim();
            if trimmed.is_empty() {
                Vec::new()
            } else {
                vec![trimmed.to_string()]
            }
        }
        _ => Vec::new(),
    }
}

fn normalize_severity(value: &str) -> &'static str {
    match value.trim().to_ascii_uppercase().as_str() {
        "CRITICAL" | "HIGH" | "ERROR" => "ERROR",
        "LOW" | "INFO" | "INFORMATIONAL" => "INFO",
        _ => "WARNING",
    }
}

fn normalize_confidence(value: &str) -> &'static str {
    match value.trim().to_ascii_uppercase().as_str() {
        "HIGH" => "HIGH",
        "LOW" => "LOW",
        _ => "MEDIUM",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn valid_graph_proof() -> Value {
        json!({
            "schema_version": "argus.joern.graph-proof.v1",
            "files": ["src/bplist.c"],
            "functions": ["parse_string_node"]
        })
    }

    fn valid_findings() -> Value {
        json!({
            "findings": [{
                "id": "cve-2017-6439",
                "rule_id": "joern-c-buffer-overflow-libplist-cve-2017-6439",
                "title": "libplist parse_string_node buffer overflow",
                "message": "Potential buffer overflow in parse_string_node",
                "severity": "HIGH",
                "confidence": "HIGH",
                "file_path": "/work/src/bplist.c",
                "start_line": 721,
                "end_line": 734,
                "function": "parse_string_node",
                "cwe": ["CWE-120"],
                "cve": ["CVE-2017-6439"],
                "evidence": {"sink": "memcpy"}
            }]
        })
    }

    #[tokio::test]
    async fn parse_output_dir_maps_valid_joern_artifacts_to_static_findings() {
        let temp = TempDir::new().expect("temp dir");
        let output = temp.path();
        fs::write(
            output.join("summary.json"),
            r#"{"status":"scan_completed","scanner":"joern"}"#,
        )
        .await
        .unwrap();
        fs::write(
            output.join("graph-proof.json"),
            valid_graph_proof().to_string(),
        )
        .await
        .unwrap();
        fs::write(output.join("findings.json"), valid_findings().to_string())
            .await
            .unwrap();
        let known_paths = BTreeSet::from(["src/bplist.c".to_string()]);

        let parsed = parse_output_dir(output, "task-1", Some("/work"), Some(&known_paths), 4096)
            .await
            .expect("parse joern output");

        assert_eq!(parsed.findings.len(), 1);
        assert_eq!(parsed.graph_proof["functions"][0], "parse_string_node");
        assert_eq!(parsed.summary["scanner"], "joern");
        let payload = &parsed.findings[0].payload;
        assert_eq!(payload["engine"], "joern");
        assert_eq!(
            payload["rule"]["id"],
            "joern-c-buffer-overflow-libplist-cve-2017-6439"
        );
        assert_eq!(payload["severity"], "ERROR");
        assert_eq!(payload["confidence"], "HIGH");
        assert_eq!(payload["file_path"], "src/bplist.c");
        assert_eq!(payload["start_line"], 721);
        assert_eq!(payload["function"], "parse_string_node");
        assert_eq!(payload["cwe"][0], "CWE-120");
        assert_eq!(payload["cve"][0], "CVE-2017-6439");
        assert_eq!(payload["raw_joern"]["evidence"]["sink"], "memcpy");
    }

    #[tokio::test]
    async fn parse_output_dir_accepts_empty_findings_with_graph_proof() {
        let temp = TempDir::new().expect("temp dir");
        let output = temp.path();
        fs::write(
            output.join("summary.json"),
            r#"{"status":"scan_completed"}"#,
        )
        .await
        .unwrap();
        fs::write(
            output.join("graph-proof.json"),
            valid_graph_proof().to_string(),
        )
        .await
        .unwrap();
        fs::write(output.join("findings.json"), r#"{"findings":[]}"#)
            .await
            .unwrap();

        let parsed = parse_output_dir(output, "task-1", None, None, 4096)
            .await
            .expect("parse empty joern output");
        assert!(parsed.findings.is_empty());
    }

    #[tokio::test]
    async fn parse_output_dir_requires_graph_proof() {
        let temp = TempDir::new().expect("temp dir");
        let output = temp.path();
        fs::write(
            output.join("summary.json"),
            r#"{"status":"scan_completed"}"#,
        )
        .await
        .unwrap();
        fs::write(output.join("findings.json"), valid_findings().to_string())
            .await
            .unwrap();

        let error = parse_output_dir(output, "task-1", None, None, 4096)
            .await
            .expect_err("missing graph proof should fail")
            .to_string();
        assert!(error.contains("graph-proof.json"), "{error}");
    }

    #[tokio::test]
    async fn parse_output_dir_rejects_malformed_findings_json() {
        let temp = TempDir::new().expect("temp dir");
        let output = temp.path();
        fs::write(
            output.join("summary.json"),
            r#"{"status":"scan_completed"}"#,
        )
        .await
        .unwrap();
        fs::write(
            output.join("graph-proof.json"),
            valid_graph_proof().to_string(),
        )
        .await
        .unwrap();
        fs::write(output.join("findings.json"), r#"{"findings":"not-array"}"#)
            .await
            .unwrap();

        let error = parse_output_dir(output, "task-1", None, None, 4096)
            .await
            .expect_err("malformed findings should fail")
            .to_string();
        assert!(error.contains("findings array"), "{error}");
    }

    #[tokio::test]
    async fn read_json_file_rejects_oversize_artifact() {
        let temp = TempDir::new().expect("temp dir");
        let path = temp.path().join("findings.json");
        fs::write(&path, r#"{"findings":[]}"#).await.unwrap();

        let error = read_json_file(&path, 4)
            .await
            .expect_err("oversize should fail")
            .to_string();
        assert!(error.contains("JOERN_RESULTS_JSON_LIMIT_BYTES"), "{error}");
    }

    #[test]
    fn build_wrapper_script_declares_stable_output_contract_and_docs_are_recorded() {
        let paths = JoernOutputPaths::default();
        let script = build_wrapper_script(&paths);
        assert!(script.contains("joern-parse \"$SOURCE_DIR\" --out \"$CPG_PATH\""));
        assert!(script.contains("joern --script \"$QUERY_DIR/c/argus-joern-scan.sc\""));
        assert!(script.contains("graph-proof.json"));
        assert!(script.contains("findings.json"));
        assert!(script.contains("summary.json"));
        assert!(script.contains("joern.log"));
        let evidence = docs_evidence();
        assert!(evidence
            .image_source
            .contains("ghcr.nju.edu.cn/joernio/joern:nightly"));
        assert!(evidence.parse_command_source.contains("joern-parse"));
        assert!(evidence.script_output_source.contains("--script"));
        assert!(evidence.scan_result_source.contains("Result:"));
    }
}
