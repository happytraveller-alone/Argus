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
    amplification: Option<&str>,
) -> Result<FeedbackOutput> {
    let stage = AuditStage::Feedback;
    events.stage_started(stage);
    let payload = json!({
        "traces": trace.traces,
        "instruction": "Turn reachable bug patterns into follow-up hunt tasks or reusable patterns.",
        "requiredOutput": {"newTasks": [], "patterns": ["string"]}
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let mut output =
        invoke_json::<FeedbackOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config, events)
            .await?
            .payload;

    // The feedback prompt schema (prompts.rs:293) does not require `task_id`
    // in new_tasks items, so the LLM legitimately omits it. Downstream
    // `hunt::run` (stages/hunt.rs:111) uses task_id to backfill
    // `finding.task_id` — an empty id would orphan every produced finding.
    // Synthesize stable `hunt-fb-{idx}` ids for empty/whitespace entries.
    for (idx, task) in output.new_tasks.iter_mut().enumerate() {
        if task.task_id.trim().is_empty() {
            task.task_id = format!("hunt-fb-{idx}");
        }
        if task.source.trim().is_empty() {
            task.source = "feedback".to_string();
        }
    }

    events.stage_completed(
        stage,
        json!({
            "newTaskCount": output.new_tasks.len(),
            "patternCount": output.patterns.len(),
        }),
    );
    Ok(output)
}
