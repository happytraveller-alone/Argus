use std::{collections::BTreeMap, io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::fs;

use crate::state::AppState;

const TASK_STATE_FILE_NAME: &str = "rust-task-state.json";

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct TaskStateSnapshot {
    pub static_tasks: BTreeMap<String, StaticTaskRecord>,
    pub opengrep_rules: BTreeMap<String, OpengrepRuleRecord>,
    #[serde(default)]
    pub codeql_build_plans: BTreeMap<String, CodeqlBuildPlanRecord>,
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
    #[serde(default)]
    pub ai_analysis_status: Option<String>,
    #[serde(default)]
    pub ai_analysis_step: Option<i32>,
    #[serde(default)]
    pub ai_analysis_step_name: Option<String>,
    #[serde(default)]
    pub ai_analysis_result: Option<Value>,
    #[serde(default)]
    pub ai_analysis_error: Option<String>,
    #[serde(default)]
    pub ai_analysis_model: Option<String>,
    #[serde(default)]
    pub ai_analysis_started_at: Option<String>,
    #[serde(default)]
    pub ai_analysis_completed_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct StaticTaskProgressRecord {
    pub progress: f64,
    pub current_stage: Option<String>,
    pub message: Option<String>,
    pub started_at: Option<String>,
    pub updated_at: Option<String>,
    pub logs: Vec<StaticTaskProgressLogRecord>,
    #[serde(default)]
    pub events: Vec<StaticTaskProgressEventRecord>,
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
            events: Vec::new(),
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
pub struct StaticTaskProgressEventRecord {
    pub timestamp: String,
    pub event_type: String,
    pub stage: String,
    pub progress: f64,
    #[serde(default)]
    pub round: Option<i64>,
    #[serde(default)]
    pub redaction: Value,
    #[serde(default)]
    pub payload: Value,
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
#[serde(default)]
pub struct CodeqlBuildPlanRecord {
    pub id: String,
    pub project_id: String,
    pub language: String,
    pub target_path: String,
    pub source_fingerprint: String,
    pub dependency_fingerprint: String,
    pub build_mode: String,
    pub commands: Vec<String>,
    pub working_directory: String,
    pub query_suite: Option<String>,
    pub status: String,
    pub llm_model: Option<String>,
    pub evidence_json: Value,
    pub created_at: String,
    pub updated_at: Option<String>,
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
    pub removed_static_tasks: usize,
}

pub async fn remove_project_tasks(
    state: &AppState,
    project_id: &str,
) -> Result<ProjectTaskCleanupSummary> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    let summary = remove_project_tasks_from_snapshot(&mut snapshot, project_id);

    if summary.removed_static_tasks > 0 {
        save_snapshot_unlocked(state, &snapshot).await?;
    }

    Ok(summary)
}

pub(crate) fn remove_project_tasks_from_snapshot(
    snapshot: &mut TaskStateSnapshot,
    project_id: &str,
) -> ProjectTaskCleanupSummary {
    let static_before = snapshot.static_tasks.len();
    snapshot
        .static_tasks
        .retain(|_, record| record.project_id != project_id);

    ProjectTaskCleanupSummary {
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
