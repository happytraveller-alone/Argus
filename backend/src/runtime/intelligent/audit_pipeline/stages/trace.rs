use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{DedupeOutput, TraceOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    dedupe: &DedupeOutput,
    events: &PipelineEventSink,
) -> Result<TraceOutput> {
    let stage = AuditStage::Trace;
    events.stage_started(stage);
    let payload = json!({
        "dedupeGroups": dedupe.groups,
        "instruction": "For each canonical finding, decide whether attacker-controlled input can reach the sink. Use unknown/false only with rationale.",
        "requiredOutput": {"traces": [{"findingId":"string","reachable":true,"confidence":0.0,"rationale":"string"}]}
    });
    let prompt = stage_prompt(stage, &payload);
    let output = invoke_json::<TraceOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    let reachable = output.traces.iter().filter(|trace| trace.reachable).count();
    events.stage_completed(
        stage,
        json!({
            "reachableCount": reachable,
            "traceCount": output.traces.len(),
        }),
    );
    Ok(output)
}
