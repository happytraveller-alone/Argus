use std::{fmt, sync::Arc};

use serde_json::json;

use crate::runtime::intelligent::{
    config::IntelligentLlmConfig, llm::IntelligentLlmInvoker, types::IntelligentTaskEvent,
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
        }
    }
}

pub struct PipelineEventSink {
    tx: tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
    events: Vec<IntelligentTaskEvent>,
}

impl PipelineEventSink {
    pub fn new(tx: tokio::sync::broadcast::Sender<IntelligentTaskEvent>) -> Self {
        Self { tx, events: vec![] }
    }

    pub fn emit(&mut self, event: IntelligentTaskEvent) {
        let _ = self.tx.send(event.clone());
        self.events.push(event);
    }

    pub fn stage_started(&mut self, stage: AuditStage) {
        self.emit(IntelligentTaskEvent::new("agent_started").with_data(json!({
            "stage": stage.as_str(),
            "agent": stage.as_str(),
        })));
    }

    pub fn stage_completed(&mut self, stage: AuditStage, data: serde_json::Value) {
        self.emit(
            IntelligentTaskEvent::new("agent_completed").with_data(json!({
                "stage": stage.as_str(),
                "agent": stage.as_str(),
                "output": data,
            })),
        );
    }

    pub fn into_events(self) -> Vec<IntelligentTaskEvent> {
        self.events
    }
}
