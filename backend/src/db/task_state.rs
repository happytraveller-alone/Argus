use std::{collections::BTreeMap, io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::fs;

use crate::state::AppState;

const TASK_STATE_FILE_NAME: &str = "rust-task-state.json";

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct TaskStateSnapshot {
    pub agent_tasks: BTreeMap<String, AgentTaskRecord>,
    pub static_tasks: BTreeMap<String, StaticTaskRecord>,
    pub opengrep_rules: BTreeMap<String, OpengrepRuleRecord>,
    pub phpstan_rule_overrides: BTreeMap<String, RuleOverrideRecord>,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AgentTaskRecord {
    pub id: String,
    pub project_id: String,
    pub name: Option<String>,
    pub description: Option<String>,
    pub task_type: String,
    pub status: String,
    pub current_phase: Option<String>,
    pub current_step: Option<String>,
    pub total_files: i64,
    pub indexed_files: i64,
    pub analyzed_files: i64,
    pub files_with_findings: i64,
    pub total_chunks: i64,
    pub findings_count: i64,
    pub verified_count: i64,
    pub false_positive_count: i64,
    pub total_iterations: i64,
    pub tool_calls_count: i64,
    pub tokens_used: i64,
    pub critical_count: i64,
    pub high_count: i64,
    pub medium_count: i64,
    pub low_count: i64,
    pub verified_critical_count: i64,
    pub verified_high_count: i64,
    pub verified_medium_count: i64,
    pub verified_low_count: i64,
    pub quality_score: f64,
    pub security_score: Option<f64>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub progress_percentage: f64,
    pub audit_scope: Option<Value>,
    pub target_vulnerabilities: Option<Vec<String>>,
    pub verification_level: Option<String>,
    pub tool_evidence_protocol: Option<String>,
    pub exclude_patterns: Option<Vec<String>>,
    pub target_files: Option<Vec<String>>,
    pub error_message: Option<String>,
    pub report: Option<String>,
    #[serde(default)]
    pub runtime: Option<String>,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default)]
    pub topology_version: Option<String>,
    #[serde(default)]
    pub input_digest: Option<String>,
    #[serde(default)]
    pub artifact_index: Option<Value>,
    #[serde(default)]
    pub report_snapshot: Option<Value>,
    #[serde(default)]
    pub feedback_bundle: Option<Value>,
    #[serde(default)]
    pub diagnostics: Option<Value>,
    pub events: Vec<AgentEventRecord>,
    pub findings: Vec<AgentFindingRecord>,
    pub checkpoints: Vec<AgentCheckpointRecord>,
    pub agent_tree: Vec<Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AgentEventRecord {
    pub id: String,
    pub task_id: String,
    pub event_type: String,
    pub phase: Option<String>,
    pub message: Option<String>,
    pub tool_name: Option<String>,
    pub tool_input: Option<Value>,
    pub tool_output: Option<Value>,
    pub tool_duration_ms: Option<i64>,
    pub finding_id: Option<String>,
    pub tokens_used: Option<i64>,
    pub metadata: Option<Value>,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub visibility: Option<String>,
    #[serde(default)]
    pub correlation_id: Option<String>,
    #[serde(default)]
    pub topology_version: Option<String>,
    #[serde(default)]
    pub source_node_id: Option<String>,
    pub sequence: i64,
    pub timestamp: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AgentFindingRecord {
    pub id: String,
    pub task_id: String,
    pub vulnerability_type: String,
    pub severity: String,
    pub title: String,
    pub display_title: Option<String>,
    pub description: Option<String>,
    pub description_markdown: Option<String>,
    pub file_path: Option<String>,
    pub line_start: Option<i64>,
    pub line_end: Option<i64>,
    pub resolved_file_path: Option<String>,
    pub resolved_line_start: Option<i64>,
    pub code_snippet: Option<String>,
    pub code_context: Option<String>,
    pub cwe_id: Option<String>,
    pub cwe_name: Option<String>,
    pub context_start_line: Option<i64>,
    pub context_end_line: Option<i64>,
    pub status: String,
    pub is_verified: bool,
    pub verdict: Option<String>,
    pub reachability: Option<String>,
    pub authenticity: Option<String>,
    pub verification_evidence: Option<String>,
    pub verification_todo_id: Option<String>,
    pub verification_fingerprint: Option<String>,
    pub reachability_file: Option<String>,
    pub reachability_function: Option<String>,
    pub reachability_function_start_line: Option<i64>,
    pub reachability_function_end_line: Option<i64>,
    pub flow_path_score: Option<f64>,
    pub flow_call_chain: Option<Vec<String>>,
    pub function_trigger_flow: Option<Vec<String>>,
    pub flow_control_conditions: Option<Vec<String>>,
    pub logic_authz_evidence: Option<Vec<String>>,
    pub has_poc: bool,
    pub poc_code: Option<String>,
    pub trigger_flow: Option<Value>,
    pub poc_trigger_chain: Option<Value>,
    pub suggestion: Option<String>,
    pub fix_code: Option<String>,
    pub report: Option<String>,
    pub ai_explanation: Option<String>,
    pub ai_confidence: Option<f64>,
    pub confidence: Option<f64>,
    #[serde(default)]
    pub source_node_id: Option<String>,
    #[serde(default)]
    pub source_role: Option<String>,
    #[serde(default)]
    pub artifact_refs: Option<Value>,
    #[serde(default)]
    pub risk_lifecycle: Option<Value>,
    #[serde(default)]
    pub discard_reason: Option<String>,
    #[serde(default)]
    pub confidence_history: Option<Value>,
    #[serde(default)]
    pub data_flow: Option<Value>,
    #[serde(default)]
    pub impact: Option<String>,
    #[serde(default)]
    pub remediation: Option<String>,
    #[serde(default)]
    pub verification: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct AgentCheckpointRecord {
    pub id: String,
    pub task_id: String,
    pub agent_id: String,
    pub agent_name: String,
    pub agent_type: String,
    pub parent_agent_id: Option<String>,
    pub iteration: i64,
    pub status: String,
    pub total_tokens: i64,
    pub tool_calls: i64,
    pub findings_count: i64,
    pub checkpoint_type: String,
    pub checkpoint_name: Option<String>,
    pub created_at: Option<String>,
    pub state_data: Value,
    pub metadata: Option<Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct StaticTaskRecord {
    pub id: String,
    pub engine: String,
    pub project_id: String,
    pub name: String,
    pub status: String,
    pub target_path: String,
    pub total_findings: i64,
    pub scan_duration_ms: i64,
    pub files_scanned: i64,
    pub error_message: Option<String>,
    pub created_at: String,
    pub updated_at: Option<String>,
    pub extra: Value,
    pub progress: StaticTaskProgressRecord,
    pub findings: Vec<StaticFindingRecord>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StaticTaskProgressRecord {
    pub progress: f64,
    pub current_stage: Option<String>,
    pub message: Option<String>,
    pub started_at: Option<String>,
    pub updated_at: Option<String>,
    pub logs: Vec<StaticTaskProgressLogRecord>,
}

impl Default for StaticTaskProgressRecord {
    fn default() -> Self {
        Self {
            progress: 0.0,
            current_stage: Some("created".to_string()),
            message: Some("task created in rust backend".to_string()),
            started_at: None,
            updated_at: None,
            logs: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct StaticTaskProgressLogRecord {
    pub timestamp: String,
    pub stage: String,
    pub message: String,
    pub progress: f64,
    pub level: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct StaticFindingRecord {
    pub id: String,
    pub scan_task_id: String,
    pub status: String,
    pub payload: Value,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct OpengrepRuleRecord {
    pub id: String,
    pub name: String,
    pub language: String,
    pub severity: String,
    pub confidence: Option<String>,
    pub description: Option<String>,
    pub cwe: Option<Vec<String>>,
    pub source: String,
    pub correct: bool,
    pub is_active: bool,
    pub created_at: String,
    pub pattern_yaml: String,
    pub patch: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct RuleOverrideRecord {
    pub id: String,
    pub is_active: Option<bool>,
    pub is_deleted: Option<bool>,
    pub patch: Value,
}

pub async fn load_snapshot(state: &AppState) -> Result<TaskStateSnapshot> {
    let _guard = state.file_store_lock.lock().await;
    load_snapshot_unlocked(state).await
}

pub(crate) async fn load_snapshot_unlocked(state: &AppState) -> Result<TaskStateSnapshot> {
    let path = task_state_file_path(state);
    match fs::read_to_string(&path).await {
        Ok(raw) => serde_json::from_str(&raw)
            .with_context(|| format!("failed to parse task state snapshot: {}", path.display())),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(TaskStateSnapshot::default()),
        Err(error) => Err(error.into()),
    }
}

pub async fn save_snapshot(state: &AppState, snapshot: &TaskStateSnapshot) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    save_snapshot_unlocked(state, snapshot).await
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ProjectTaskCleanupSummary {
    pub removed_agent_tasks: usize,
    pub removed_static_tasks: usize,
}

pub async fn remove_project_tasks(
    state: &AppState,
    project_id: &str,
) -> Result<ProjectTaskCleanupSummary> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    let summary = remove_project_tasks_from_snapshot(&mut snapshot, project_id);

    if summary.removed_agent_tasks > 0 || summary.removed_static_tasks > 0 {
        save_snapshot_unlocked(state, &snapshot).await?;
    }

    Ok(summary)
}

pub(crate) fn remove_project_tasks_from_snapshot(
    snapshot: &mut TaskStateSnapshot,
    project_id: &str,
) -> ProjectTaskCleanupSummary {
    let agent_before = snapshot.agent_tasks.len();
    snapshot
        .agent_tasks
        .retain(|_, record| record.project_id != project_id);
    let static_before = snapshot.static_tasks.len();
    snapshot
        .static_tasks
        .retain(|_, record| record.project_id != project_id);

    ProjectTaskCleanupSummary {
        removed_agent_tasks: agent_before.saturating_sub(snapshot.agent_tasks.len()),
        removed_static_tasks: static_before.saturating_sub(snapshot.static_tasks.len()),
    }
}

pub(crate) async fn save_snapshot_unlocked(
    state: &AppState,
    snapshot: &TaskStateSnapshot,
) -> Result<()> {
    ensure_file_storage_root(state).await?;
    let path = task_state_file_path(state);
    let tmp_path = path.with_extension("tmp");
    let bytes = serde_json::to_vec_pretty(snapshot)?;
    fs::write(&tmp_path, bytes).await?;
    fs::rename(tmp_path, path).await?;
    Ok(())
}

fn task_state_file_path(state: &AppState) -> PathBuf {
    state.config.zip_storage_path.join(TASK_STATE_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<()> {
    fs::create_dir_all(&state.config.zip_storage_path).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{AgentEventRecord, AgentFindingRecord, AgentTaskRecord};
    use serde_json::json;

    #[test]
    fn agent_task_state_defaults_legacy_snapshots_for_agentflow_fields() {
        let record: AgentTaskRecord = serde_json::from_value(json!({
            "id": "task-1",
            "project_id": "project-1",
            "task_type": "agent_audit",
            "status": "completed",
            "created_at": "2026-04-27T00:00:00Z"
        }))
        .expect("legacy task snapshot should deserialize");

        assert_eq!(record.runtime, None);
        assert_eq!(record.artifact_index, None);
        assert_eq!(record.report_snapshot, None);
        assert!(record.events.is_empty());
    }

    #[test]
    fn agent_event_and_finding_state_accept_agentflow_view_fields() {
        let event: AgentEventRecord = serde_json::from_value(json!({
            "id": "event-1",
            "task_id": "task-1",
            "event_type": "node_completed",
            "sequence": 1,
            "timestamp": "2026-04-27T00:00:00Z",
            "role": "vuln-reasoner",
            "visibility": "user",
            "correlation_id": "task-1",
            "topology_version": "p1",
            "source_node_id": "node-1"
        }))
        .expect("event envelope should deserialize");
        assert_eq!(event.role.as_deref(), Some("vuln-reasoner"));
        assert_eq!(event.visibility.as_deref(), Some("user"));

        let finding: AgentFindingRecord = serde_json::from_value(json!({
            "id": "finding-1",
            "task_id": "task-1",
            "vulnerability_type": "sql_injection",
            "severity": "high",
            "title": "SQL injection",
            "status": "verified",
            "is_verified": true,
            "created_at": "2026-04-27T00:00:00Z",
            "source_node_id": "node-1",
            "source_role": "vuln-reasoner",
            "artifact_refs": [{"path": "reports/finding.json"}],
            "impact": "database disclosure",
            "remediation": "use parameterized queries",
            "verification": "confirmed by reasoning"
        }))
        .expect("finding view fields should deserialize");
        assert_eq!(finding.source_role.as_deref(), Some("vuln-reasoner"));
        assert_eq!(finding.impact.as_deref(), Some("database disclosure"));
    }
}
