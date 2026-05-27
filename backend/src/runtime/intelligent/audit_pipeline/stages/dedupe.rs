use std::path::Path;

use anyhow::Result;
use serde_json::json;

use crate::runtime::intelligent::types::IntelligentTaskEvent;

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
    path_blacklist_extra: &[String],
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
    let mut output =
        invoke_json::<DedupeOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config, events)
            .await?
            .payload;
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

    // Build a lookup from finding_id -> file path for blacklist cross-reference
    let id_to_path: std::collections::HashMap<&str, &str> = validation
        .findings
        .iter()
        .map(|vf| (vf.finding.finding_id.as_str(), vf.finding.file.as_str()))
        .collect();

    let mut groups_to_drop: Vec<usize> = Vec::new();

    for (group_idx, group) in output.groups.iter_mut().enumerate() {
        let canonical_id = group.canonical_finding_id.clone();
        group.finding_ids.retain(|fid| {
            if let Some(path) = id_to_path.get(fid.as_str()) {
                if let Some(reason) = crate::runtime::intelligent::code_intel::is_blacklisted(
                    Path::new(path),
                    path_blacklist_extra,
                ) {
                    events.emit(IntelligentTaskEvent::new("finding_blacklisted").with_data(
                        json!({
                            "stage": stage.as_str(),
                            "findingId": fid,
                            "path": super::sanitize_path_for_event(path),
                            "blacklistReason": reason,
                        }),
                    ));
                    return false;
                }
            }
            true
        });

        // If canonical was dropped or group is now empty, mark for whole-group removal
        let canonical_dropped = !group.finding_ids.iter().any(|fid| fid == &canonical_id);
        if canonical_dropped || group.finding_ids.is_empty() {
            groups_to_drop.push(group_idx);
        }
    }

    // Drop groups in reverse order to preserve indices
    for idx in groups_to_drop.into_iter().rev() {
        output.groups.remove(idx);
    }

    events.stage_completed(stage, json!({"groupCount": output.groups.len()}));
    Ok(output)
}
