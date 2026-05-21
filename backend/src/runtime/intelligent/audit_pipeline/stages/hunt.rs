use anyhow::Result;
use serde_json::json;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    repo::source_snippets,
    stage_prompt,
    types::{AuditFinding, HuntOutput, ReconOutput},
};

pub async fn run(
    ctx: &AuditRunContext,
    recon: &ReconOutput,
    events: &mut PipelineEventSink,
) -> Result<HuntOutput> {
    let stage = AuditStage::Hunt;
    events.stage_started(stage);
    let mut findings = Vec::new();
    for task in &recon.initial_tasks {
        let snippets = source_snippets(&ctx.archive, &task.target_files, 8_000);
        let payload = json!({
            "task": task,
            "architectureSummary": recon.architecture_summary,
            "snippets": snippets,
            "requiredOutput": {
                "findings": [{"findingId":"string","file":"string","lineStart":1,"lineEnd":1,"vulnClass":"string","severity":"low|medium|high|critical","description":"string","evidence":"string","confidence":0.0}]
            }
        });
        let prompt = stage_prompt(stage, &payload);
        let mut output = invoke_json::<HuntOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
            .await
            .map(|result| {
                events.emit(result.invocation.attempt_event);
                result.payload
            })?;
        for finding in &mut output.findings {
            if finding.task_id.is_none() {
                finding.task_id = Some(task.task_id.clone());
            }
            normalize_finding(finding);
        }
        findings.extend(output.findings);
    }
    let output = HuntOutput { findings };
    events.stage_completed(stage, json!({"findingCount": output.findings.len()}));
    Ok(output)
}

fn normalize_finding(finding: &mut AuditFinding) {
    if finding.line_start == 0 {
        finding.line_start = 1;
    }
    if finding.line_end < finding.line_start {
        finding.line_end = finding.line_start;
    }
    if finding.severity.trim().is_empty() {
        finding.severity = "medium".to_string();
    }
}
