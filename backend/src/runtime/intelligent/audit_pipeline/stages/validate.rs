use std::path::Path;

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
    amplification: Option<&str>,
    path_blacklist_extra: &[String],
) -> Result<ValidationOutput> {
    let stage = AuditStage::Validate;
    events.stage_started(stage);
    let payload = json!({
        "findings": hunt.findings,
        "instruction": "Adversarially validate findings. Confirm only if evidence supports attacker impact.",
        "requiredOutput": {"findings": [{"findingId":"string","validationStatus":"confirmed|rejected|needs_more_info","validationRationale":"string"}]}
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let mut output =
        invoke_json::<ValidationOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config, events)
            .await?
            .payload;
    if output.findings.is_empty() && amplification.is_none() {
        // ROUND-0 ONLY: this fallback runs only when no amplification is supplied,
        // which corresponds to round 0 in the run_stage_with_reflection meta-loop
        // (next_amp == None there). Subsequent rounds always carry an
        // amplification string (reflection's reshape output or synthesized
        // blacklist amplification), so the fallback won't re-confirm findings
        // that reflection has explicitly pruned. (F2 — replaces the
        // `is_first_attempt: bool` parameter approach.)
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
    output.findings.retain(|vf| {
        match crate::runtime::intelligent::code_intel::is_blacklisted(
            Path::new(&vf.finding.file),
            path_blacklist_extra,
        ) {
            Some(reason) => {
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "finding_blacklisted",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage.as_str(),
                        "findingId": vf.finding.finding_id,
                        "path": super::sanitize_path_for_event(&vf.finding.file),
                        "blacklistReason": reason,
                    })),
                );
                false
            }
            None => true,
        }
    });
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
