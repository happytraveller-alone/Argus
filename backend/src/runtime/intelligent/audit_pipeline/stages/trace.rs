//! Trace stage — reachability analysis.
//!
//! Two-pass architecture (see `.omc/plans/ralplan-codegraph-integration-v2.md` §Phase 3):
//!   * Per-finding fallback: when `ctx.code_intel` is absent, the finding's language
//!     is not indexed, or the token budget is exhausted, the stage runs the existing
//!     single-pass LLM call and produces the same `TraceResult` as before.
//!   * Two-pass path: pre-resolve the symbol at the finding's file:line, ask the LLM
//!     for up to 5 retrieval queries (Pass 1), dispatch them through the
//!     `CodeIntelligence` trait, then ask the LLM to issue a verdict from the
//!     structured evidence (Pass 2). No regression vs the previous single-pass
//!     behavior is preserved whenever the new path is unavailable.

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use anyhow::Result;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::task::JoinSet;

use crate::runtime::intelligent::{
    code_intel::{CodeIntelligence, SymbolMatch},
    token_budget::{BudgetExceeded, Pass, TokenBudget},
    types::IntelligentTaskEvent,
};

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    prompts::{TRACE_PASS1_PROMPT, TRACE_PASS2_PROMPT},
    stage_prompt,
    types::{DedupeOutput, TraceOutput, TraceResult, ValidationOutput, ValidatedFinding},
};

/// Base token budget per finding for the two-pass flow. Used to construct a
/// `TokenBudget` (which applies the 1.5x multiplier and 25/75 split internally).
///
/// TODO: surface this through `IntelligentLlmConfig` once per-stage budget knobs land.
const BASE_BUDGET_PER_FINDING: u64 = 4_000;

/// Hard cap on retrieval queries per finding in Pass 1.
const MAX_QUERIES_PER_FINDING: usize = 5;

/// Per-finding concurrency. Mirrors `AuditPipelineConfig::hunt_concurrency`
/// default; trace doesn't currently receive a config, so we hardcode 4.
const TRACE_CONCURRENCY: usize = 4;

/// Coarse heuristic: ~4 chars per token. Used to estimate prompt token cost
/// for budget enforcement before each LLM call.
fn estimate_tokens(text: &str) -> u64 {
    ((text.len() as f64) / 4.0).ceil() as u64
}

/// Run the Trace stage. Builds one `TraceResult` per `DedupeGroup`, choosing
/// two-pass or single-pass per finding based on availability.
pub async fn run(
    ctx: &AuditRunContext,
    dedupe: &DedupeOutput,
    validation: &ValidationOutput,
    events: &PipelineEventSink,
) -> Result<TraceOutput> {
    let stage = AuditStage::Trace;
    events.stage_started(stage);

    // Build a map of finding_id -> ValidatedFinding for file/line resolution.
    let validated_by_id: std::collections::HashMap<String, ValidatedFinding> = validation
        .findings
        .iter()
        .map(|finding| (finding.finding.finding_id.clone(), finding.clone()))
        .collect();

    let semaphore = Arc::new(tokio::sync::Semaphore::new(TRACE_CONCURRENCY));
    let mut join_set: JoinSet<Result<TraceResult>> = JoinSet::new();

    for group in &dedupe.groups {
        let canonical_id = group.canonical_finding_id.clone();
        let validated = validated_by_id.get(&canonical_id).cloned();
        let ctx = ctx.clone();
        let events = events.clone();
        let sem = Arc::clone(&semaphore);

        join_set.spawn(async move {
            let _permit = sem.acquire().await.expect("semaphore closed");
            let validated = match validated {
                Some(v) => v,
                None => {
                    // No finding metadata — fall back to a single-pass call seeded
                    // with just the canonical id, matching prior behavior.
                    return single_pass_for_id(&ctx, &canonical_id, &events).await;
                }
            };
            run_finding(&ctx, &validated, &events).await
        });
    }

    let mut traces: Vec<TraceResult> = Vec::with_capacity(dedupe.groups.len());
    while let Some(joined) = join_set.join_next().await {
        match joined {
            Ok(Ok(trace)) => traces.push(trace),
            Ok(Err(err)) => return Err(err),
            Err(join_err) => return Err(anyhow::anyhow!("trace task panicked: {join_err}")),
        }
    }

    let reachable = traces.iter().filter(|trace| trace.reachable).count();
    events.stage_completed(
        stage,
        json!({
            "reachableCount": reachable,
            "traceCount": traces.len(),
        }),
    );
    Ok(TraceOutput { traces })
}

/// Decide single-pass vs two-pass for one finding and execute.
async fn run_finding(
    ctx: &AuditRunContext,
    validated: &ValidatedFinding,
    events: &PipelineEventSink,
) -> Result<TraceResult> {
    let finding = &validated.finding;
    let finding_id = finding.finding_id.clone();

    let intel = match &ctx.code_intel {
        Some(intel) if intel.is_available() => intel.clone(),
        _ => {
            emit_fallback(events, &finding_id, "no_intel");
            ctx.partial_analysis.store(true, Ordering::Relaxed);
            return single_pass_for_finding(ctx, validated, events).await;
        }
    };

    let lang = match map_extension_to_language(&finding.file) {
        Some(lang) => lang,
        None => {
            emit_fallback(events, &finding_id, "language_unsupported");
            ctx.partial_analysis.store(true, Ordering::Relaxed);
            return single_pass_for_finding(ctx, validated, events).await;
        }
    };
    let indexed = intel.languages_indexed();
    if !indexed.iter().any(|entry| entry.eq_ignore_ascii_case(&lang)) {
        emit_fallback(events, &finding_id, "language_unsupported");
        ctx.partial_analysis.store(true, Ordering::Relaxed);
        return single_pass_for_finding(ctx, validated, events).await;
    }

    // Pre-resolve symbol — closes the grounding gap (Architect concern #5 in plan).
    let resolved = match intel
        .resolve_symbol_at(&finding.file, finding.line_start)
        .await
    {
        Ok(symbol) => symbol,
        Err(err) => {
            tracing::debug!(finding_id = %finding_id, error = %err, "resolve_symbol_at failed");
            None
        }
    };
    if resolved.is_none() {
        emit_fallback(events, &finding_id, "pre_resolve_failed");
        ctx.partial_analysis.store(true, Ordering::Relaxed);
        return single_pass_for_finding(ctx, validated, events).await;
    }

    events.emit(IntelligentTaskEvent::new("trace_two_pass_started").with_data(json!({
        "findingId": finding_id,
        "file": finding.file,
        "lineStart": finding.line_start,
    })));

    let budget = TokenBudget::new(BASE_BUDGET_PER_FINDING);
    let fell_back = Arc::new(AtomicBool::new(false));
    match two_pass_for_finding(
        ctx,
        intel.as_ref(),
        validated,
        resolved.as_ref(),
        &budget,
        events,
        Arc::clone(&fell_back),
    )
    .await
    {
        Ok(trace) => Ok(trace),
        Err(err) => {
            tracing::warn!(
                finding_id = %finding_id,
                error = %err,
                "two-pass trace failed; falling back to single-pass"
            );
            if !fell_back.load(Ordering::Relaxed) {
                emit_fallback(events, &finding_id, "two_pass_error");
            }
            ctx.partial_analysis.store(true, Ordering::Relaxed);
            single_pass_for_finding(ctx, validated, events).await
        }
    }
}

/// Execute Pass 1 + dispatch + Pass 2. On `BudgetExceeded` returns Ok with a
/// fallback `TraceResult` (caller decides whether to substitute single-pass).
#[allow(clippy::too_many_arguments)]
async fn two_pass_for_finding(
    ctx: &AuditRunContext,
    intel: &dyn CodeIntelligence,
    validated: &ValidatedFinding,
    resolved: Option<&SymbolMatch>,
    budget: &TokenBudget,
    events: &PipelineEventSink,
    fell_back: Arc<AtomicBool>,
) -> Result<TraceResult> {
    let finding = &validated.finding;
    let finding_id = finding.finding_id.clone();
    let finding_json = json!({
        "findingId": finding.finding_id,
        "file": finding.file,
        "lineStart": finding.line_start,
        "lineEnd": finding.line_end,
        "vulnClass": finding.vuln_class,
        "description": finding.description,
        "evidence": finding.evidence,
    });

    // ── Pass 1: ask the LLM which queries to run ───────────────────────────────
    let pass1_payload = json!({
        "finding": finding_json,
        "resolvedSymbol": resolved,
        "maxQueries": MAX_QUERIES_PER_FINDING,
    });
    let pass1_prompt = build_prompt(TRACE_PASS1_PROMPT, &pass1_payload);
    if let Some(trace) = check_budget(
        budget,
        Pass::Retrieval,
        estimate_tokens(&pass1_prompt),
        ctx,
        validated,
        events,
        &fell_back,
    )
    .await?
    {
        return Ok(trace);
    }
    let retrieval = invoke_json::<RetrievalRequest>(
        &*ctx.invoker,
        AuditStage::Trace,
        &pass1_prompt,
        &ctx.llm_config,
    )
    .await
    .map(|result| {
        events.emit(result.invocation.attempt_event.clone());
        result.payload
    })
    .map_err(|err| anyhow::anyhow!("trace pass1 invoke failed: {err}"))?;

    let mut queries = retrieval.queries;
    queries.truncate(MAX_QUERIES_PER_FINDING);
    events.emit(IntelligentTaskEvent::new("trace_pass1_queries").with_data(json!({
        "findingId": finding_id,
        "queryCount": queries.len(),
    })));

    // ── Dispatch queries ───────────────────────────────────────────────────────
    let mut results: Vec<Value> = Vec::with_capacity(queries.len());
    for query in queries {
        let outcome = dispatch_query(intel, &query).await;
        results.push(json!({
            "tool": query.tool,
            "args": query.args,
            "result": outcome,
        }));
    }

    // ── Pass 2: reasoning over evidence ────────────────────────────────────────
    let pass2_payload = json!({
        "finding": finding_json,
        "resolvedSymbol": resolved,
        "retrievalResults": results,
    });
    let pass2_prompt = build_prompt(TRACE_PASS2_PROMPT, &pass2_payload);
    if let Some(trace) = check_budget(
        budget,
        Pass::Reasoning,
        estimate_tokens(&pass2_prompt),
        ctx,
        validated,
        events,
        &fell_back,
    )
    .await?
    {
        return Ok(trace);
    }

    let mut verdict = invoke_json::<TraceResult>(
        &*ctx.invoker,
        AuditStage::Trace,
        &pass2_prompt,
        &ctx.llm_config,
    )
    .await
    .map(|result| {
        events.emit(result.invocation.attempt_event.clone());
        result.payload
    })
    .map_err(|err| anyhow::anyhow!("trace pass2 invoke failed: {err}"))?;
    if verdict.finding_id.is_empty() {
        verdict.finding_id = finding_id.clone();
    }

    events.emit(IntelligentTaskEvent::new("trace_pass2_completed").with_data(json!({
        "findingId": finding_id,
        "reachable": verdict.reachable,
        "confidence": verdict.confidence,
    })));

    Ok(verdict)
}

fn build_prompt(template: &str, payload: &Value) -> String {
    format!(
        "{template}\n\nInput:\n{}",
        serde_json::to_string_pretty(payload).unwrap_or_else(|_| "{}".to_string())
    )
}

/// Enforce token budget for `pass`. On exceed, emit events, flip flags, run
/// single-pass and return `Ok(Some(trace))`. On success, return `Ok(None)`.
async fn check_budget(
    budget: &TokenBudget,
    pass: Pass,
    tokens: u64,
    ctx: &AuditRunContext,
    validated: &ValidatedFinding,
    events: &PipelineEventSink,
    fell_back: &Arc<AtomicBool>,
) -> Result<Option<TraceResult>> {
    match budget.record(pass, tokens) {
        Ok(()) => Ok(None),
        Err(BudgetExceeded { pass, used, cap }) => {
            let finding_id = &validated.finding.finding_id;
            events.emit(IntelligentTaskEvent::new("token_budget_exceeded").with_data(json!({
                "findingId": finding_id,
                "pass": format!("{pass:?}"),
                "used": used,
                "cap": cap,
            })));
            emit_fallback(events, finding_id, "budget_exceeded");
            fell_back.store(true, Ordering::Relaxed);
            ctx.partial_analysis.store(true, Ordering::Relaxed);
            Ok(Some(single_pass_for_finding(ctx, validated, events).await?))
        }
    }
}

/// Dispatch a single retrieval query to the CodeIntelligence backend, returning
/// a serializable result value. Unknown tools are skipped with a warning shape.
async fn dispatch_query(intel: &dyn CodeIntelligence, query: &QueryRequest) -> Value {
    let arg_str = |key: &str| {
        query
            .args
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    };
    let arg_u32 = |key: &str, default: u32| {
        query
            .args
            .get(key)
            .and_then(Value::as_u64)
            .map(|v| v as u32)
            .unwrap_or(default)
    };
    match query.tool.as_str() {
        "get_callers" => to_value(intel.get_callers(&arg_str("symbol"), arg_u32("depth", 2)).await),
        "get_callees" => to_value(intel.get_callees(&arg_str("symbol"), arg_u32("depth", 2)).await),
        "get_context" => to_value(intel.get_context(&arg_str("file"), arg_u32("line", 1)).await),
        "search_symbol" => to_value(intel.search_symbol(&arg_str("name")).await),
        "get_call_chain" => to_value(
            intel
                .get_call_chain(
                    &arg_str("from_file"),
                    arg_u32("from_line", 1),
                    arg_u32("max_hops", 3),
                )
                .await,
        ),
        other => {
            tracing::warn!(tool = %other, "trace pass1 requested unknown tool; skipping");
            json!({"error": format!("unknown tool: {other}")})
        }
    }
}

fn to_value<T: serde::Serialize>(result: anyhow::Result<T>) -> Value {
    match result {
        Ok(value) => serde_json::to_value(value)
            .unwrap_or_else(|err| json!({"error": err.to_string()})),
        Err(err) => json!({"error": err.to_string()}),
    }
}

/// Single-pass fallback: identical to the pre-integration Trace behavior, but
/// scoped to ONE finding so concurrent per-finding fallback works correctly.
async fn single_pass_for_finding(
    ctx: &AuditRunContext,
    validated: &ValidatedFinding,
    events: &PipelineEventSink,
) -> Result<TraceResult> {
    let finding = &validated.finding;
    let payload = json!({
        "dedupeGroups": [{
            "groupId": format!("group-{}", finding.finding_id),
            "canonicalFindingId": finding.finding_id,
            "findingIds": [finding.finding_id],
            "rootCause": finding.description,
            "canonical": {
                "findingId": finding.finding_id,
                "file": finding.file,
                "lineStart": finding.line_start,
                "lineEnd": finding.line_end,
                "vulnClass": finding.vuln_class,
                "description": finding.description,
                "evidence": finding.evidence,
            }
        }],
        "instruction": "For the canonical finding, decide whether attacker-controlled input can reach the sink. Use unknown/false only with rationale.",
        "requiredOutput": {"traces": [{"findingId":"string","reachable":true,"confidence":0.0,"rationale":"string"}]}
    });
    let prompt = stage_prompt(AuditStage::Trace, &payload);
    let output = invoke_json::<TraceOutput>(
        &*ctx.invoker,
        AuditStage::Trace,
        &prompt,
        &ctx.llm_config,
    )
    .await
    .map(|result| {
        events.emit(result.invocation.attempt_event);
        result.payload
    })?;
    let trace = output
        .traces
        .into_iter()
        .find(|t| t.finding_id == finding.finding_id)
        .unwrap_or_else(|| TraceResult {
            finding_id: finding.finding_id.clone(),
            reachable: false,
            confidence: Some(0.0),
            rationale: "single-pass LLM returned no matching trace; defaulting to unreachable"
                .to_string(),
        });
    Ok(trace)
}

/// Single-pass fallback when no ValidatedFinding metadata is available (rare —
/// dedupe references a finding the validate stage didn't produce). Emits a
/// stub trace so the pipeline still has one result per group.
async fn single_pass_for_id(
    ctx: &AuditRunContext,
    finding_id: &str,
    events: &PipelineEventSink,
) -> Result<TraceResult> {
    emit_fallback(events, finding_id, "missing_validation_metadata");
    ctx.partial_analysis.store(true, Ordering::Relaxed);
    Ok(TraceResult {
        finding_id: finding_id.to_string(),
        reachable: false,
        confidence: Some(0.0),
        rationale: "no validated finding metadata available for trace; defaulting to unreachable"
            .to_string(),
    })
}

fn emit_fallback(events: &PipelineEventSink, finding_id: &str, reason: &str) {
    events.emit(IntelligentTaskEvent::new("trace_fallback").with_data(json!({
        "findingId": finding_id,
        "reason": reason,
    })));
}

/// LLM Pass 1 output: a list of structural query requests.
#[derive(Debug, Clone, Deserialize)]
pub struct RetrievalRequest {
    #[serde(default)]
    pub queries: Vec<QueryRequest>,
}

/// One query against the CodeIntelligence trait. `tool` is the method name and
/// `args` is a free-form map validated per-tool during dispatch.
#[derive(Debug, Clone, Deserialize)]
pub struct QueryRequest {
    pub tool: String,
    #[serde(default)]
    pub args: Value,
}

/// Map a file extension to the language string codegraph reports. Returns
/// `None` for unknown extensions so callers can fall back to single-pass.
pub fn map_extension_to_language(file: &str) -> Option<String> {
    let lower = file.to_ascii_lowercase();
    let dot = lower.rfind('.')?;
    let ext = &lower[dot + 1..];
    let lang = match ext {
        "rs" => "rust",
        "py" | "pyi" => "python",
        "ts" => "typescript",
        "tsx" => "tsx",
        "js" | "mjs" | "cjs" => "javascript",
        "jsx" => "jsx",
        "go" => "go",
        "java" => "java",
        "kt" | "kts" => "kotlin",
        "rb" => "ruby",
        "php" => "php",
        "swift" => "swift",
        "scala" => "scala",
        "cs" => "csharp",
        "cpp" | "cc" | "cxx" | "hpp" | "hh" | "hxx" => "cpp",
        "c" | "h" => "c",
        _ => return None,
    };
    Some(lang.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retrieval_request_parses_well_formed_json() {
        let raw = r#"{
            "queries": [
                {"tool": "get_callers", "args": {"symbol": "doStuff", "depth": 2}},
                {"tool": "get_context", "args": {"file": "src/a.rs", "line": 42}}
            ]
        }"#;
        let parsed: RetrievalRequest = serde_json::from_str(raw).expect("parse");
        assert_eq!(parsed.queries.len(), 2);
        assert_eq!(parsed.queries[0].tool, "get_callers");
        assert_eq!(
            parsed.queries[1]
                .args
                .get("file")
                .and_then(Value::as_str)
                .unwrap(),
            "src/a.rs"
        );
    }

    #[test]
    fn retrieval_request_tolerates_missing_queries_field() {
        let raw = r#"{}"#;
        let parsed: RetrievalRequest = serde_json::from_str(raw).expect("parse");
        assert!(parsed.queries.is_empty());
    }

    #[test]
    fn extension_mapping_covers_common_languages() {
        assert_eq!(map_extension_to_language("src/lib.rs").as_deref(), Some("rust"));
        assert_eq!(map_extension_to_language("app/main.py").as_deref(), Some("python"));
        assert_eq!(map_extension_to_language("ui/Button.tsx").as_deref(), Some("tsx"));
        assert_eq!(map_extension_to_language("ui/util.ts").as_deref(), Some("typescript"));
        assert_eq!(map_extension_to_language("server.go").as_deref(), Some("go"));
        assert_eq!(map_extension_to_language("Main.java").as_deref(), Some("java"));
        assert_eq!(map_extension_to_language("a.cpp").as_deref(), Some("cpp"));
        assert_eq!(map_extension_to_language("a.c").as_deref(), Some("c"));
        assert_eq!(map_extension_to_language("README.md"), None);
        assert_eq!(map_extension_to_language("noext"), None);
    }

    #[test]
    fn estimate_tokens_is_monotonic() {
        let short = estimate_tokens("hello");
        let long = estimate_tokens(&"hello".repeat(100));
        assert!(long > short);
    }
}
