pub mod context;
pub mod json;
pub mod prompts;
pub mod repo;
pub mod stages;
pub mod types;

use std::sync::Arc;

use anyhow::{Context as AnyhowContext, Result};
use serde_json::json;

use crate::{
    db::projects,
    runtime::intelligent::{
        config::IntelligentLlmConfig,
        llm::IntelligentLlmInvoker,
        types::{IntelligentTaskEvent, IntelligentTaskFinding},
    },
    state::AppState,
};

use self::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    repo::ProjectArchive,
    types::PipelineOutputs,
};

pub const PIPELINE_AGENT_COUNT: usize = 8;
pub const PIPELINE_AGENT_NAMES: [&str; PIPELINE_AGENT_COUNT] = [
    "recon", "hunt", "validate", "gapfill", "dedupe", "trace", "feedback", "report",
];

#[derive(Debug, Clone)]
pub struct AuditPipelineResult {
    pub input_summary: String,
    pub report_summary: String,
    pub findings: Vec<IntelligentTaskFinding>,
    pub events: Vec<IntelligentTaskEvent>,
}

pub async fn run_pipeline(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    llm_config: &IntelligentLlmConfig,
    invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
    tx: &tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
) -> Result<AuditPipelineResult> {
    let project = projects::get_project(state, project_id)
        .await
        .map_err(|error| anyhow::anyhow!(error.to_string()))?
        .ok_or_else(|| anyhow::anyhow!("project not found: {project_id}"))?;
    let archive_meta = project
        .archive
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("project {project_id} has no archive"))?;

    let archive = ProjectArchive::new(
        archive_meta.storage_path.clone(),
        archive_meta.original_filename.clone(),
    );
    let entries = archive
        .list_entries()
        .with_context(|| format!("failed to list archive for project {project_id}"))?;
    let input_summary = repo::build_inventory_summary(&entries);

    let mut event_sink = PipelineEventSink::new(tx.clone());
    event_sink.emit(
        IntelligentTaskEvent::new("pipeline_started").with_data(json!({
            "agentCount": PIPELINE_AGENT_COUNT,
            "agents": PIPELINE_AGENT_NAMES,
        })),
    );

    let ctx = AuditRunContext::new(
        task_id.to_string(),
        project_id.to_string(),
        project.name.clone(),
        archive,
        entries,
        llm_config.clone(),
        invoker,
    );

    let mut outputs = PipelineOutputs::default();
    outputs.recon = stages::recon::run(&ctx, &mut event_sink).await?;
    outputs.hunt = stages::hunt::run(&ctx, &outputs.recon, &mut event_sink).await?;
    outputs.validate = stages::validate::run(&ctx, &outputs.hunt, &mut event_sink).await?;
    outputs.gapfill =
        stages::gapfill::run(&ctx, &outputs.recon, &outputs.validate, &mut event_sink).await?;
    outputs.dedupe = stages::dedupe::run(&ctx, &outputs.validate, &mut event_sink).await?;
    outputs.trace = stages::trace::run(&ctx, &outputs.dedupe, &mut event_sink).await?;
    outputs.feedback = stages::feedback::run(&ctx, &outputs.trace, &mut event_sink).await?;
    outputs.report = stages::report::run(&ctx, &outputs, &mut event_sink).await?;

    let findings = outputs.to_task_findings();
    event_sink.emit(
        IntelligentTaskEvent::new("pipeline_completed").with_data(json!({
            "agentCount": PIPELINE_AGENT_COUNT,
            "findingCount": findings.len(),
        })),
    );

    Ok(AuditPipelineResult {
        input_summary,
        report_summary: outputs.report.summary.clone(),
        findings,
        events: event_sink.into_events(),
    })
}

#[must_use]
pub fn stage_prompt(stage: AuditStage, payload: &serde_json::Value) -> String {
    format!(
        "You are the {stage} agent in an 8-agent security audit pipeline.

{}

Return only one JSON object matching the requested schema. Do not use markdown fences.

Input:
{}",
        prompts::stage_contract(stage),
        serde_json::to_string_pretty(payload).unwrap_or_else(|_| "{}".to_string())
    )
}
