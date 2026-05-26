use anyhow::Result;
use serde_json::json;

use crate::runtime::intelligent::types::IntelligentTaskEvent;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    repo::{build_inventory_summary, select_representative_files},
    stage_prompt,
    types::{fallback_recon, ReconOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    events: &PipelineEventSink,
    amplification: Option<&str>,
) -> Result<ReconOutput> {
    let stage = AuditStage::Recon;
    events.stage_started(stage);
    let target_files = select_representative_files(&ctx.entries, 40);
    let payload = json!({
        "projectId": ctx.project_id,
        "projectName": ctx.project_name,
        "inventorySummary": build_inventory_summary(&ctx.entries),
        "targetFiles": target_files,
        "requiredOutput": {
            "architectureSummary": "string",
            "subsystems": [{"name":"string","path":"string","purpose":"string"}],
            "initialTasks": [{"taskId":"string","attackClass":"string","scopeHint":"string","targetFiles":["string"],"rationale":"string","priority":1}]
        }
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let mut output = invoke_json::<ReconOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    if output.initial_tasks.is_empty() {
        output = fallback_recon(&ctx.entries);
    }
    events.stage_completed(
        stage,
        json!({
            "taskCount": output.initial_tasks.len(),
            "subsystemCount": output.subsystems.len(),
        }),
    );
    events.emit(
        IntelligentTaskEvent::new("recon_tasks_created").with_data(json!({
            "count": output.initial_tasks.len(),
        })),
    );
    Ok(output)
}
