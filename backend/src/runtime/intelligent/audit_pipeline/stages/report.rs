use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{PipelineOutputs, ReportOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    outputs: &PipelineOutputs,
    events: &PipelineEventSink,
) -> Result<ReportOutput> {
    let stage = AuditStage::Report;
    events.stage_started(stage);
    let payload = json!({
        "recon": outputs.recon,
        "validatedFindings": outputs.validate.findings,
        "dedupe": outputs.dedupe,
        "trace": outputs.trace,
        "feedback": outputs.feedback,
        "instruction": "Produce the final structured report summary for the Argus intelligent task detail page.",
        "requiredOutput": {"summary":"string", "findings": [], "recommendations": ["string"]}
    });
    let prompt = stage_prompt(stage, &payload);
    let mut output = invoke_json::<ReportOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    if output.summary.trim().is_empty() {
        let confirmed = outputs
            .validate
            .findings
            .iter()
            .filter(|finding| finding.validation_status == "confirmed")
            .count();
        output.summary =
            format!("8-agent intelligent audit completed with {confirmed} confirmed findings.");
    }
    events.stage_completed(
        stage,
        json!({
            "summaryBytes": output.summary.len(),
            "recommendationCount": output.recommendations.len(),
        }),
    );
    Ok(output)
}
