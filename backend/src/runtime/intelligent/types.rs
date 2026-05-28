use serde::{Deserialize, Serialize};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum FindingScopeType {
    File,
    Module,
}

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
    // New event kinds emitted by the reflection + blacklist mechanism (audit_pipeline):
    // - "reflection_round_started"      { stage, round, reason }
    // - "reflection_round_completed"    { stage, round, action: "prune"|"reshape", droppedCount?, keptCount? }
    // - "reflection_budget_exhausted"   { stage, totalRounds }
    // - "finding_blacklisted"           { stage, findingId, path, blacklistReason }
    // - "stage_quality_gate_failed"     (existing, retained for round-5 fallback)
    // - "BLACKLIST_VIOLATION" is a GateFailure.reason string, not a separate event kind
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line_start: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line_end: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vuln_class: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cwe_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_type: Option<FindingScopeType>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub module: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resolved_file_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub confidence: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub validation_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reachable: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_summary: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub poc_result: Option<serde_json::Value>,
    /// User verdict: `None` = pending, `Some("verified")` = true positive,
    /// `Some("false_positive")` = false positive.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_verdict: Option<String>,
    #[serde(default, rename = "evidenceCodeSnippets", skip_serializing_if = "Vec::is_empty")]
    pub evidence_code_snippets: Vec<crate::runtime::intelligent::audit_pipeline::types::EvidenceCodeSnippet>,
    #[serde(default, rename = "evidenceProse", skip_serializing_if = "Option::is_none")]
    pub evidence_prose: Option<String>,
    #[serde(default, rename = "reachabilityChain", skip_serializing_if = "Option::is_none")]
    pub reachability_chain: Option<Vec<crate::runtime::intelligent::audit_pipeline::types::CallHop>>,
    #[serde(default, rename = "reachabilityEntryPoint", skip_serializing_if = "Option::is_none")]
    pub reachability_entry_point: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IntelligentTaskRecord {
    pub task_id: String,
    pub project_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_root: Option<String>,
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
    /// `true` when the scan ran in degraded mode because codegraph indexing
    /// failed or fell back per-finding. Surfaced so users know the call-graph
    /// based reasoning was unavailable. See `.omc/plans/ralplan-codegraph-integration-v2.md` §AC5.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub partial_analysis: bool,
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
            project_name: None,
            project_root: None,
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
            partial_analysis: false,
        }
    }

    #[must_use]
    pub fn with_project_root(mut self, root: impl Into<String>) -> Self {
        self.project_root = Some(root.into());
        self
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
        self.emit_task_summary();
        Ok(())
    }

    pub fn mark_failed(&mut self, stage: impl Into<String>, reason: impl Into<String>) {
        let now = now_rfc3339();
        self.status = IntelligentTaskStatus::Failed;
        self.completed_at = Some(now);
        self.failure_stage = Some(stage.into());
        self.failure_reason = Some(reason.into());
        self.emit_task_summary();
    }

    /// Append a `task_summary` event whose counters are derived from
    /// `event_log` so no struct fields / serde migration are needed. Called
    /// from `mark_completed` (after `can_complete()?` passes and status
    /// flips to `Completed`) and `mark_failed` (after status flips to
    /// `Failed`). Per ralplan AC-B7 R3-2: emission strictly after status
    /// transition prevents orphan summaries on validation-rejected
    /// completions.
    fn emit_task_summary(&mut self) {
        let llm_attempt_count = self
            .event_log
            .iter()
            .filter(|e| e.kind == "llm_attempt")
            .count() as u32;
        let parse_failure_count = self
            .event_log
            .iter()
            .filter(|e| e.kind == "parse_failure")
            .count() as u32;
        let rate = if llm_attempt_count == 0 {
            0.0
        } else {
            f64::from(parse_failure_count) / f64::from(llm_attempt_count)
        };
        self.append_event(
            IntelligentTaskEvent::new("task_summary").with_data(serde_json::json!({
                "llmAttemptCount": llm_attempt_count,
                "parseFailureCount": parse_failure_count,
                "parseFailureRate": rate,
            })),
        );
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
        assert!(r.project_name.is_none());
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

    /// Helper: build a record whose proof fields all satisfy `can_complete`
    /// so the only signal under test is the `task_summary` derivation.
    fn ready_to_complete_record() -> IntelligentTaskRecord {
        let mut r = IntelligentTaskRecord::new_pending(
            "t-sum".to_string(),
            "p-sum".to_string(),
            "model".to_string(),
            "sha256:fp".to_string(),
        );
        r.input_summary = "files".to_string();
        r.report_summary = "summary".to_string();
        r.duration_ms = Some(1000);
        r
    }

    /// Test 7 (Plan Step 10) — `mark_completed` must append a `task_summary`
    /// event whose counters are derived from `event_log` (no extra struct
    /// fields). The summary lands strictly AFTER the status flip so a
    /// validation-rejected completion never leaves an orphan summary.
    #[test]
    fn task_summary_emitted_with_derived_counters() {
        let mut r = ready_to_complete_record();
        r.append_event(IntelligentTaskEvent::new("llm_attempt"));
        r.append_event(IntelligentTaskEvent::new("llm_attempt"));
        r.append_event(IntelligentTaskEvent::new("llm_attempt"));
        r.append_event(IntelligentTaskEvent::new("parse_failure"));

        r.mark_completed().expect("mark_completed must succeed");

        assert_eq!(r.status, IntelligentTaskStatus::Completed);
        let last = r
            .event_log
            .last()
            .expect("event_log must contain task_summary as the final event");
        assert_eq!(last.kind, "task_summary");
        let data = last
            .data
            .as_ref()
            .expect("task_summary must carry derived counters in data");
        assert_eq!(data["llmAttemptCount"], 3);
        assert_eq!(data["parseFailureCount"], 1);
        let rate = data["parseFailureRate"]
            .as_f64()
            .expect("parseFailureRate must be a float");
        assert!(
            (rate - (1.0 / 3.0)).abs() < 1e-9,
            "expected ~1/3, got {rate}"
        );
    }

    /// Test 7b (Plan Step 10) — `mark_failed` also appends `task_summary` so
    /// failure-path runs surface the same observability counters as
    /// successful runs.
    #[test]
    fn task_summary_emitted_on_mark_failed() {
        let mut r = ready_to_complete_record();
        r.append_event(IntelligentTaskEvent::new("llm_attempt"));
        r.append_event(IntelligentTaskEvent::new("parse_failure"));
        r.append_event(IntelligentTaskEvent::new("parse_failure"));

        r.mark_failed("hunt", "test");

        assert_eq!(r.status, IntelligentTaskStatus::Failed);
        let last = r
            .event_log
            .last()
            .expect("event_log must contain task_summary even on failure");
        assert_eq!(last.kind, "task_summary");
        let data = last.data.as_ref().expect("task_summary must carry data");
        assert_eq!(data["llmAttemptCount"], 1);
        assert_eq!(data["parseFailureCount"], 2);
        let rate = data["parseFailureRate"].as_f64().unwrap();
        assert!((rate - 2.0).abs() < 1e-9, "expected 2.0, got {rate}");
    }
}
