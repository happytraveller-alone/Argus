use std::{
    fmt,
    sync::{atomic::AtomicBool, Arc},
};

use serde_json::json;

use crate::runtime::intelligent::{
    agent_runner::AgentRunner, code_intel::CodeIntelligence, config::IntelligentLlmConfig,
    llm::IntelligentLlmInvoker, types::IntelligentTaskEvent,
};

use super::repo::{ArchiveEntry, ProjectArchive};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AuditStage {
    Recon,
    Hunt,
    Validate,
    Gapfill,
    Dedupe,
    Trace,
    Feedback,
    Report,
}

impl AuditStage {
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Recon => "recon",
            Self::Hunt => "hunt",
            Self::Validate => "validate",
            Self::Gapfill => "gapfill",
            Self::Dedupe => "dedupe",
            Self::Trace => "trace",
            Self::Feedback => "feedback",
            Self::Report => "report",
        }
    }
}

impl fmt::Display for AuditStage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Clone)]
pub struct AuditRunContext {
    pub task_id: String,
    pub project_id: String,
    pub project_name: String,
    pub archive: ProjectArchive,
    pub entries: Vec<ArchiveEntry>,
    pub llm_config: IntelligentLlmConfig,
    pub invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
    pub agent_runner: Option<Arc<dyn AgentRunner + Send + Sync>>,
    /// Optional code intelligence backend (codegraph). When `None`, stages
    /// fall back to single-pass behavior (no regression vs pre-integration).
    pub code_intel: Option<Arc<dyn CodeIntelligence>>,
    /// Set to `true` when codegraph init fails or any stage falls back from
    /// two-pass to single-pass. Surfaced in the final task record so users
    /// know the scan ran in degraded mode.
    pub partial_analysis: Arc<AtomicBool>,
}

impl AuditRunContext {
    pub fn new(
        task_id: String,
        project_id: String,
        project_name: String,
        archive: ProjectArchive,
        entries: Vec<ArchiveEntry>,
        llm_config: IntelligentLlmConfig,
        invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
    ) -> Self {
        Self {
            task_id,
            project_id,
            project_name,
            archive,
            entries,
            llm_config,
            invoker,
            agent_runner: None,
            code_intel: None,
            partial_analysis: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Builder method to attach a CodeIntelligence backend to the context.
    /// Returns `self` so callers can chain construction without breaking the
    /// existing `new()` signature.
    #[must_use]
    pub fn with_code_intel(mut self, intel: Arc<dyn CodeIntelligence>) -> Self {
        self.code_intel = Some(intel);
        self
    }
}

/// Channel-based event sink. `emit` takes `&self` so it can be shared across concurrent tasks.
/// The broadcast sender forwards events to external subscribers; the mpsc sender collects them
/// for the final `into_events()` drain.
#[derive(Clone)]
pub struct PipelineEventSink {
    broadcast_tx: tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
    collect_tx: tokio::sync::mpsc::UnboundedSender<IntelligentTaskEvent>,
}

impl PipelineEventSink {
    /// Create a new sink. Returns the sink and a receiver that drains all emitted events.
    pub fn new(
        broadcast_tx: tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
    ) -> (
        Self,
        tokio::sync::mpsc::UnboundedReceiver<IntelligentTaskEvent>,
    ) {
        let (collect_tx, collect_rx) = tokio::sync::mpsc::unbounded_channel();
        (
            Self {
                broadcast_tx,
                collect_tx,
            },
            collect_rx,
        )
    }

    pub fn emit(&self, event: IntelligentTaskEvent) {
        let _ = self.broadcast_tx.send(event.clone());
        let _ = self.collect_tx.send(event);
    }

    pub fn stage_started(&self, stage: AuditStage) {
        self.emit(IntelligentTaskEvent::new("agent_started").with_data(json!({
            "stage": stage.as_str(),
            "agent": stage.as_str(),
        })));
    }

    pub fn stage_completed(&self, stage: AuditStage, data: serde_json::Value) {
        self.emit(
            IntelligentTaskEvent::new("agent_completed").with_data(json!({
                "stage": stage.as_str(),
                "agent": stage.as_str(),
                "output": data,
            })),
        );
    }
}
