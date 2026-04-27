use std::path::{Component, Path};

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::db::task_state::{
    AgentCheckpointRecord, AgentEventRecord, AgentFindingRecord, AgentTaskRecord,
};

pub const FORBIDDEN_STATIC_FIELDS: &[&str] = &[
    "static_task_id",
    "opengrep_task_id",
    "candidate_finding_ids",
    "static_findings",
    "bootstrap_task_id",
    "bootstrap_candidate_count",
    "candidate_findings",
];

pub const FORBIDDEN_STATIC_ORIGINS: &[&str] =
    &["opengrep", "static", "bandit", "gitleaks", "phpstan", "pmd"];

const SENSITIVE_KEYS: &[&str] = &[
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "customheaders",
    "custom_headers",
    "llmapikey",
    "llm_api_key",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportError {
    pub reason_code: &'static str,
    pub message: String,
}

impl ImportError {
    fn new(reason_code: &'static str, message: impl Into<String>) -> Self {
        Self {
            reason_code,
            message: message.into(),
        }
    }
}

pub type ImportResult<T> = Result<T, ImportError>;

pub fn validate_no_static_candidates(value: &Value) -> ImportResult<()> {
    let mut violations = Vec::new();
    collect_static_candidate_violations(value, "$", &mut violations);
    if violations.is_empty() {
        Ok(())
    } else {
        Err(ImportError::new(
            "forbidden_static_input",
            format!(
                "智能审计禁止使用静态扫描候选输入：{}",
                violations.join(", ")
            ),
        ))
    }
}

fn collect_static_candidate_violations(value: &Value, path: &str, violations: &mut Vec<String>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                let lower_key = key.to_ascii_lowercase();
                let child_path = format!("{path}.{key}");
                if FORBIDDEN_STATIC_FIELDS.contains(&lower_key.as_str()) {
                    violations.push(child_path.clone());
                }
                if matches!(
                    lower_key.as_str(),
                    "candidate_origin" | "source_engine" | "origin" | "engine"
                ) {
                    if let Some(origin) = child.as_str() {
                        let normalized = origin.to_ascii_lowercase();
                        if FORBIDDEN_STATIC_ORIGINS.contains(&normalized.as_str()) {
                            violations.push(format!("{child_path}={origin}"));
                        }
                    }
                }
                if lower_key.contains("static")
                    && (lower_key.contains("finding")
                        || lower_key.contains("scan")
                        || lower_key.contains("candidate"))
                {
                    violations.push(child_path.clone());
                }
                collect_static_candidate_violations(child, &child_path, violations);
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                collect_static_candidate_violations(child, &format!("{path}[{index}]"), violations);
            }
        }
        Value::String(text) => {
            let lower = text.to_ascii_lowercase();
            if lower.contains("static finding") || lower.contains("static scan") {
                violations.push(format!("{path}=<static-scan-text>"));
            }
        }
        _ => {}
    }
}

pub fn sanitize_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let sanitized = map
                .iter()
                .map(|(key, child)| {
                    let normalized = key.replace('-', "_").to_ascii_lowercase();
                    if SENSITIVE_KEYS.contains(&normalized.as_str()) {
                        (key.clone(), Value::String("[REDACTED]".to_string()))
                    } else {
                        (key.clone(), sanitize_value(child))
                    }
                })
                .collect::<Map<_, _>>();
            Value::Object(sanitized)
        }
        Value::Array(items) => Value::Array(items.iter().map(sanitize_value).collect()),
        Value::String(text) => Value::String(redact_text(text)),
        _ => value.clone(),
    }
}

pub fn redact_text(text: &str) -> String {
    let mut redacted = text.to_string();
    for marker in [
        "Authorization:",
        "authorization:",
        "Cookie:",
        "cookie:",
        "apiKey=",
        "api_key=",
    ] {
        redacted = redact_marker_values(&redacted, marker);
    }
    redacted = redacted.replace("/var/run/docker.sock", "[REDACTED_DOCKER_SOCKET]");
    redacted
}

fn redact_marker_values(text: &str, marker: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut remaining = text;
    while let Some(start) = remaining.find(marker) {
        output.push_str(&remaining[..start + marker.len()]);
        let value = &remaining[start + marker.len()..];
        let whitespace_len = value.len() - value.trim_start().len();
        output.push_str(&value[..whitespace_len]);
        output.push_str("[REDACTED]");
        let token = &value[whitespace_len..];
        let end = token
            .find(|c: char| c.is_whitespace() || c == '&' || c == ',' || c == ';')
            .unwrap_or(token.len());
        remaining = &token[end..];
    }
    output.push_str(remaining);
    output
}

pub fn validate_relative_artifact_path(path: &str) -> ImportResult<()> {
    let candidate = Path::new(path);
    if candidate.is_absolute() {
        return Err(ImportError::new(
            "runner_output_invalid",
            format!("artifact path must be relative: {path}"),
        ));
    }
    if candidate.components().any(|component| {
        matches!(
            component,
            Component::ParentDir | Component::RootDir | Component::Prefix(_)
        )
    }) {
        return Err(ImportError::new(
            "runner_output_invalid",
            format!("artifact path escapes task output directory: {path}"),
        ));
    }
    let lower = path.to_ascii_lowercase();
    if lower.contains("docker.sock") || lower.contains("/var/run") || lower.contains("/run/docker")
    {
        return Err(ImportError::new(
            "runner_output_invalid",
            format!("artifact path points at a forbidden host runtime path: {path}"),
        ));
    }
    Ok(())
}

pub fn import_runner_output(record: &mut AgentTaskRecord, raw_output: &Value) -> ImportResult<()> {
    validate_no_static_candidates(raw_output)?;
    reject_native_only_output(raw_output)?;
    let output = sanitize_value(raw_output);
    if output.get("runtime").and_then(Value::as_str) != Some("agentflow") {
        return Err(ImportError::new(
            "runner_output_invalid",
            "runner output runtime must be `agentflow`",
        ));
    }
    let run_id = required_string(&output, "run_id")?;
    let topology_version = output
        .get("topology_version")
        .and_then(Value::as_str)
        .unwrap_or("agentflow-p1-v1");
    validate_artifacts(&output)?;

    let now = now_rfc3339();
    record.status = "completed".to_string();
    record.current_phase = Some("completed".to_string());
    record.current_step = Some("AgentFlow runner output imported".to_string());
    record.completed_at = Some(now.clone());
    record.progress_percentage = 100.0;

    merge_agentflow_scope(record, &run_id, topology_version, &output);
    import_events(record, &output, topology_version);
    import_checkpoints(record, &output, topology_version);
    import_findings(record, &output)?;
    record.agent_tree = output
        .get("agent_tree")
        .or_else(|| output.get("nodes"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_else(|| default_agent_tree(record, topology_version));
    record.report = output
        .get("report")
        .and_then(|report| {
            report
                .get("summary_markdown")
                .or_else(|| report.get("summary"))
        })
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .or_else(|| Some("# AgentFlow 智能审计报告\n\n未发现可确认漏洞。".to_string()));
    refresh_aggregates(record);
    push_import_event(
        record,
        "report_generated",
        Some("completed"),
        Some("AgentFlow 智能审计结果已导入 Argus"),
        Some(json!({
            "runtime": "agentflow",
            "run_id": run_id,
            "topology_version": topology_version,
        })),
    );
    Ok(())
}

fn reject_native_only_output(output: &Value) -> ImportResult<()> {
    let has_argus_business_shape = output.get("runtime").and_then(Value::as_str)
        == Some("agentflow")
        && (output.get("findings").is_some()
            || output.get("report").is_some()
            || output.get("events").is_some());
    let native_only = output.get("pipeline").is_some()
        && output.get("nodes").is_some()
        && output.get("findings").is_none()
        && output.get("report").is_none();
    if !has_argus_business_shape || native_only {
        return Err(ImportError::new(
            "runner_output_invalid",
            "AgentFlow native RunRecord/RunEvent/NodeResult cannot be imported directly as Argus findings",
        ));
    }
    Ok(())
}

fn required_string(value: &Value, key: &'static str) -> ImportResult<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
        .ok_or_else(|| {
            ImportError::new(
                "runner_output_invalid",
                format!("runner output missing `{key}`"),
            )
        })
}

fn validate_artifacts(output: &Value) -> ImportResult<()> {
    if let Some(artifacts) = output.get("artifact_index").and_then(Value::as_array) {
        for artifact in artifacts {
            if let Some(path) = artifact.get("path").and_then(Value::as_str) {
                validate_relative_artifact_path(path)?;
            }
        }
    }
    Ok(())
}

fn merge_agentflow_scope(
    record: &mut AgentTaskRecord,
    run_id: &str,
    topology_version: &str,
    output: &Value,
) {
    let mut scope = record.audit_scope.clone().unwrap_or_else(|| json!({}));
    if !scope.is_object() {
        scope = json!({ "value": scope });
    }
    let obj = scope.as_object_mut().expect("scope normalized as object");
    obj.insert(
        "agentflow".to_string(),
        json!({
            "runtime": "agentflow",
            "run_id": run_id,
            "topology_version": topology_version,
            "input_digest": output.get("input_digest").cloned().unwrap_or(Value::Null),
            "artifact_index": output.get("artifact_index").cloned().unwrap_or_else(|| json!([])),
            "report_snapshot": output.get("report").cloned().unwrap_or(Value::Null),
            "diagnostics": output.get("diagnostics").cloned().unwrap_or(Value::Null),
        }),
    );
    record.audit_scope = Some(scope);
}

fn import_events(record: &mut AgentTaskRecord, output: &Value, topology_version: &str) {
    if let Some(events) = output.get("events").and_then(Value::as_array) {
        for event in events {
            let event_type = event
                .get("type")
                .or_else(|| event.get("event_type"))
                .and_then(Value::as_str)
                .unwrap_or("agentflow_event");
            let phase = event.get("phase").and_then(Value::as_str);
            let message = event.get("message").and_then(Value::as_str);
            let mut metadata = event.get("metadata").cloned().unwrap_or_else(|| json!({}));
            if let Some(obj) = metadata.as_object_mut() {
                obj.insert("topology_version".to_string(), json!(topology_version));
                obj.insert(
                    "role".to_string(),
                    event.get("role").cloned().unwrap_or(Value::Null),
                );
                obj.insert("visibility".to_string(), json!("user"));
                obj.insert(
                    "correlation_id".to_string(),
                    json!(Uuid::new_v4().to_string()),
                );
            }
            push_import_event(record, event_type, phase, message, Some(metadata));
        }
    }
}

fn import_checkpoints(record: &mut AgentTaskRecord, output: &Value, topology_version: &str) {
    if let Some(checkpoints) = output.get("checkpoints").and_then(Value::as_array) {
        for checkpoint in checkpoints {
            record.checkpoints.push(AgentCheckpointRecord {
                id: checkpoint
                    .get("id")
                    .and_then(Value::as_str)
                    .map(ToString::to_string)
                    .unwrap_or_else(|| Uuid::new_v4().to_string()),
                task_id: record.id.clone(),
                agent_id: checkpoint
                    .get("agent_id")
                    .and_then(Value::as_str)
                    .unwrap_or("agentflow")
                    .to_string(),
                agent_name: checkpoint
                    .get("agent_name")
                    .and_then(Value::as_str)
                    .unwrap_or("AgentFlow")
                    .to_string(),
                agent_type: checkpoint
                    .get("role")
                    .or_else(|| checkpoint.get("agent_type"))
                    .and_then(Value::as_str)
                    .unwrap_or("agentflow")
                    .to_string(),
                parent_agent_id: checkpoint
                    .get("parent_agent_id")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                iteration: checkpoint
                    .get("iteration")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                status: checkpoint
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("completed")
                    .to_string(),
                total_tokens: checkpoint
                    .get("tokens_used")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                tool_calls: checkpoint
                    .get("tool_calls")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                findings_count: checkpoint
                    .get("findings_count")
                    .and_then(Value::as_i64)
                    .unwrap_or(0),
                checkpoint_type: checkpoint
                    .get("type")
                    .or_else(|| checkpoint.get("checkpoint_type"))
                    .and_then(Value::as_str)
                    .unwrap_or("agentflow")
                    .to_string(),
                checkpoint_name: checkpoint
                    .get("name")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                created_at: checkpoint
                    .get("created_at")
                    .and_then(Value::as_str)
                    .map(ToString::to_string)
                    .or_else(|| Some(now_rfc3339())),
                state_data: checkpoint
                    .get("state_data")
                    .cloned()
                    .unwrap_or_else(|| json!({"topology_version": topology_version})),
                metadata: Some(
                    json!({"source": "agentflow", "topology_version": topology_version}),
                ),
            });
        }
    }
}

fn import_findings(record: &mut AgentTaskRecord, output: &Value) -> ImportResult<()> {
    record.findings.clear();
    if let Some(findings) = output.get("findings").and_then(Value::as_array) {
        for finding in findings {
            validate_no_static_candidates(finding)?;
            let id = finding
                .get("id")
                .and_then(Value::as_str)
                .map(ToString::to_string)
                .unwrap_or_else(|| Uuid::new_v4().to_string());
            record.findings.push(AgentFindingRecord {
                id,
                task_id: record.id.clone(),
                vulnerability_type: finding
                    .get("vulnerability_type")
                    .or_else(|| finding.get("type"))
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
                    .to_string(),
                severity: finding
                    .get("severity")
                    .and_then(Value::as_str)
                    .unwrap_or("medium")
                    .to_string(),
                title: finding
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("AgentFlow finding")
                    .to_string(),
                display_title: finding
                    .get("display_title")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                description: finding
                    .get("description")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                description_markdown: finding
                    .get("description_markdown")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                file_path: finding
                    .get("file_path")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                line_start: finding.get("line_start").and_then(Value::as_i64),
                line_end: finding.get("line_end").and_then(Value::as_i64),
                resolved_file_path: finding
                    .get("resolved_file_path")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                resolved_line_start: finding.get("resolved_line_start").and_then(Value::as_i64),
                code_snippet: finding
                    .get("code_snippet")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                code_context: finding
                    .get("code_context")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                cwe_id: finding
                    .get("cwe_id")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                cwe_name: finding
                    .get("cwe_name")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                context_start_line: finding.get("context_start_line").and_then(Value::as_i64),
                context_end_line: finding.get("context_end_line").and_then(Value::as_i64),
                status: finding
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("verified")
                    .to_string(),
                is_verified: finding
                    .get("is_verified")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
                verdict: finding
                    .get("verdict")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                reachability: finding
                    .get("reachability")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                authenticity: finding
                    .get("authenticity")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                verification_evidence: finding
                    .get("verification_evidence")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                verification_todo_id: finding
                    .get("verification_todo_id")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                verification_fingerprint: finding
                    .get("verification_fingerprint")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                reachability_file: finding
                    .get("reachability_file")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                reachability_function: finding
                    .get("reachability_function")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                reachability_function_start_line: finding
                    .get("reachability_function_start_line")
                    .and_then(Value::as_i64),
                reachability_function_end_line: finding
                    .get("reachability_function_end_line")
                    .and_then(Value::as_i64),
                flow_path_score: finding.get("flow_path_score").and_then(Value::as_f64),
                flow_call_chain: string_vec(finding.get("flow_call_chain")),
                function_trigger_flow: string_vec(finding.get("function_trigger_flow")),
                flow_control_conditions: string_vec(finding.get("flow_control_conditions")),
                logic_authz_evidence: string_vec(finding.get("logic_authz_evidence")),
                has_poc: finding
                    .get("has_poc")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                poc_code: finding
                    .get("poc_code")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                trigger_flow: finding.get("trigger_flow").cloned(),
                poc_trigger_chain: finding.get("poc_trigger_chain").cloned(),
                suggestion: finding
                    .get("suggestion")
                    .or_else(|| finding.get("remediation"))
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                fix_code: finding
                    .get("fix_code")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                report: finding
                    .get("report")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                ai_explanation: finding
                    .get("ai_explanation")
                    .and_then(Value::as_str)
                    .map(ToString::to_string),
                ai_confidence: finding.get("ai_confidence").and_then(Value::as_f64),
                confidence: finding.get("confidence").and_then(Value::as_f64),
                created_at: finding
                    .get("created_at")
                    .and_then(Value::as_str)
                    .map(ToString::to_string)
                    .unwrap_or_else(now_rfc3339),
            });
        }
    }
    Ok(())
}

fn string_vec(value: Option<&Value>) -> Option<Vec<String>> {
    value.and_then(Value::as_array).map(|items| {
        items
            .iter()
            .filter_map(Value::as_str)
            .map(ToString::to_string)
            .collect()
    })
}

fn default_agent_tree(record: &AgentTaskRecord, topology_version: &str) -> Vec<Value> {
    vec![json!({
        "id": format!("agentflow-{}", record.id),
        "agent_id": format!("agentflow-{}", record.id),
        "agent_name": "AgentFlow P1 Pipeline",
        "agent_type": "agentflow",
        "role": "audit-reporter",
        "topology_version": topology_version,
        "status": "completed",
        "result_summary": record.report.clone().unwrap_or_default(),
        "findings_count": record.findings.len(),
        "children": [],
    })]
}

fn refresh_aggregates(record: &mut AgentTaskRecord) {
    record.findings_count = record.findings.len() as i64;
    record.verified_count = record
        .findings
        .iter()
        .filter(|finding| finding.is_verified)
        .count() as i64;
    record.critical_count = count_severity(record, "critical");
    record.high_count = count_severity(record, "high");
    record.medium_count = count_severity(record, "medium");
    record.low_count = count_severity(record, "low");
    record.verified_critical_count = count_verified_severity(record, "critical");
    record.verified_high_count = count_verified_severity(record, "high");
    record.verified_medium_count = count_verified_severity(record, "medium");
    record.verified_low_count = count_verified_severity(record, "low");
    record.security_score = Some(
        (100.0
            - (record.critical_count * 20
                + record.high_count * 12
                + record.medium_count * 6
                + record.low_count * 2) as f64)
            .max(0.0),
    );
}

fn count_severity(record: &AgentTaskRecord, severity: &str) -> i64 {
    record
        .findings
        .iter()
        .filter(|finding| finding.severity.eq_ignore_ascii_case(severity))
        .count() as i64
}

fn count_verified_severity(record: &AgentTaskRecord, severity: &str) -> i64 {
    record
        .findings
        .iter()
        .filter(|finding| finding.is_verified && finding.severity.eq_ignore_ascii_case(severity))
        .count() as i64
}

fn push_import_event(
    record: &mut AgentTaskRecord,
    event_type: &str,
    phase: Option<&str>,
    message: Option<&str>,
    metadata: Option<Value>,
) {
    record.events.push(AgentEventRecord {
        id: Uuid::new_v4().to_string(),
        task_id: record.id.clone(),
        event_type: event_type.to_string(),
        phase: phase.map(ToString::to_string),
        message: message.map(ToString::to_string),
        tool_name: None,
        tool_input: None,
        tool_output: None,
        tool_duration_ms: None,
        finding_id: None,
        tokens_used: None,
        metadata,
        sequence: record.events.len() as i64 + 1,
        timestamp: now_rfc3339(),
    });
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record() -> AgentTaskRecord {
        AgentTaskRecord {
            id: "task-1".to_string(),
            project_id: "project-1".to_string(),
            name: None,
            description: None,
            task_type: "agent_audit".to_string(),
            status: "running".to_string(),
            current_phase: None,
            current_step: None,
            total_files: 0,
            indexed_files: 0,
            analyzed_files: 0,
            files_with_findings: 0,
            total_chunks: 0,
            findings_count: 0,
            verified_count: 0,
            false_positive_count: 0,
            total_iterations: 1,
            tool_calls_count: 0,
            tokens_used: 0,
            critical_count: 0,
            high_count: 0,
            medium_count: 0,
            low_count: 0,
            verified_critical_count: 0,
            verified_high_count: 0,
            verified_medium_count: 0,
            verified_low_count: 0,
            quality_score: 0.0,
            security_score: Some(0.0),
            created_at: "2026-01-01T00:00:00Z".to_string(),
            started_at: Some("2026-01-01T00:00:01Z".to_string()),
            completed_at: None,
            progress_percentage: 0.0,
            audit_scope: Some(json!({})),
            target_vulnerabilities: None,
            verification_level: None,
            tool_evidence_protocol: None,
            exclude_patterns: None,
            target_files: None,
            error_message: None,
            report: None,
            events: Vec::new(),
            findings: Vec::new(),
            checkpoints: Vec::new(),
            agent_tree: Vec::new(),
        }
    }

    #[test]
    fn agentflow_importer_rejects_forbidden_static_candidate_fields_and_engines() {
        let payload = json!({
            "runtime": "agentflow",
            "run_id": "run-1",
            "findings": [{"title": "bad", "candidate_origin": "opengrep"}],
            "audit_scope": {"static_task_id": "static-1"}
        });
        let error = validate_no_static_candidates(&payload).unwrap_err();
        assert_eq!(error.reason_code, "forbidden_static_input");
        assert!(error.message.contains("static_task_id"));
        assert!(error.message.contains("opengrep"));
    }

    #[test]
    fn agentflow_importer_rejects_native_runrecord_only_payload() {
        let native = json!({
            "id": "run-1",
            "status": "completed",
            "pipeline": {"nodes": []},
            "nodes": []
        });
        let mut record = record();
        let error = import_runner_output(&mut record, &native).unwrap_err();
        assert_eq!(error.reason_code, "runner_output_invalid");
    }

    #[test]
    fn agentflow_importer_rejects_artifact_path_traversal_and_socket_refs() {
        assert!(validate_relative_artifact_path("reports/summary.md").is_ok());
        assert!(validate_relative_artifact_path("../secret").is_err());
        assert!(validate_relative_artifact_path("/var/run/docker.sock").is_err());
        assert!(validate_relative_artifact_path("run/docker.sock").is_err());
    }

    #[test]
    fn agentflow_importer_redacts_sensitive_values_before_state_import() {
        let mut record = record();
        let output = json!({
            "runtime": "agentflow",
            "run_id": "run-1",
            "events": [{"type": "runner_log", "message": "Authorization: Bearer-secret"}],
            "diagnostics": {"apiKey": "sk-secret", "stderr_tail": "Cookie: abc /var/run/docker.sock"},
            "artifact_index": [{"path": "reports/summary.md"}],
            "findings": [],
            "report": {"summary_markdown": "# OK"}
        });
        import_runner_output(&mut record, &output).unwrap();
        let scope = serde_json::to_string(&record.audit_scope).unwrap();
        assert!(!scope.contains("sk-secret"));
        assert!(!scope.contains("/var/run/docker.sock"));
        assert!(scope.contains("[REDACTED]"));
    }

    #[test]
    fn agentflow_importer_maps_business_output_into_argus_task_state() {
        let mut record = record();
        let output = json!({
            "runtime": "agentflow",
            "run_id": "run-1",
            "topology_version": "agentflow-p1-v1",
            "artifact_index": [{"path": "reports/summary.md", "sha256": sha256_hex(b"ok")}],
            "agent_tree": [{"agent_id": "report", "role": "audit-reporter", "status": "completed"}],
            "events": [{"type": "node_completed", "role": "audit-reporter", "message": "done"}],
            "checkpoints": [{"agent_id": "report", "role": "audit-reporter", "status": "completed", "type": "completed"}],
            "findings": [{
                "id": "finding-1",
                "vulnerability_type": "path_traversal",
                "severity": "high",
                "title": "unsafe path join",
                "file_path": "src/main.rs",
                "line_start": 12,
                "confidence": 0.91,
                "remediation": "normalize paths"
            }],
            "report": {"summary_markdown": "# Report"}
        });
        import_runner_output(&mut record, &output).unwrap();
        assert_eq!(record.status, "completed");
        assert_eq!(record.findings_count, 1);
        assert_eq!(record.high_count, 1);
        assert_eq!(
            record.findings[0].suggestion.as_deref(),
            Some("normalize paths")
        );
        assert!(record.audit_scope.unwrap()["agentflow"]["run_id"] == "run-1");
    }
}
