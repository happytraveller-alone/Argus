use std::{
    fmt,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc,
    },
};

use serde_json::json;

use crate::runtime::intelligent::{
    agent_runner::AgentRunner, code_intel::CodeIntelligence, config::IntelligentLlmConfig,
    config::StageEngineSelection, llm::IntelligentLlmInvoker, types::IntelligentTaskEvent,
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
    /// Per-stage execution-engine selection (Phase 0.5 dispatch seam). Defaults
    /// to all-Rust; the orchestrator consults it before each stage so a future
    /// Node sidecar can own a stage out-of-process. With no `intelligentEngine`
    /// config present every stage stays Rust and the existing in-process path
    /// runs unchanged (AC2).
    pub engine_selection: StageEngineSelection,
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
            engine_selection: StageEngineSelection::all_rust(),
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

    /// Builder method to set the per-stage engine selection (Phase 0.5 seam).
    /// Defaults to all-Rust when unset, preserving the baseline behavior.
    #[must_use]
    pub fn with_engine_selection(mut self, selection: StageEngineSelection) -> Self {
        self.engine_selection = selection;
        self
    }
}

/// Channel-based event sink. `emit` takes `&self` so it can be shared across concurrent tasks.
/// The broadcast sender forwards events to external subscribers; the mpsc sender collects them
/// for the final `into_events()` drain.
///
/// **Single `seq` authority:** every event is stamped with a monotonic `seq`
/// from `seq_counter` *before* it is split into the broadcast copy and the
/// collected copy, so the live SSE event and the persisted event always carry
/// the same `seq`. The counter is shared (via `with_seq_counter`) with the
/// task-level lifecycle emitter in `task.rs`, so `seq` is globally monotonic
/// across both the `run_started`/`step_*`/`audit_pipeline_failed` lifecycle
/// events and the per-stage pipeline events of one task.
#[derive(Clone)]
pub struct PipelineEventSink {
    broadcast_tx: tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
    collect_tx: tokio::sync::mpsc::UnboundedSender<IntelligentTaskEvent>,
    seq_counter: Arc<AtomicU64>,
}

impl PipelineEventSink {
    /// Create a new sink. Returns the sink and a receiver that drains all emitted events.
    ///
    /// The sink starts with a private `seq` counter (seeded at 1). Production
    /// callers in `task.rs` immediately replace it via [`with_seq_counter`] so
    /// the task-level lifecycle events and the pipeline events share one
    /// monotonic counter. Test callers can use the private counter as-is.
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
                seq_counter: Arc::new(AtomicU64::new(1)),
            },
            collect_rx,
        )
    }

    /// Share an externally-owned `seq` counter so pipeline events interleave
    /// monotonically with the task-level lifecycle events emitted in `task.rs`.
    #[must_use]
    pub fn with_seq_counter(mut self, counter: Arc<AtomicU64>) -> Self {
        self.seq_counter = counter;
        self
    }

    pub fn emit(&self, mut event: IntelligentTaskEvent) {
        // Stamp seq from the shared counter BEFORE cloning so the broadcast and
        // collected copies carry the same monotonic value (single authority).
        event.seq = self.seq_counter.fetch_add(1, Ordering::SeqCst);
        let _ = self.broadcast_tx.send(event.clone());
        let _ = self.collect_tx.send(event);
    }

    pub fn stage_started(&self, stage: AuditStage) {
        self.emit(IntelligentTaskEvent::new("agent_started").with_data(json!({
            "stage": stage.as_str(),
            "agent": stage.as_str(),
        })));
    }

    /// Emits the `agent_completed` SSE event for a stage transition.
    ///
    /// CONTRACT (per .omc/plans/ralplan-intelligent-audit-detail-ui-fixes-2026-05-26.md §BE-4):
    /// Callers should persist any stage-produced findings to the IntelligentTaskRecord
    /// (via `task::flush_findings_to_record(...).await`) BEFORE invoking
    /// `stage_completed`, so that frontend SSE consumers re-querying the record after
    /// observing `agent_completed{stage}` see the post-stage findings without a race.
    /// Currently the orchestrator in `audit_pipeline/mod.rs` flushes AFTER each stage
    /// returns (because emits happen inside the stage's `run()` function). The race
    /// window equals the duration of `flush_findings_to_record` (~ms) and is acceptable
    /// for current consumers which read findings from the SSE-attached record snapshot
    /// rather than re-fetching on each event.
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
