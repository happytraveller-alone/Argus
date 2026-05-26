use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{DedupeGroup, DedupeOutput, ValidationOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    validation: &ValidationOutput,
    events: &PipelineEventSink,
    amplification: Option<&str>,
) -> Result<DedupeOutput> {
    let stage = AuditStage::Dedupe;
    events.stage_started(stage);
    let confirmed = validation
        .findings
        .iter()
        .filter(|finding| finding.validation_status == "confirmed")
        .collect::<Vec<_>>();
    let payload = json!({
        "confirmedFindings": confirmed,
        "instruction": "Cluster findings by root cause and choose canonical representatives.",
        "requiredOutput": {"groups": [{"groupId":"string","canonicalFindingId":"string","findingIds":["string"],"rootCause":"string"}]}
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let mut output = invoke_json::<DedupeOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
        .await
        .map(|result| {
            events.emit(result.invocation.attempt_event);
            result.payload
        })?;
    if output.groups.is_empty() {
        output.groups = validation
            .findings
            .iter()
            .filter(|finding| finding.validation_status == "confirmed")
            .map(|finding| DedupeGroup {
                group_id: format!("group-{}", finding.finding.finding_id),
                canonical_finding_id: finding.finding.finding_id.clone(),
                finding_ids: vec![finding.finding.finding_id.clone()],
                root_cause: finding.finding.description.clone(),
            })
            .collect();
    }
    events.stage_completed(stage, json!({"groupCount": output.groups.len()}));
    Ok(output)
}
