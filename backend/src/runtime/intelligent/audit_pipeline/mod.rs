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
        code_intel::{cache::CodeGraphCache, codegraph_client::CodeGraphClient, CodeIntelligence},
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

    let mut ctx = AuditRunContext::new(
        task_id.to_string(),
        project_id.to_string(),
        project.name.clone(),
        archive,
        entries,
        llm_config.clone(),
        invoker,
    );

    // ── CodeGraph code intelligence bring-up (best-effort) ───────────────────
    // Per plan §Step 2.7. archive_meta.sha256 already exists at ingest, so this
    // does NOT count against AC4's 30s budget. On failure, partial_analysis is
    // flagged and stages fall back to single-pass behavior automatically.
    let code_intel_client: Option<Arc<CodeGraphClient>> = {
        match try_init_code_intel(archive_meta, &config.audit_sandbox_image).await {
            Ok(client) => {
                event_sink.emit(
                    IntelligentTaskEvent::new("codegraph_init_completed").with_data(json!({
                        "archiveSha256": archive_meta.sha256,
                        "languagesIndexed": client.languages_indexed(),
                    })),
                );
                let arc = Arc::new(client);
                ctx.code_intel = Some(arc.clone());
                Some(arc)
            }
            Err(err) => {
                ctx.partial_analysis
                    .store(true, std::sync::atomic::Ordering::Relaxed);
                let error_chain = format_anyhow_error_chain(&err);
                event_sink.emit(
                    IntelligentTaskEvent::new("codegraph_init_failed").with_data(json!({
                        "archiveSha256": archive_meta.sha256,
                        "error": err.to_string(),
                        "errorChain": error_chain,
                    })),
                );
                tracing::warn!(
                    archive_sha256 = %archive_meta.sha256,
                    error = %err,
                    error_chain = %error_chain,
                    "codegraph init failed; scan continuing in degraded mode"
                );
                None
            }
        }
    };

    // Token budget tracker (approximate — incremented per LLM call attempt event).
    let _token_counter = Arc::new(AtomicU64::new(0));

    // ── CodeGraph lifecycle guard ─────────────────────────────────────────
    // Wrap the codegraph client so the container is destroyed even if a stage
    // panics or the task is cancelled. Explicit shutdown on success/error;
    // label-based blanket `podman rm -f` in Drop catches every other path.
    let codegraph_guard = CodeGraphCleanupGuard {
        client: code_intel_client.clone(),
    };

    // Run stages inside an inner async block so cleanup runs even on stage error.
    // The existing `?` operator semantics inside the block produce a Result we
    // inspect AFTER calling shutdown on the code intel client.
    let stages_result: Result<PipelineOutputs> = async {
        // ── Phase 1: recon ────────────────────────────────────────────────
        let mut outputs = PipelineOutputs::default();
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
                    event_sink.emit(IntelligentTaskEvent::new("budget_exceeded").with_data(
                        json!({
                            "phase": "gapfill_loop",
                            "iteration": gap_iter,
                        }),
                    ));
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
        outputs.trace =
            stages::trace::run(&ctx, &outputs.dedupe, &outputs.validate, &event_sink).await?;

        // ── Phase 4: feedback → hunt → validate → dedupe → trace loop ────────────
        for fb_iter in 0..config.feedback_iterations {
            if let Some(budget) = config.max_tokens_budget {
                if _token_counter.load(Ordering::Relaxed) >= budget {
                    event_sink.emit(IntelligentTaskEvent::new("budget_exceeded").with_data(
                        json!({
                            "phase": "feedback_loop",
                            "iteration": fb_iter,
                        }),
                    ));
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
            outputs.trace =
                stages::trace::run(&ctx, &outputs.dedupe, &outputs.validate, &event_sink).await?;
        }

        // ── Phase 5: report ───────────────────────────────────────────
        outputs.report = stages::report::run(&ctx, &outputs, &event_sink).await?;
        Ok(outputs)
    }
    .await;

    // ── CodeGraph shutdown (always runs on stage success/error) ──────────────
    // Explicit shutdown through the guard. On panic or task cancellation the
    // guard's Drop fires a label-based blanket `podman rm -f` as safety net.
    codegraph_guard.shutdown().await;

    let outputs = stages_result?;
    let findings = outputs.to_task_findings();
    event_sink.emit(
        IntelligentTaskEvent::new("pipeline_completed").with_data(json!({
            "agentCount": PIPELINE_AGENT_COUNT,
            "findingCount": findings.len(),
            "partialAnalysis": ctx.partial_analysis.load(std::sync::atomic::Ordering::Relaxed),
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

/// Best-effort code intelligence bring-up. Failure is the caller's signal to
/// continue in degraded mode (single-pass for all stages). See plan §Step 2.7.
async fn try_init_code_intel(
    archive_meta: &crate::state::StoredProjectArchive,
    sandbox_image: &str,
) -> Result<CodeGraphClient> {
    let cache = Arc::new(CodeGraphCache::new().context("CodeGraphCache::new failed")?);
    let archive_path = std::path::Path::new(&archive_meta.storage_path);
    CodeGraphClient::init(
        archive_path,
        &archive_meta.original_filename,
        archive_meta.sha256.clone(),
        sandbox_image,
        cache,
    )
    .await
}

fn format_anyhow_error_chain(error: &anyhow::Error) -> String {
    error
        .chain()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join(": ")
}

// ── CodeGraph container lifecycle guard ───────────────────────────────────

/// Ensures the codegraph container is destroyed regardless of how the pipeline
/// exits: normal return, stage error (`?`), panic, or task cancellation.
///
/// - `.shutdown().await` calls `CodeGraphClient::shutdown()` for a clean exit.
/// - `Drop` runs `podman rm -f` on any containers labelled `argus-codegraph` as
///   a synchronous fire-and-forget safety net (no tokio runtime dependency).
struct CodeGraphCleanupGuard {
    client: Option<Arc<CodeGraphClient>>,
}

impl CodeGraphCleanupGuard {
    /// Destroy the codegraph container and run label-based blanket cleanup.
    ///
    /// Consumes the guard so that `Drop` does not fire a second cleanup.
    async fn shutdown(mut self) {
        if let Some(client) = self.client.take() {
            if let Err(err) = client.shutdown().await {
                tracing::warn!(error = %err, "codegraph explicit shutdown failed");
            }
            // Belt-and-suspenders: also run label-based cleanup to catch any
            // containers that survived the explicit shutdown above (e.g. podman
            // rm returned an error but the container is still running).
            spawn_label_cleanup();
        }
    }
}

impl Drop for CodeGraphCleanupGuard {
    fn drop(&mut self) {
        if self.client.is_some() {
            // Safety net for panics and task cancellation where `shutdown()`
            // was never called. Fire-and-forget, no runtime dependency.
            spawn_label_cleanup();
        }
    }
}

/// Fire-and-forget: remove all containers labelled `argus-codegraph`.
fn spawn_label_cleanup() {
    let _ = std::process::Command::new("sh")
        .args([
            "-c",
            "podman rm -f $(podman ps -aq --filter label=argus-codegraph) 2>/dev/null",
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_anyhow_error_chain_preserves_context_sources() {
        let error = std::fs::read_to_string("/definitely/missing/codegraph.db")
            .context("cache.try_load failed")
            .context("CodeGraphClient::init failed")
            .unwrap_err();

        let chain = format_anyhow_error_chain(&error);
        assert!(chain.contains("CodeGraphClient::init failed"), "{chain}");
        assert!(chain.contains("cache.try_load failed"), "{chain}");
        assert!(
            chain.contains("No such file") || chain.contains("os error"),
            "{chain}"
        );
    }
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
