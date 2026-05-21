use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{HuntOutput, ValidatedFinding, ValidationOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    hunt: &HuntOutput,
    events: &PipelineEventSink,
) -> Result<ValidationOutput> {
    let stage = AuditStage::Validate;
    events.stage_started(stage);
    let payload = json!({
        "findings": hunt.findings,
        "instruction": "Adversarially validate findings. Confirm only if evidence supports attacker impact.",
        "requiredOutput": {"findings": [{"findingId":"string","validationStatus":"confirmed|rejected|needs_more_info","validationRationale":"string"}]}
    });
    let prompt = stage_prompt(stage, &payload);
    let mut output =
        invoke_json::<ValidationOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
            .await
            .map(|result| {
                events.emit(result.invocation.attempt_event);
                result.payload
            })?;
    if output.findings.is_empty() {
        output.findings = hunt
            .findings
            .iter()
            .cloned()
            .map(|finding| ValidatedFinding {
                finding,
                validation_status: "confirmed".to_string(),
                validation_rationale:
                    "Confirmed by fallback because validate returned no findings.".to_string(),
            })
            .collect();
    }
    let confirmed = output
        .findings
        .iter()
        .filter(|finding| finding.validation_status == "confirmed")
        .count();
    events.stage_completed(
        stage,
        json!({
            "confirmedCount": confirmed,
            "rejectedCount": output.findings.len().saturating_sub(confirmed),
        }),
    );
    Ok(output)
}
