pub mod context;
pub mod coverage;
pub mod json;
pub mod prompts;
pub mod repo;
pub mod stages;
pub mod state_db;
pub mod types;

use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

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

/// Tuning knobs for the iterative pipeline.
#[derive(Debug, Clone)]
pub struct AuditPipelineConfig {
    /// Max concurrent LLM calls inside the hunt stage.
    pub hunt_concurrency: usize,
    /// How many gapfill → hunt → validate rounds to run after the first pass.
    pub gapfill_iterations: usize,
    /// How many feedback → hunt → validate → dedupe → trace rounds to run.
    pub feedback_iterations: usize,
    /// Optional hard cap on total tokens consumed (approximate, best-effort).
    pub max_tokens_budget: Option<u64>,
    /// Podman image for the audit sandbox (tool execution environment).
    pub audit_sandbox_image: String,
}

impl Default for AuditPipelineConfig {
    fn default() -> Self {
        Self {
            hunt_concurrency: 4,
            gapfill_iterations: 2,
            feedback_iterations: 1,
            max_tokens_budget: None,
            audit_sandbox_image: std::env::var("AUDIT_SANDBOX_IMAGE")
                .unwrap_or_else(|_| "argus/audit-sandbox:latest".to_string()),
        }
    }
}

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
    run_pipeline_with_config(
        state,
        task_id,
        project_id,
        llm_config,
        invoker,
        tx,
        &AuditPipelineConfig::default(),
    )
    .await
}

pub async fn run_pipeline_with_config(
    state: &AppState,
    task_id: &str,
    project_id: &str,
    llm_config: &IntelligentLlmConfig,
    invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
    tx: &tokio::sync::broadcast::Sender<IntelligentTaskEvent>,
    config: &AuditPipelineConfig,
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

    // Channel-based event collection: sink clones go to concurrent tasks,
    // collector task drains them into a Vec for the final result.
    let (event_sink, mut collect_rx) = PipelineEventSink::new(tx.clone());
    let collector = tokio::spawn(async move {
        let mut events = Vec::new();
        while let Some(ev) = collect_rx.recv().await {
            events.push(ev);
        }
        events
    });

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

    // Token budget tracker (approximate — incremented per LLM call attempt event).
    let _token_counter = Arc::new(AtomicU64::new(0));

    let mut outputs = PipelineOutputs::default();

    // ── Phase 1: recon ────────────────────────────────────────────────────────
    outputs.recon = stages::recon::run(&ctx, &event_sink).await?;

    // ── Phase 2: hunt → validate → gapfill loop ───────────────────────────────
    let mut hunt_tasks = outputs.recon.initial_tasks.clone();
    outputs.hunt =
        stages::hunt::run(&ctx, &hunt_tasks, config.hunt_concurrency, &event_sink).await?;
    outputs.validate = stages::validate::run(&ctx, &outputs.hunt, &event_sink).await?;

    for gap_iter in 0..config.gapfill_iterations {
        // Budget check (best-effort).
        if let Some(budget) = config.max_tokens_budget {
            if _token_counter.load(Ordering::Relaxed) >= budget {
                event_sink.emit(
                    IntelligentTaskEvent::new("budget_exceeded").with_data(json!({
                        "phase": "gapfill_loop",
                        "iteration": gap_iter,
                    })),
                );
                break;
            }
        }

        outputs.gapfill =
            stages::gapfill::run(&ctx, &outputs.recon, &outputs.validate, &event_sink).await?;

        if outputs.gapfill.new_tasks.is_empty() {
            break;
        }

        event_sink.emit(
            IntelligentTaskEvent::new("gapfill_tasks_added").with_data(json!({
                "iteration": gap_iter,
                "newTaskCount": outputs.gapfill.new_tasks.len(),
            })),
        );

        hunt_tasks = outputs.gapfill.new_tasks.clone();
        let gap_hunt =
            stages::hunt::run(&ctx, &hunt_tasks, config.hunt_concurrency, &event_sink).await?;

        // Merge new findings into the accumulated hunt output.
        outputs.hunt.findings.extend(gap_hunt.findings);
        outputs.validate = stages::validate::run(&ctx, &outputs.hunt, &event_sink).await?;
    }

    // ── Phase 3: dedupe → trace ───────────────────────────────────────────────
    outputs.dedupe = stages::dedupe::run(&ctx, &outputs.validate, &event_sink).await?;
    outputs.trace = stages::trace::run(&ctx, &outputs.dedupe, &event_sink).await?;

    // ── Phase 4: feedback → hunt → validate → dedupe → trace loop ────────────
    for fb_iter in 0..config.feedback_iterations {
        if let Some(budget) = config.max_tokens_budget {
            if _token_counter.load(Ordering::Relaxed) >= budget {
                event_sink.emit(
                    IntelligentTaskEvent::new("budget_exceeded").with_data(json!({
                        "phase": "feedback_loop",
                        "iteration": fb_iter,
                    })),
                );
                break;
            }
        }

        outputs.feedback = stages::feedback::run(&ctx, &outputs.trace, &event_sink).await?;

        if outputs.feedback.new_tasks.is_empty() {
            break;
        }

        event_sink.emit(
            IntelligentTaskEvent::new("feedback_tasks_added").with_data(json!({
                "iteration": fb_iter,
                "newTaskCount": outputs.feedback.new_tasks.len(),
            })),
        );

        let fb_hunt = stages::hunt::run(
            &ctx,
            &outputs.feedback.new_tasks,
            config.hunt_concurrency,
            &event_sink,
        )
        .await?;
        outputs.hunt.findings.extend(fb_hunt.findings);
        outputs.validate = stages::validate::run(&ctx, &outputs.hunt, &event_sink).await?;
        outputs.dedupe = stages::dedupe::run(&ctx, &outputs.validate, &event_sink).await?;
        outputs.trace = stages::trace::run(&ctx, &outputs.dedupe, &event_sink).await?;
    }

    // ── Phase 5: report ───────────────────────────────────────────────────────
    outputs.report = stages::report::run(&ctx, &outputs, &event_sink).await?;

    let findings = outputs.to_task_findings();
    event_sink.emit(
        IntelligentTaskEvent::new("pipeline_completed").with_data(json!({
            "agentCount": PIPELINE_AGENT_COUNT,
            "findingCount": findings.len(),
        })),
    );

    // Drop the sink so the collector task can finish draining.
    drop(event_sink);
    let events = collector.await.unwrap_or_default();

    Ok(AuditPipelineResult {
        input_summary,
        report_summary: outputs.report.summary.clone(),
        findings,
        events,
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
