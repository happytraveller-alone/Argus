use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CubeSandboxTaskStatus {
    Queued,
    Starting,
    Running,
    Completed,
    Failed,
    Interrupted,
    CleanupFailed,
}

impl CubeSandboxTaskStatus {
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Failed | Self::Interrupted | Self::CleanupFailed
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CubeSandboxCleanupStatus {
    NotStarted,
    Completed,
    Failed,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CubeSandboxTaskRecord {
    pub task_id: String,
    pub status: CubeSandboxTaskStatus,
    pub code: String,
    pub created_at: String,
    pub updated_at: String,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
    pub duration_ms: Option<u64>,
    pub sandbox_id: Option<String>,
    pub stdout: String,
    pub stderr: String,
    pub stdout_truncated: bool,
    pub stderr_truncated: bool,
    pub exit_code: Option<i32>,
    pub error_category: Option<String>,
    pub error_message: Option<String>,
    pub cleanup_status: CubeSandboxCleanupStatus,
    pub cleanup_error: Option<String>,
    pub helper_log_tail: String,
    pub cube_api_log_tail: String,
    pub interrupt_requested: bool,
    pub timeout_seconds: Option<u64>,
    pub metadata: Option<Value>,
}

impl CubeSandboxTaskRecord {
    pub fn new_queued(
        task_id: String,
        code: String,
        timeout_seconds: Option<u64>,
        metadata: Option<Value>,
    ) -> Self {
        let now = now_rfc3339();
        Self {
            task_id,
            status: CubeSandboxTaskStatus::Queued,
            code,
            created_at: now.clone(),
            updated_at: now,
            started_at: None,
            finished_at: None,
            duration_ms: None,
            sandbox_id: None,
            stdout: String::new(),
            stderr: String::new(),
            stdout_truncated: false,
            stderr_truncated: false,
            exit_code: None,
            error_category: None,
            error_message: None,
            cleanup_status: CubeSandboxCleanupStatus::NotStarted,
            cleanup_error: None,
            helper_log_tail: String::new(),
            cube_api_log_tail: String::new(),
            interrupt_requested: false,
            timeout_seconds,
            metadata,
        }
    }

    pub fn touch(&mut self) {
        self.updated_at = now_rfc3339();
    }

    pub fn mark_terminal(&mut self, status: CubeSandboxTaskStatus) {
        self.status = status;
        let now = now_rfc3339();
        self.updated_at = now.clone();
        self.finished_at = Some(now);
    }
}

pub fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| OffsetDateTime::now_utc().unix_timestamp().to_string())
}
