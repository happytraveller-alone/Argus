use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{FeedbackOutput, TraceOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    trace: &TraceOutput,
    events: &PipelineEventSink,
) -> Result<FeedbackOutput> {
    let stage = AuditStage::Feedback;
    events.stage_started(stage);
    let payload = json!({
        "traces": trace.traces,
        "instruction": "Turn reachable bug patterns into follow-up hunt tasks or reusable patterns.",
        "requiredOutput": {"newTasks": [], "patterns": ["string"]}
    });
    let prompt = stage_prompt(stage, &payload);
    let output = invoke_json::<FeedbackOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    events.stage_completed(
        stage,
        json!({
            "newTaskCount": output.new_tasks.len(),
            "patternCount": output.patterns.len(),
        }),
    );
    Ok(output)
}
