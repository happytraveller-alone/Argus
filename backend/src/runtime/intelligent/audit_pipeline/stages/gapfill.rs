use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{GapfillOutput, ReconOutput, ValidationOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    recon: &ReconOutput,
    validation: &ValidationOutput,
    events: &PipelineEventSink,
    amplification: Option<&str>,
) -> Result<GapfillOutput> {
    let stage = AuditStage::Gapfill;
    events.stage_started(stage);
    let payload = json!({
        "architectureSummary": recon.architecture_summary,
        "confirmedFindings": validation.findings.iter().filter(|f| f.validation_status == "confirmed").collect::<Vec<_>>(),
        "existingTasks": recon.initial_tasks,
        "instruction": "Identify under-covered areas and propose extra hunt tasks only when useful.",
        "requiredOutput": {"newTasks": [], "rationale": "string"}
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let output = invoke_json::<GapfillOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    events.stage_completed(stage, json!({"newTaskCount": output.new_tasks.len()}));
    Ok(output)
}
