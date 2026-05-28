use std::sync::atomic::Ordering;

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
    amplification: Option<&str>,
) -> Result<ReportOutput> {
    let stage = AuditStage::Report;
    events.stage_started(stage);
    let payload = json!({
        "recon": outputs.recon,
        "validatedFindings": outputs.validate.findings,
        "dedupe": outputs.dedupe,
        "trace": outputs.trace,
        "feedback": outputs.feedback,
        "instruction": "为 Argus 智能审计任务详情页生成最终的结构化报告摘要。所有自然语言字段必须使用简体中文撰写（summary、recommendations，以及 findings 中的 description / evidence / 说明等）；技术标识符、文件路径、JSON 键、代码片段保持原样。",
        "requiredOutput": {"summary": "string (简体中文)", "findings": [], "recommendations": ["string (简体中文)"]}
    });
    let mut prompt = stage_prompt(stage, &payload);
    if let Some(amp) = amplification {
        prompt.push_str(amp);
    }
    let mut output =
        invoke_json::<ReportOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config, events)
            .await?
            .payload;
    if output.summary.trim().is_empty() {
        let confirmed = outputs
            .validate
            .findings
            .iter()
            .filter(|finding| finding.validation_status == "confirmed")
            .count();
        output.summary = format!("智能审计已完成，共确认 {confirmed} 个高置信度风险点。");
    }
    // AC8: when any upstream stage soft-degraded via the quality gate, mark
    // the report summary so users see partial coverage explicitly.
    const PARTIAL_PREFIX: &str = "[部分覆盖] ";
    if ctx.partial_analysis.load(Ordering::Relaxed) && !output.summary.starts_with(PARTIAL_PREFIX) {
        output.summary = format!("{PARTIAL_PREFIX}{}", output.summary);
    }
    events.stage_completed(
        stage,
        json!({
            "summaryBytes": output.summary.len(),
            "recommendationCount": output.recommendations.len(),
            "partialAnalysis": ctx.partial_analysis.load(Ordering::Relaxed),
        }),
    );
    Ok(output)
}
