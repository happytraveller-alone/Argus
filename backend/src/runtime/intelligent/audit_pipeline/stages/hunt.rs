use std::sync::Arc;

use anyhow::Result;
use serde_json::json;
use tokio::task::JoinSet;

use crate::runtime::intelligent::agent_runner::{AgentRunConfig, standard_tool_defs};

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    repo::source_snippets,
    stage_prompt,
    types::{AuditFinding, HuntOutput, HuntTask},
};

pub async fn run(
    ctx: &AuditRunContext,
    tasks: &[HuntTask],
    concurrency: usize,
    events: &PipelineEventSink,
) -> Result<HuntOutput> {
    let stage = AuditStage::Hunt;
    events.stage_started(stage);

    let semaphore = Arc::new(tokio::sync::Semaphore::new(concurrency.max(1)));
    let mut join_set: JoinSet<Result<Vec<AuditFinding>>> = JoinSet::new();

    for task in tasks {
        let ctx = ctx.clone();
        let events = events.clone();
        let task = task.clone();
        let sem = Arc::clone(&semaphore);

        join_set.spawn(async move {
            // Acquire permit before calling LLM to bound concurrency.
            let _permit = sem.acquire().await.expect("semaphore closed");
            let snippets = source_snippets(&ctx.archive, &task.target_files, 8_000);
            let payload = json!({
                "task": task,
                "architectureSummary": "",
                "snippets": snippets,
                "requiredOutput": {
                    "findings": [{"findingId":"string","file":"string","lineStart":1,"lineEnd":1,"vulnClass":"string","severity":"low|medium|high|critical","description":"string","evidence":"string","confidence":0.0}]
                }
            });
            let prompt = stage_prompt(stage, &payload);

            let mut output: HuntOutput = if let Some(runner) = &ctx.agent_runner {
                let tools = standard_tool_defs(&["Read", "Grep", "Glob", "Exec"]);
                let config = AgentRunConfig::default();
                let result = runner
                    .run_agent(stage.as_str(), &prompt, payload.clone(), &tools, &config)
                    .await?;
                serde_json::from_value(result.payload)?
            } else {
                invoke_json::<HuntOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config)
                    .await
                    .map(|result| {
                        events.emit(result.invocation.attempt_event);
                        result.payload
                    })?
            };
            for finding in &mut output.findings {
                if finding.task_id.is_none() {
                    finding.task_id = Some(task.task_id.clone());
                }
                normalize_finding(finding);
            }
            Ok(output.findings)
        });
    }

    let mut findings = Vec::new();
    while let Some(result) = join_set.join_next().await {
        match result {
            Ok(Ok(task_findings)) => findings.extend(task_findings),
            Ok(Err(err)) => return Err(err),
            Err(join_err) => return Err(anyhow::anyhow!("hunt task panicked: {join_err}")),
        }
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
