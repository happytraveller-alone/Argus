use std::path::Path;
use std::sync::Arc;

use anyhow::Result;
use serde_json::json;
use tokio::task::JoinSet;

use crate::runtime::intelligent::agent_runner::{AgentRunConfig, standard_tool_defs};
use crate::runtime::intelligent::code_intel::path_classifier::{
    PathCategory, classify_path,
};

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    repo::source_snippets,
    stage_prompt,
    types::{
        AuditFinding, ConfidenceSource, DismissalCategory, DismissalEvidence, HuntOutput,
        HuntTask,
    },
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
                normalize_finding(finding, &task.target_files);
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

/// Normalize a freshly-emitted `AuditFinding`:
///   - clamp line numbers,
///   - default empty severity to `"medium"`,
///   - **Plan AC0.F**: when the upstream `HuntTask` has exactly one target file
///     and that file lives under a known test/vendor path component, write a
///     `dismissal_evidence` with `confidence_source: PathPattern`.
///
/// Phase 0 scope-limit: multi-target tasks (`target_files.len() != 1`) leave
/// `dismissal_evidence = None` — multi-file taint reasoning is Phase 1 work.
/// Real-code single targets also leave `None`; Phase 1 Hunt Pass 2 fills those.
fn normalize_finding(finding: &mut AuditFinding, target_files: &[String]) {
    if finding.line_start == 0 {
        finding.line_start = 1;
    }
    if finding.line_end < finding.line_start {
        finding.line_end = finding.line_start;
    }
    if finding.severity.trim().is_empty() {
        finding.severity = "medium".to_string();
    }

    if finding.dismissal_evidence.is_none() && target_files.len() == 1 {
        let (category, pattern) = classify_path(Path::new(&target_files[0]));
        let dismissal_category = match category {
            PathCategory::Test => Some(DismissalCategory::Test),
            PathCategory::Vendor => Some(DismissalCategory::Vendor),
            PathCategory::RealCode => None,
        };
        if let Some(category) = dismissal_category {
            finding.dismissal_evidence = Some(DismissalEvidence {
                category,
                confidence_source: ConfidenceSource::PathPattern,
                path_pattern: pattern,
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base_finding() -> AuditFinding {
        AuditFinding {
            finding_id: "f1".to_string(),
            file: "tests/integration_test.rs".to_string(),
            line_start: 5,
            line_end: 5,
            vuln_class: "sql_injection".to_string(),
            severity: "high".to_string(),
            description: "stub".to_string(),
            evidence: "stub".to_string(),
            ..Default::default()
        }
    }

    /// AC0.F integration: a finding under `tests/` MUST receive
    /// `dismissal_evidence` with `confidence_source: PathPattern`.
    #[test]
    fn normalize_finding_writes_path_pattern_evidence_for_test_dir() {
        let mut finding = base_finding();
        let targets = vec!["tests/integration_test.rs".to_string()];
        normalize_finding(&mut finding, &targets);
        let evidence = finding
            .dismissal_evidence
            .expect("test path must produce dismissal_evidence");
        assert_eq!(evidence.category, DismissalCategory::Test);
        assert_eq!(evidence.confidence_source, ConfidenceSource::PathPattern);
        assert_eq!(evidence.path_pattern.as_deref(), Some("tests/"));
    }

    /// Real code single target leaves dismissal_evidence None (Phase 1 fills it).
    #[test]
    fn normalize_finding_leaves_real_code_evidence_none() {
        let mut finding = base_finding();
        finding.file = "src/handler.rs".to_string();
        let targets = vec!["src/handler.rs".to_string()];
        normalize_finding(&mut finding, &targets);
        assert!(finding.dismissal_evidence.is_none());
    }

    /// Vendor path produces Vendor category + PathPattern source.
    #[test]
    fn normalize_finding_writes_vendor_evidence() {
        let mut finding = base_finding();
        finding.file = "vendor/lib/foo.go".to_string();
        let targets = vec!["vendor/lib/foo.go".to_string()];
        normalize_finding(&mut finding, &targets);
        let evidence = finding
            .dismissal_evidence
            .expect("vendor path must produce dismissal_evidence");
        assert_eq!(evidence.category, DismissalCategory::Vendor);
        assert_eq!(evidence.confidence_source, ConfidenceSource::PathPattern);
        assert_eq!(evidence.path_pattern.as_deref(), Some("vendor/"));
    }

    /// Multi-target findings (Phase 1 scope) leave dismissal_evidence None.
    #[test]
    fn normalize_finding_skips_multi_target() {
        let mut finding = base_finding();
        let targets = vec![
            "tests/a.rs".to_string(),
            "tests/b.rs".to_string(),
        ];
        normalize_finding(&mut finding, &targets);
        assert!(finding.dismissal_evidence.is_none());
    }

    /// Empty target_files leaves dismissal_evidence None.
    #[test]
    fn normalize_finding_skips_empty_targets() {
        let mut finding = base_finding();
        let targets: Vec<String> = vec![];
        normalize_finding(&mut finding, &targets);
        assert!(finding.dismissal_evidence.is_none());
    }

    /// Pre-existing dismissal_evidence is not overwritten.
    #[test]
    fn normalize_finding_preserves_existing_evidence() {
        let mut finding = base_finding();
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::Sanitized,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
        });
        let targets = vec!["tests/something.rs".to_string()];
        normalize_finding(&mut finding, &targets);
        let evidence = finding.dismissal_evidence.expect("preserved");
        assert_eq!(evidence.category, DismissalCategory::Sanitized);
        assert_eq!(evidence.confidence_source, ConfidenceSource::RuleMatched);
    }
}
