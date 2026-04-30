use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

pub const ARGUS_AGENTFLOW_CONTRACT_VERSION: &str = "argus-agentflow-p1/v1";
pub const P1_TOPOLOGY_VERSION: &str = "p1-fixed-dag-v1";
pub const DEFAULT_STDIO_TAIL_BYTES: u64 = 64 * 1024;

pub const P1_ALLOWED_TARGETS: &[&str] = &["local", "container"];
pub const P1_REQUIRED_ROLES: &[&str] = &["env-inter", "vuln-reasoner", "audit-reporter"];

pub const FORBIDDEN_STATIC_INPUT_KEYS: &[&str] = &[
    "static_task_id",
    "opengrep_task_id",
    "candidate_finding_ids",
    "static_findings",
    "bootstrap_task_id",
    "bootstrap_candidate_count",
    "candidate_findings",
];

pub const FORBIDDEN_STATIC_ORIGIN_VALUES: &[&str] =
    &["opengrep", "static", "bandit", "gitleaks", "phpstan", "pmd"];

pub const FORBIDDEN_STATIC_ORIGIN_KEYS: &[&str] = &["candidate_origin", "source_engine"];

pub const SENSITIVE_CONFIG_KEYS: &[&str] = &[
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "customheaders",
    "custom_headers",
];

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowTargetKind {
    Local,
    Container,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowVerificationLevel {
    Basic,
    Standard,
    Strict,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowSeverity {
    Critical,
    High,
    Medium,
    Low,
    Info,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowTaskStatus {
    Queued,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowVisibility {
    #[serde(alias = "ALL", alias = "all")]
    User,
    #[serde(alias = "ORCHESTRATOR_ONLY", alias = "orchestrator_only")]
    Diagnostic,
    #[serde(alias = "AGENTS_ONLY", alias = "agents_only")]
    Internal,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentflowCheckpointStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ArgusAgentflowRunnerInput {
    pub contract_version: String,
    pub task_id: String,
    pub project_id: String,
    pub project_root: String,
    pub target: AgentflowTargetKind,
    pub topology_version: String,
    pub audit_scope: AgentflowAuditScope,
    pub output_dir: String,
    pub llm: AgentflowLlmConfig,
    pub resource_budget: AgentflowResourceBudget,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

impl ArgusAgentflowRunnerInput {
    pub fn forbidden_static_inputs(&self) -> Vec<ForbiddenStaticInput> {
        let mut findings =
            forbidden_static_inputs_in_value(&serde_json::to_value(self).unwrap_or(Value::Null));
        findings.sort();
        findings.dedup();
        findings
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowAuditScope {
    #[serde(default)]
    pub target_files: Vec<String>,
    #[serde(default)]
    pub exclude_patterns: Vec<String>,
    #[serde(default)]
    pub target_vulnerabilities: Vec<String>,
    pub verification_level: AgentflowVerificationLevel,
    #[serde(default)]
    pub prompt_skill: Option<String>,
    #[serde(default)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowLlmConfig {
    pub provider: String,
    pub model: String,
    #[serde(default)]
    pub base_url: Option<String>,
    #[serde(default)]
    pub api_key_ref: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wire_api: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub api_key_env: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowResourceBudget {
    pub max_cpu_cores: f64,
    pub max_memory_mb: u64,
    pub max_duration_seconds: u64,
    pub max_concurrency: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ArgusAgentflowRunnerOutput {
    pub contract_version: String,
    pub task_id: String,
    pub run: AgentflowRunSummary,
    #[serde(default)]
    pub events: Vec<AgentflowEventEnvelope>,
    #[serde(default)]
    pub checkpoints: Vec<AgentflowCheckpoint>,
    #[serde(default)]
    pub findings: Vec<AgentflowFinding>,
    pub report: AgentflowReport,
    #[serde(default)]
    pub agent_tree: Vec<AgentflowAgentTreeNode>,
    #[serde(default)]
    pub artifacts: Vec<AgentflowArtifactRef>,
    #[serde(default)]
    pub artifact_index: Vec<AgentflowArtifactRef>,
    #[serde(default)]
    pub feedback_bundle: Option<Value>,
    #[serde(default)]
    pub diagnostics: AgentflowDiagnostics,
}

impl ArgusAgentflowRunnerOutput {
    pub fn forbidden_static_inputs(&self) -> Vec<ForbiddenStaticInput> {
        let mut findings =
            forbidden_static_inputs_in_value(&serde_json::to_value(self).unwrap_or(Value::Null));
        findings.sort();
        findings.dedup();
        findings
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowRunSummary {
    pub run_id: String,
    pub status: AgentflowTaskStatus,
    pub topology_version: String,
    #[serde(default)]
    pub topology_change: Option<Value>,
    #[serde(default)]
    pub started_at: Option<String>,
    #[serde(default)]
    pub finished_at: Option<String>,
    #[serde(default)]
    pub input_digest: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowEventEnvelope {
    pub id: String,
    pub sequence: i64,
    pub timestamp: String,
    pub event_type: String,
    pub role: String,
    pub visibility: AgentflowVisibility,
    pub correlation_id: String,
    pub topology_version: String,
    #[serde(default)]
    pub node_id: Option<String>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub data: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowCheckpoint {
    pub id: String,
    pub agent_id: String,
    pub agent_name: String,
    pub agent_type: String,
    pub role: String,
    pub status: AgentflowCheckpointStatus,
    pub checkpoint_type: String,
    pub topology_version: String,
    #[serde(default)]
    pub parent_agent_id: Option<String>,
    #[serde(default)]
    pub iteration: i64,
    #[serde(default)]
    pub total_tokens: i64,
    #[serde(default)]
    pub tool_calls: i64,
    #[serde(default)]
    pub findings_count: i64,
    #[serde(default)]
    pub created_at: Option<String>,
    #[serde(default)]
    pub state_data: BTreeMap<String, Value>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowFinding {
    pub id: String,
    pub vulnerability_type: String,
    pub severity: AgentflowSeverity,
    pub title: String,
    pub status: String,
    pub is_verified: bool,
    pub source: AgentflowFindingSource,
    #[serde(default)]
    pub discard_reason: Option<String>,
    #[serde(default)]
    pub location: Option<AgentflowFindingLocation>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub evidence: Option<String>,
    #[serde(default)]
    pub impact: Option<String>,
    #[serde(default)]
    pub remediation: Option<String>,
    #[serde(default)]
    pub verification: Option<String>,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default)]
    pub confidence_history: Vec<AgentflowConfidencePoint>,
    #[serde(default)]
    pub data_flow: Vec<String>,
    #[serde(default)]
    pub artifact_refs: Vec<String>,
    #[serde(default)]
    pub risk_lifecycle: Option<Value>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowFindingSource {
    pub node_id: String,
    pub node_role: String,
    pub agent_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowFindingLocation {
    pub file_path: String,
    #[serde(default)]
    pub line_start: Option<i64>,
    #[serde(default)]
    pub line_end: Option<i64>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowConfidencePoint {
    pub stage: String,
    pub confidence: f64,
    #[serde(default)]
    pub reason: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowReport {
    pub title: String,
    pub summary: String,
    #[serde(default)]
    pub markdown: Option<String>,
    #[serde(default)]
    pub verified_count: i64,
    #[serde(default)]
    pub findings_count: i64,
    #[serde(default)]
    pub severity_counts: BTreeMap<String, i64>,
    #[serde(default)]
    pub statistics: BTreeMap<String, Value>,
    #[serde(default)]
    pub sections: Vec<Value>,
    #[serde(default)]
    pub discard_summary: Option<Value>,
    #[serde(default)]
    pub timeline: Vec<Value>,
    #[serde(default)]
    pub artifact_index: Vec<AgentflowArtifactRef>,
    #[serde(default)]
    pub diagnostics: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AgentflowAgentTreeNode {
    pub id: String,
    pub role: String,
    pub label: String,
    pub status: AgentflowCheckpointStatus,
    pub topology_version: String,
    #[serde(default)]
    pub parent_id: Option<String>,
    #[serde(default)]
    pub duration_ms: Option<i64>,
    #[serde(default)]
    pub findings_count: i64,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowArtifactRef {
    pub id: String,
    pub path: String,
    pub artifact_type: String,
    pub size: u64,
    pub sha256: String,
    pub producer_node: String,
    pub created_at: String,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentflowDiagnostics {
    #[serde(default)]
    pub runner_exit_code: Option<i32>,
    #[serde(default)]
    pub resource_diagnostics: Option<Value>,
    #[serde(default)]
    pub dynamic_expert_diagnostics: Option<Value>,
    #[serde(default)]
    pub stdout_tail: Option<String>,
    #[serde(default)]
    pub stderr_tail: Option<String>,
    #[serde(default)]
    pub reason_code: Option<String>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub dynamic_experts_enabled: Option<bool>,
    #[serde(default)]
    pub remote_target_enabled: Option<bool>,
    #[serde(default)]
    pub agentflow_serve_enabled: Option<bool>,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ForbiddenStaticInput {
    pub path: String,
    pub key: String,
    pub value: Option<String>,
}

pub fn forbidden_static_inputs_in_value(value: &Value) -> Vec<ForbiddenStaticInput> {
    let mut findings = Vec::new();
    visit_forbidden_static_inputs(value, "$", &mut findings);
    findings
}

pub fn contains_forbidden_static_input(value: &Value) -> bool {
    !forbidden_static_inputs_in_value(value).is_empty()
}

fn visit_forbidden_static_inputs(
    value: &Value,
    path: &str,
    findings: &mut Vec<ForbiddenStaticInput>,
) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                let child_path = format_object_path(path, key);
                let normalized_key = normalize_contract_token(key);
                if FORBIDDEN_STATIC_INPUT_KEYS
                    .iter()
                    .any(|forbidden| normalize_contract_token(forbidden) == normalized_key)
                {
                    findings.push(ForbiddenStaticInput {
                        path: child_path.clone(),
                        key: key.clone(),
                        value: scalar_preview(child),
                    });
                }
                if FORBIDDEN_STATIC_ORIGIN_KEYS
                    .iter()
                    .any(|forbidden| normalize_contract_token(forbidden) == normalized_key)
                {
                    if let Some(value) = child.as_str() {
                        let normalized_value = normalize_contract_token(value);
                        if FORBIDDEN_STATIC_ORIGIN_VALUES.iter().any(|forbidden| {
                            normalize_contract_token(forbidden) == normalized_value
                        }) {
                            findings.push(ForbiddenStaticInput {
                                path: child_path.clone(),
                                key: key.clone(),
                                value: Some(value.to_string()),
                            });
                        }
                    }
                }
                if key_mentions_static_bootstrap(key) || value_mentions_static_bootstrap(child) {
                    findings.push(ForbiddenStaticInput {
                        path: child_path.clone(),
                        key: key.clone(),
                        value: scalar_preview(child),
                    });
                }
                visit_forbidden_static_inputs(child, &child_path, findings);
            }
        }
        Value::Array(items) => {
            for (index, child) in items.iter().enumerate() {
                visit_forbidden_static_inputs(child, &format!("{path}[{index}]"), findings);
            }
        }
        _ => {}
    }
}

fn format_object_path(parent: &str, key: &str) -> String {
    if key
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
    {
        format!("{parent}.{key}")
    } else {
        format!(
            "{parent}[{}]",
            serde_json::to_string(key).unwrap_or_else(|_| "\"?\"".to_string())
        )
    }
}

fn normalize_contract_token(value: &str) -> String {
    value
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .flat_map(|ch| ch.to_lowercase())
        .collect()
}

fn key_mentions_static_bootstrap(key: &str) -> bool {
    let normalized = normalize_contract_token(key);
    normalized.contains("staticscan")
        || normalized.contains("staticfinding")
        || normalized.contains("scannerbootstrap")
}

fn value_mentions_static_bootstrap(value: &Value) -> bool {
    match value {
        Value::String(value) => {
            let normalized = normalize_contract_token(value);
            normalized.contains("staticscan") || normalized.contains("staticfinding")
        }
        _ => false,
    }
}

fn scalar_preview(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.clone()),
        Value::Number(value) => Some(value.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        Value::Null => Some("null".to_string()),
        _ => None,
    }
}

pub fn sensitive_config_key_set() -> BTreeSet<String> {
    SENSITIVE_CONFIG_KEYS
        .iter()
        .map(|key| normalize_contract_token(key))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn agentflow_contract_static_gate_recurses_through_scope_payloads() {
        let payload = json!({
            "audit_scope": {
                "safe": true,
                "nested": [{"candidate_finding_ids": ["f1"]}],
                "meta": {"candidate_origin": "opengrep"}
            }
        });

        let findings = forbidden_static_inputs_in_value(&payload);
        assert!(findings
            .iter()
            .any(|finding| finding.path == "$.audit_scope.nested[0].candidate_finding_ids"));
        assert!(findings
            .iter()
            .any(|finding| finding.path == "$.audit_scope.meta.candidate_origin"));
    }

    #[test]
    fn agentflow_contract_static_gate_covers_all_forbidden_engine_origins() {
        for origin in FORBIDDEN_STATIC_ORIGIN_VALUES {
            let payload = json!({"source_engine": origin});
            assert!(
                contains_forbidden_static_input(&payload),
                "origin {origin} should be rejected"
            );
        }
    }

    #[test]
    fn agentflow_runner_input_round_trips_without_static_candidates() {
        let input = ArgusAgentflowRunnerInput {
            contract_version: ARGUS_AGENTFLOW_CONTRACT_VERSION.to_string(),
            task_id: "task-1".to_string(),
            project_id: "project-1".to_string(),
            project_root: "/workspace/project".to_string(),
            target: AgentflowTargetKind::Container,
            topology_version: P1_TOPOLOGY_VERSION.to_string(),
            audit_scope: AgentflowAuditScope {
                target_files: vec!["src/main.rs".to_string()],
                exclude_patterns: vec!["target/**".to_string()],
                target_vulnerabilities: vec!["authz".to_string()],
                verification_level: AgentflowVerificationLevel::Standard,
                prompt_skill: Some("secure-code-audit".to_string()),
                extra: BTreeMap::new(),
            },
            output_dir: "/workspace/output/task-1".to_string(),
            llm: AgentflowLlmConfig {
                provider: "openai-compatible".to_string(),
                model: "configured-model".to_string(),
                base_url: Some("https://example.invalid/v1".to_string()),
                api_key_ref: Some("system_config:llm.apiKey".to_string()),
                agent_kind: None,
                wire_api: None,
                api_key_env: None,
            },
            resource_budget: AgentflowResourceBudget {
                max_cpu_cores: 2.0,
                max_memory_mb: 4096,
                max_duration_seconds: 3600,
                max_concurrency: 2,
            },
            metadata: BTreeMap::new(),
        };

        let value = serde_json::to_value(&input).expect("serialize input");
        assert_eq!(value["contract_version"], ARGUS_AGENTFLOW_CONTRACT_VERSION);
        assert!(input.forbidden_static_inputs().is_empty());
        let decoded: ArgusAgentflowRunnerInput =
            serde_json::from_value(value).expect("decode input");
        assert_eq!(decoded.topology_version, P1_TOPOLOGY_VERSION);
    }

    #[test]
    fn agentflow_runner_output_requires_argus_event_envelope_fields() {
        let output = ArgusAgentflowRunnerOutput {
            contract_version: ARGUS_AGENTFLOW_CONTRACT_VERSION.to_string(),
            task_id: "task-1".to_string(),
            run: AgentflowRunSummary {
                run_id: "run-1".to_string(),
                status: AgentflowTaskStatus::Completed,
                topology_version: P1_TOPOLOGY_VERSION.to_string(),
                started_at: None,
                finished_at: None,
                input_digest: Some("sha256:abc".to_string()),
                topology_change: None,
            },
            events: vec![AgentflowEventEnvelope {
                id: "event-1".to_string(),
                sequence: 1,
                timestamp: "2026-04-27T00:00:00Z".to_string(),
                event_type: "report_generated".to_string(),
                role: "audit-reporter".to_string(),
                visibility: AgentflowVisibility::User,
                correlation_id: "run-1:event-1".to_string(),
                topology_version: P1_TOPOLOGY_VERSION.to_string(),
                node_id: Some("audit-reporter".to_string()),
                message: Some("报告已生成".to_string()),
                data: BTreeMap::new(),
            }],
            checkpoints: Vec::new(),
            findings: Vec::new(),
            report: AgentflowReport {
                title: "智能审计报告".to_string(),
                summary: "未发现可确认漏洞".to_string(),
                markdown: None,
                verified_count: 0,
                findings_count: 0,
                severity_counts: BTreeMap::new(),
                statistics: BTreeMap::new(),
                sections: Vec::new(),
                discard_summary: None,
                timeline: Vec::new(),
                artifact_index: Vec::new(),
                diagnostics: BTreeMap::new(),
            },
            agent_tree: Vec::new(),
            artifacts: Vec::new(),
            artifact_index: Vec::new(),
            feedback_bundle: None,
            diagnostics: AgentflowDiagnostics::default(),
        };

        let value = serde_json::to_value(&output).expect("serialize output");
        assert_eq!(value["events"][0]["sequence"], 1);
        assert_eq!(value["events"][0]["visibility"], "user");
        assert_eq!(value["events"][0]["topology_version"], P1_TOPOLOGY_VERSION);
        assert!(output.forbidden_static_inputs().is_empty());
    }

    #[test]
    fn agentflow_runner_input_round_trip_preserves_new_fields() {
        let config = AgentflowLlmConfig {
            provider: "anthropic_compatible".to_string(),
            model: "claude-opus-4-5".to_string(),
            base_url: None,
            api_key_ref: None,
            agent_kind: Some("claude".into()),
            wire_api: Some("messages".into()),
            api_key_env: Some("ANTHROPIC_API_KEY".into()),
        };

        let json_str = serde_json::to_string(&config).expect("serialize AgentflowLlmConfig");
        assert!(
            json_str.contains("\"agent_kind\":\"claude\""),
            "JSON must contain agent_kind:claude, got: {json_str}"
        );
        assert!(
            json_str.contains("\"wire_api\":\"messages\""),
            "JSON must contain wire_api:messages, got: {json_str}"
        );
        assert!(
            json_str.contains("\"api_key_env\":\"ANTHROPIC_API_KEY\""),
            "JSON must contain api_key_env:ANTHROPIC_API_KEY, got: {json_str}"
        );

        let decoded: AgentflowLlmConfig =
            serde_json::from_str(&json_str).expect("deserialize AgentflowLlmConfig");
        assert_eq!(decoded, config);
    }

    #[test]
    fn agentflow_runner_input_legacy_struct_serializes_without_new_fields() {
        let config = AgentflowLlmConfig {
            provider: "openai_compatible".to_string(),
            model: "gpt-4o".to_string(),
            base_url: Some("https://example.invalid/v1".to_string()),
            api_key_ref: Some("system_config:llmApiKey".to_string()),
            agent_kind: None,
            wire_api: None,
            api_key_env: None,
        };

        let json_str = serde_json::to_string(&config).expect("serialize legacy AgentflowLlmConfig");
        assert!(
            !json_str.contains("agent_kind"),
            "legacy JSON must NOT contain agent_kind, got: {json_str}"
        );
        assert!(
            !json_str.contains("wire_api"),
            "legacy JSON must NOT contain wire_api, got: {json_str}"
        );
        assert!(
            !json_str.contains("api_key_env"),
            "legacy JSON must NOT contain api_key_env, got: {json_str}"
        );

        let decoded: AgentflowLlmConfig =
            serde_json::from_str(&json_str).expect("deserialize legacy AgentflowLlmConfig");
        assert_eq!(decoded, config);
    }

    #[test]
    fn agentflow_runner_output_accepts_p2_p3_visibility_and_report_fields() {
        let output = json!({
            "contract_version": ARGUS_AGENTFLOW_CONTRACT_VERSION,
            "task_id": "task-1",
            "run": {
                "run_id": "run-1",
                "status": "completed",
                "topology_version": "p3-dynamic-topology-v1",
                "topology_change": {"action": "scale_out", "approved": false}
            },
            "events": [{
                "id": "event-1",
                "sequence": 1,
                "timestamp": "2026-04-27T00:00:00Z",
                "event_type": "topology_change",
                "role": "orchestrator",
                "visibility": "ORCHESTRATOR_ONLY",
                "correlation_id": "run-1:event-1",
                "topology_version": "p3-dynamic-topology-v1",
                "data": {}
            }],
            "checkpoints": [],
            "findings": [{
                "id": "finding-1",
                "vulnerability_type": "authz",
                "severity": "high",
                "title": "risk lifecycle survives",
                "status": "discarded",
                "is_verified": false,
                "discard_reason": "R3_unreachable",
                "risk_lifecycle": {"state": "DISCARDED"},
                "source": {
                    "node_id": "risk-reviewer",
                    "node_role": "validator",
                    "agent_id": "agent-1"
                }
            }],
            "report": {
                "title": "report",
                "summary": "summary",
                "sections": [{"title": "Discarded"}],
                "statistics": {"discarded": 1},
                "discard_summary": {"R3_unreachable": 1},
                "timeline": [{"event_type": "topology_change"}]
            },
            "artifact_index": [],
            "feedback_bundle": {"next_prompt": "narrow scope"},
            "diagnostics": {
                "resource_diagnostics": {"queued": false},
                "dynamic_expert_diagnostics": {"enabled": false}
            }
        });

        let decoded: ArgusAgentflowRunnerOutput =
            serde_json::from_value(output).expect("decode P2/P3-compatible output");
        assert_eq!(decoded.run.topology_version, "p3-dynamic-topology-v1");
        assert_eq!(
            decoded.events[0].visibility,
            AgentflowVisibility::Diagnostic
        );
        assert_eq!(
            decoded.findings[0].discard_reason.as_deref(),
            Some("R3_unreachable")
        );
        assert_eq!(decoded.report.sections.len(), 1);
        assert!(decoded.feedback_bundle.is_some());
    }
}
