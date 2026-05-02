use serde::{Deserialize, Serialize};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

pub fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "1970-01-01T00:00:00Z".to_string())
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntelligentTaskStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

impl IntelligentTaskStatus {
    #[must_use]
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Completed | Self::Failed | Self::Cancelled)
    }

    #[must_use]
    pub fn is_cancellable(&self) -> bool {
        matches!(self, Self::Pending | Self::Running)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentTaskEvent {
    pub kind: String,
    pub timestamp: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

impl IntelligentTaskEvent {
    pub fn new(kind: impl Into<String>) -> Self {
        Self {
            kind: kind.into(),
            timestamp: now_rfc3339(),
            message: None,
            data: None,
        }
    }

    pub fn with_message(mut self, message: impl Into<String>) -> Self {
        self.message = Some(message.into());
        self
    }

    pub fn with_data(mut self, data: serde_json::Value) -> Self {
        self.data = Some(data);
        self
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentTaskFinding {
    pub id: String,
    pub severity: String,
    pub summary: String,
    pub evidence: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentTaskRecord {
    pub task_id: String,
    pub project_id: String,
    pub status: IntelligentTaskStatus,
    pub created_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub started_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u64>,
    pub llm_model: String,
    pub llm_fingerprint: String,
    pub input_summary: String,
    pub event_log: Vec<IntelligentTaskEvent>,
    pub report_summary: String,
    pub findings: Vec<IntelligentTaskFinding>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_stage: Option<String>,
}

impl IntelligentTaskRecord {
    pub fn new_pending(
        task_id: String,
        project_id: String,
        model: String,
        fingerprint: String,
    ) -> Self {
        Self {
            task_id,
            project_id,
            status: IntelligentTaskStatus::Pending,
            created_at: now_rfc3339(),
            started_at: None,
            completed_at: None,
            duration_ms: None,
            llm_model: model,
            llm_fingerprint: fingerprint,
            input_summary: String::new(),
            event_log: Vec::new(),
            report_summary: String::new(),
            findings: Vec::new(),
            failure_reason: None,
            failure_stage: None,
        }
    }

    pub fn mark_running(&mut self) {
        self.status = IntelligentTaskStatus::Running;
        self.started_at = Some(now_rfc3339());
    }

    pub fn mark_completed(&mut self) -> Result<(), &'static str> {
        self.can_complete()?;
        let now = now_rfc3339();
        self.status = IntelligentTaskStatus::Completed;
        self.completed_at = Some(now);
        Ok(())
    }

    pub fn mark_failed(&mut self, stage: impl Into<String>, reason: impl Into<String>) {
        let now = now_rfc3339();
        self.status = IntelligentTaskStatus::Failed;
        self.completed_at = Some(now);
        self.failure_stage = Some(stage.into());
        self.failure_reason = Some(reason.into());
    }

    pub fn mark_cancelled(&mut self) {
        let now = now_rfc3339();
        self.status = IntelligentTaskStatus::Cancelled;
        self.completed_at = Some(now);
    }

    pub fn append_event(&mut self, event: IntelligentTaskEvent) {
        self.event_log.push(event);
    }

    /// Validates that the required proof fields are populated before completing.
    pub fn can_complete(&self) -> Result<(), &'static str> {
        if self.event_log.is_empty() {
            return Err("event_log must be non-empty before completing");
        }
        if self.input_summary.is_empty() {
            return Err("input_summary must be non-empty before completing");
        }
        if self.report_summary.is_empty() {
            return Err("report_summary must be non-empty before completing");
        }
        if self.duration_ms.is_none() {
            return Err("duration_ms must be set before completing");
        }
        if self.llm_fingerprint.is_empty() {
            return Err("llm_fingerprint must be non-empty before completing");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_terminal_and_cancellable_helpers() {
        assert!(!IntelligentTaskStatus::Pending.is_terminal());
        assert!(IntelligentTaskStatus::Pending.is_cancellable());

        assert!(!IntelligentTaskStatus::Running.is_terminal());
        assert!(IntelligentTaskStatus::Running.is_cancellable());

        assert!(IntelligentTaskStatus::Completed.is_terminal());
        assert!(!IntelligentTaskStatus::Completed.is_cancellable());

        assert!(IntelligentTaskStatus::Failed.is_terminal());
        assert!(!IntelligentTaskStatus::Failed.is_cancellable());

        assert!(IntelligentTaskStatus::Cancelled.is_terminal());
        assert!(!IntelligentTaskStatus::Cancelled.is_cancellable());
    }

    #[test]
    fn new_pending_defaults() {
        let r = IntelligentTaskRecord::new_pending(
            "t1".to_string(),
            "p1".to_string(),
            "claude-3-5-sonnet".to_string(),
            "sha256:abc".to_string(),
        );
        assert_eq!(r.status, IntelligentTaskStatus::Pending);
        assert!(r.event_log.is_empty());
        assert!(r.findings.is_empty());
        assert!(r.started_at.is_none());
        assert!(r.duration_ms.is_none());
    }

    #[test]
    fn mark_completed_rejects_missing_proof_fields() {
        let mut r = IntelligentTaskRecord::new_pending(
            "t1".to_string(),
            "p1".to_string(),
            "model".to_string(),
            "fp".to_string(),
        );
        // missing all proof fields
        assert!(r.mark_completed().is_err());
        r.event_log.push(IntelligentTaskEvent::new("run_started"));
        r.input_summary = "files".to_string();
        r.report_summary = "summary".to_string();
        r.duration_ms = Some(1000);
        // fingerprint already set in new_pending
        assert!(r.mark_completed().is_ok());
        assert_eq!(r.status, IntelligentTaskStatus::Completed);
    }
}
