//! Hunt stage — vulnerability discovery + dismissal classification.
//!
//! Two-pass dismissal architecture (Plan Phase 1 / AC1.C, mirrors trace.rs:74-105):
//!   * Pass 0 (LLM hunt, single-pass): the existing LLM call that emits the
//!     raw `AuditFinding` records.
//!   * Pass 1 (LLM-directed retrieval): for each finding, ask the LLM which
//!     structural queries to run (`find_taint_through`, `get_callers`, …).
//!     Capped at 5 queries per finding (mirrors trace).
//!   * SoT lookup: for every symbol surfaced by Pass 1 queries, check the
//!     `sanitizer_sot` table. A hit deterministically writes a
//!     `dismissal_evidence` with `confidence_source: RuleMatched` BEFORE Pass 2.
//!   * Pass 2 (LLM reasoning): consume the retrieval results + the SoT
//!     pre-verdict. When `rule_matched=true`, Pass 2 may ONLY fill `rationale`;
//!     the runtime drops any `category`/`confidence_source` it tries to set
//!     (Architect C4 — prompt-injection defence).
//!
//! 6 fallback reasons trigger `partial_analysis.store(true)` and skip the
//! 2-pass flow for that finding (mirror trace.rs:333-358):
//!   `code_intel_none`, `language_not_indexed`, `pre_resolve_failed`,
//!   `budget_exhausted`, `two_pass_error`, `missing_metadata`.

use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use anyhow::Result;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::task::JoinSet;

use crate::runtime::intelligent::agent_runner::{standard_tool_defs, AgentRunConfig};
use crate::runtime::intelligent::code_intel::dead_code::detect_dead_code;
use crate::runtime::intelligent::code_intel::path_classifier::{classify_path, PathCategory};
use crate::runtime::intelligent::code_intel::{lookup_sanitizer, CodeIntelligence};
use crate::runtime::intelligent::token_budget::{BudgetExceeded, Pass, TokenBudget};
use crate::runtime::intelligent::types::IntelligentTaskEvent;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    prompts::{HUNT_PASS1_PROMPT, HUNT_PASS2_PROMPT},
    repo::source_snippets,
    stage_prompt,
    types::{
        AuditFinding, ConfidenceSource, DismissalCategory, DismissalEvidence, HuntOutput, HuntTask,
    },
};

/// Base token budget per finding for the 2-pass dismissal flow.
const BASE_BUDGET_PER_FINDING: u64 = 4_000;

/// Hard cap on retrieval queries per finding in Pass 1 (mirrors trace).
const MAX_QUERIES_PER_FINDING: usize = 5;

/// Coarse heuristic: ~4 chars per token. Used for budget enforcement.
fn estimate_tokens(text: &str) -> u64 {
    ((text.len() as f64) / 4.0).ceil() as u64
}

pub async fn run(
    ctx: &AuditRunContext,
    tasks: &[HuntTask],
    concurrency: usize,
    events: &PipelineEventSink,
    amplification: Option<&str>,
    path_blacklist_extra: &[String],
) -> Result<HuntOutput> {
    let stage = AuditStage::Hunt;
    events.stage_started(stage);

    // Convert the borrowed amplification into an owned String so each spawned
    // task can clone it into its 'static future.
    let amplification: Option<String> = amplification.map(str::to_string);

    let semaphore = Arc::new(tokio::sync::Semaphore::new(concurrency.max(1)));
    let mut join_set: JoinSet<Result<Vec<AuditFinding>>> = JoinSet::new();

    for task in tasks {
        let ctx = ctx.clone();
        let events = events.clone();
        let task = task.clone();
        let sem = Arc::clone(&semaphore);
        let task_amp = amplification.clone();

        join_set.spawn(async move {
            // Acquire permit before calling LLM to bound concurrency.
            let _permit = sem.acquire().await.expect("semaphore closed");
            let snippets = source_snippets(&ctx.archive, &task.target_files, 8_000);
            let payload = json!({
                "task": task,
                "architectureSummary": "",
                "snippets": snippets,
                "requiredOutput": {
                    "findings": [{
                        "findingId":"string",
                        "file":"string (project-root-relative path when scopeType=file)",
                        "cweId":"string (format 'CWE-{digits}'; omit field entirely if cannot determine)",
                        "scopeType":"string ('file' or 'module')",
                        "module":"string (required when scopeType='module')",
                        "lineStart":1,
                        "lineEnd":1,
                        "vulnClass":"string",
                        "severity":"low|medium|high|critical",
                        "description":"string",
                        "evidence_prose":"Natural-language description of the vulnerability mechanism. MUST NOT contain code blocks, file paths, or line numbers.",
                        "evidence_code_snippets":[{"file":"relative/path or null","line_start":1,"line_end":1,"code":"exact code text","language":"rust"}],
                        "confidence":0.0
                    }]
                }
            });
            let mut prompt = stage_prompt(stage, &payload);
            if let Some(amp) = task_amp.as_deref() {
                prompt.push_str(amp);
            }

            let mut output: HuntOutput = if let Some(runner) = &ctx.agent_runner {
                let tools = standard_tool_defs(&["Read", "Grep", "Glob", "Exec"]);
                let config = AgentRunConfig::default();
                let result = runner
                    .run_agent(stage.as_str(), &prompt, payload.clone(), &tools, &config)
                    .await?;
                serde_json::from_value(result.payload)?
            } else {
                invoke_json::<HuntOutput>(&*ctx.invoker, stage, &prompt, &ctx.llm_config, &events)
                    .await?
                    .payload
            };
            for finding in &mut output.findings {
                if finding.task_id.is_none() {
                    finding.task_id = Some(task.task_id.clone());
                }
                // Phase 0 path-pattern path_classifier verdict (single-target only).
                let path_verdict = path_classify_for_task(&task.target_files);
                normalize_finding(finding, &task.target_files, path_verdict.as_ref());

                // Phase 1 two-pass dismissal enrichment. Best-effort: errors
                // here are reported as fallback events but never bubble — the
                // finding survives with whatever path-pattern verdict (if any)
                // normalize_finding already wrote.
                if let Err(err) =
                    enrich_dismissal_two_pass(&ctx, finding, &task, &events).await
                {
                    tracing::debug!(
                        finding_id = %finding.finding_id,
                        error = %err,
                        "hunt two-pass enrichment failed; keeping path_pattern verdict"
                    );
                }
            }
            Ok(output.findings)
        });
    }

    let mut findings = Vec::new();
    while let Some(result) = join_set.join_next().await {
        match result {
            Ok(Ok(task_findings)) => findings.extend(task_findings),
            Ok(Err(err)) => {
                tracing::warn!(error = %err, "hunt task failed; skipping task findings");
                events.emit(
                    IntelligentTaskEvent::new("hunt_task_failed")
                        .with_data(json!({"error": err.to_string()})),
                );
            }
            Err(join_err) => return Err(anyhow::anyhow!("hunt task panicked: {join_err}")),
        }
    }

    // Post-drain blacklist retain: drop findings whose `file` path is blacklisted.
    // For each dropped finding, emit a `finding_blacklisted` event so callers can
    // reconstruct GateFailure.metadata.violated_paths (defense-in-depth via
    // predicate at call site in Step 8).
    let mut dropped_for_blacklist: usize = 0;
    findings.retain(|f| {
        match crate::runtime::intelligent::code_intel::is_blacklisted(
            Path::new(&f.file),
            path_blacklist_extra,
        ) {
            Some(reason) => {
                events.emit(
                    IntelligentTaskEvent::new("finding_blacklisted").with_data(json!({
                        "stage": stage.as_str(),
                        "findingId": f.finding_id,
                        "path": super::sanitize_path_for_event(&f.file),
                        "blacklistReason": reason,
                    })),
                );
                dropped_for_blacklist += 1;
                false
            }
            None => true,
        }
    });
    // dropped_for_blacklist intentionally not surfaced on output; the call-site
    // predicate (Step 8) re-scans the post-retain output and reconstructs
    // GateFailure with metadata.violated_paths if anything is still blacklisted.
    let _ = dropped_for_blacklist; // suppress unused if not logged elsewhere

    let output = HuntOutput { findings };
    events.stage_completed(stage, json!({"findingCount": output.findings.len()}));
    Ok(output)
}

/// Phase 0 path-pattern classifier verdict for the upstream task's
/// `target_files`. Returns `Some` only for single-target tasks (multi-target
/// flows skip path_classifier per the user decision and go straight to LLM
/// Pass 2). Real-code single targets also return `None`.
fn path_classify_for_task(target_files: &[String]) -> Option<DismissalEvidence> {
    if target_files.len() != 1 {
        return None;
    }
    let (category, pattern) = classify_path(Path::new(&target_files[0]));
    let dismissal_category = match category {
        PathCategory::Test => Some(DismissalCategory::Test),
        PathCategory::Vendor => Some(DismissalCategory::Vendor),
        // Blacklisted paths are handled by the is_blacklisted helper in later
        // pipeline steps (reflection / retain filter). The legacy
        // path_classify_for_task path does not yet carry a DismissalCategory
        // for blacklist dirs — treat as real code here so existing behaviour
        // is preserved until those steps are wired in.
        PathCategory::Blacklisted(_) | PathCategory::RealCode => None,
    };
    dismissal_category.map(|category| DismissalEvidence {
        category,
        confidence_source: ConfidenceSource::PathPattern,
        path_pattern: pattern,
        sanitizer_symbols: Vec::new(),
        rationale: None,
    })
}

/// Normalize a freshly-emitted `AuditFinding`:
///   - clamp line numbers,
///   - default empty severity to `"medium"`,
///   - **Plan AC0.F**: write a path-pattern dismissal verdict for single-target
///     tasks landing under known test/vendor paths.
///
/// `path_verdict`, if `Some`, was computed by [`path_classify_for_task`]. We
/// only assign it when the finding has no pre-existing dismissal_evidence —
/// callers must not lose a deterministic rule_matched verdict written by the
/// SoT enrichment path.
fn normalize_finding(
    finding: &mut AuditFinding,
    _target_files: &[String],
    path_verdict: Option<&DismissalEvidence>,
) {
    // Line number sanity.
    if finding.line_start == 0 {
        finding.line_start = 1;
    }
    if finding.line_end == 0 || finding.line_end < finding.line_start {
        finding.line_end = finding.line_start;
    }

    // Severity: empty → "medium".
    if finding.severity.trim().is_empty() {
        finding.severity = "medium".to_string();
    }

    // Confidence: missing/zero → 0.5.
    if finding.confidence.map(|c| c == 0.0).unwrap_or(true) {
        finding.confidence = Some(0.5);
    }

    // Language backfill: if the LLM omitted language or left it blank,
    // derive it from the file extension (AC1.2).
    if finding.language.trim().is_empty() {
        finding.language = map_extension_to_language(&finding.file).unwrap_or_default();
    }

    // Path-pattern dismissal verdict (Phase 0 / AC0.F).
    if finding.dismissal_evidence.is_none() {
        if let Some(verdict) = path_verdict {
            finding.dismissal_evidence = Some(verdict.clone());
        }
    }
}

// ---------------------------------------------------------------------------
// Two-pass dismissal enrichment (Plan Phase 1 / AC1.C)
// ---------------------------------------------------------------------------

/// Resolved language for a finding's file extension. Mirrors trace.rs map.
fn map_extension_to_language(file: &str) -> Option<String> {
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

/// Run Pass 1 + structural retrieval + SoT lookup + Pass 2 for ONE finding.
///
/// Emits a `hunt_fallback` event + flips `ctx.partial_analysis` for each of
/// the 6 fallback reasons. Updates `finding.dismissal_evidence` in place; never
/// downgrades a pre-existing `rule_matched` verdict.
async fn enrich_dismissal_two_pass(
    ctx: &AuditRunContext,
    finding: &mut AuditFinding,
    task: &HuntTask,
    events: &PipelineEventSink,
) -> Result<()> {
    let finding_id = finding.finding_id.clone();

    // Multi-target tasks bypass path_classifier (decided per user); the 2-pass
    // flow still runs against the finding's own `file`. So multi-target only
    // changes whether we have a pre-Pass-2 path-pattern verdict.
    let intel = match &ctx.code_intel {
        Some(intel) if intel.is_available() => intel.clone(),
        _ => {
            emit_fallback(events, &finding_id, "code_intel_none");
            ctx.partial_analysis.store(true, Ordering::SeqCst);
            return Ok(());
        }
    };

    let lang = match map_extension_to_language(&finding.file) {
        Some(lang) => lang,
        None => {
            emit_fallback(events, &finding_id, "language_not_indexed");
            ctx.partial_analysis.store(true, Ordering::SeqCst);
            return Ok(());
        }
    };
    let indexed = intel.languages_indexed();
    if !indexed
        .iter()
        .any(|entry| entry.eq_ignore_ascii_case(&lang))
    {
        emit_fallback(events, &finding_id, "language_not_indexed");
        ctx.partial_analysis.store(true, Ordering::SeqCst);
        return Ok(());
    }

    // Pre-resolve symbol at the finding's file:line — closes the grounding
    // gap (mirror trace.rs:152-166).
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
        ctx.partial_analysis.store(true, Ordering::SeqCst);
        return Ok(());
    }

    let budget = TokenBudget::new(BASE_BUDGET_PER_FINDING);
    let fell_back = Arc::new(AtomicBool::new(false));

    events.emit(
        IntelligentTaskEvent::new("hunt_two_pass_started").with_data(json!({
            "findingId": finding_id,
            "file": finding.file,
            "lineStart": finding.line_start,
            "language": lang,
            "isMultiTarget": task.target_files.len() != 1,
        })),
    );

    let finding_json = json!({
        "findingId": finding.finding_id,
        "file": finding.file,
        "lineStart": finding.line_start,
        "lineEnd": finding.line_end,
        "vulnClass": finding.vuln_class,
        "description": finding.description,
        "evidence": finding.evidence,
    });

    // ── Pass 1: ask LLM which queries to run ───────────────────────────────
    let pass1_payload = json!({
        "finding": finding_json,
        "resolvedSymbol": resolved,
        "maxQueries": MAX_QUERIES_PER_FINDING,
    });
    let pass1_prompt = build_prompt(HUNT_PASS1_PROMPT, &pass1_payload);
    if budget_check(
        &budget,
        Pass::Retrieval,
        estimate_tokens(&pass1_prompt),
        ctx,
        &finding_id,
        events,
        &fell_back,
    ) {
        return Ok(());
    }
    let retrieval = match invoke_json::<RetrievalRequest>(
        &*ctx.invoker,
        AuditStage::Hunt,
        &pass1_prompt,
        &ctx.llm_config,
        events,
    )
    .await
    {
        Ok(result) => result.payload,
        Err(err) => {
            tracing::warn!(finding_id = %finding_id, error = %err, "hunt pass1 invoke failed");
            emit_fallback(events, &finding_id, "two_pass_error");
            ctx.partial_analysis.store(true, Ordering::SeqCst);
            return Ok(());
        }
    };

    let mut queries = retrieval.queries;
    queries.truncate(MAX_QUERIES_PER_FINDING);
    events.emit(
        IntelligentTaskEvent::new("hunt_pass1_queries").with_data(json!({
            "findingId": finding_id,
            "queryCount": queries.len(),
        })),
    );

    // ── Dispatch queries + SoT scan ────────────────────────────────────────
    let mut results: Vec<Value> = Vec::with_capacity(queries.len());
    // Symbols observed on returned taint chains / call edges. Run each through
    // sanitizer_sot::lookup_sanitizer; first hit becomes the deterministic
    // RuleMatched verdict.
    let mut sot_hit: Option<String> = None;
    let mut taint_truncated = false;
    for query in queries {
        let outcome = dispatch_query(&*intel, &query).await;

        // Collect observable symbols from the outcome for SoT scanning.
        scan_symbols_for_sot(&outcome, &lang, &mut sot_hit);
        if outcome
            .get("truncated")
            .and_then(Value::as_bool)
            .unwrap_or(false)
            || outcome
                .get("nodes")
                .and_then(Value::as_array)
                .is_none_or(|arr| arr.is_empty())
                && outcome
                    .get("sink_reached")
                    .and_then(Value::as_bool)
                    .is_some()
        {
            // taint search result: emit truncation event for observability.
            if outcome
                .get("truncated")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                taint_truncated = true;
            }
        }

        results.push(json!({
            "tool": query.tool,
            "args": query.args,
            "result": outcome,
        }));
    }

    if taint_truncated {
        events.emit(
            IntelligentTaskEvent::new("hunt_taint_truncated").with_data(json!({
                "findingId": finding_id,
            })),
        );
    }

    // SoT hit → deterministic RuleMatched verdict written BEFORE Pass 2.
    let rule_matched_before = sot_hit.is_some();
    if let Some(symbol) = sot_hit.as_ref() {
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::Sanitized,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
            sanitizer_symbols: vec![symbol.clone()],
            rationale: None,
        });
    }

    // ── v0.3.b: dead-code channel — runs AFTER path_classifier (normalize_finding)
    //    and SoT, BEFORE Pass 2. Only fires when no deterministic verdict has
    //    been set yet (path_pattern or rule_matched). On hit, write a
    //    DeadCode / RuleMatched verdict and skip Pass 2 entirely — the
    //    dismissal is conclusive.
    let dead_code_hit = if finding.dismissal_evidence.is_none() {
        ctx.archive
            .read_text_file(&finding.file, 256 * 1024)
            .ok()
            .flatten()
            .and_then(|source| {
                detect_dead_code(&source, finding.line_start, &lang).map(|p| p.to_string())
            })
    } else {
        None
    };
    if let Some(pattern) = dead_code_hit.as_ref() {
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::DeadCode,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
            sanitizer_symbols: vec![pattern.clone()],
            rationale: None,
        });
        events.emit(
            IntelligentTaskEvent::new("hunt_dead_code_hit").with_data(json!({
                "findingId": finding_id,
                "pattern": pattern,
            })),
        );
        // Deterministic dismissal — skip Pass 2 LLM call.
        return Ok(());
    }

    // ── Pass 2: reasoning over evidence ────────────────────────────────────
    let pass2_payload = json!({
        "finding": finding_json,
        "resolvedSymbol": resolved,
        "retrievalResults": results,
        "ruleMatched": rule_matched_before,
        "ruleMatchedSymbol": sot_hit,
        "pathPatternHint": finding
            .dismissal_evidence
            .as_ref()
            .and_then(|d| d.path_pattern.clone()),
    });
    let pass2_prompt = build_prompt(HUNT_PASS2_PROMPT, &pass2_payload);
    if budget_check(
        &budget,
        Pass::Reasoning,
        estimate_tokens(&pass2_prompt),
        ctx,
        &finding_id,
        events,
        &fell_back,
    ) {
        return Ok(());
    }

    let verdict = match invoke_json::<HuntPass2Verdict>(
        &*ctx.invoker,
        AuditStage::Hunt,
        &pass2_prompt,
        &ctx.llm_config,
        events,
    )
    .await
    {
        Ok(result) => result.payload,
        Err(err) => {
            tracing::warn!(finding_id = %finding_id, error = %err, "hunt pass2 invoke failed");
            emit_fallback(events, &finding_id, "two_pass_error");
            ctx.partial_analysis.store(true, Ordering::SeqCst);
            return Ok(());
        }
    };

    // Apply verdict, enforcing Architect C4: when rule_matched was pre-set,
    // only `rationale` may be filled by the LLM.
    apply_pass2_verdict(finding, verdict, rule_matched_before);

    events.emit(
        IntelligentTaskEvent::new("hunt_pass2_completed").with_data(json!({
            "findingId": finding_id,
            "category": finding
                .dismissal_evidence
                .as_ref()
                .map(|d| d.category),
            "confidenceSource": finding
                .dismissal_evidence
                .as_ref()
                .map(|d| d.confidence_source),
            "ruleMatched": rule_matched_before,
        })),
    );

    Ok(())
}

/// Enforce token budget for `pass`. On exceed, emit events, flip flags, and
/// return `true` (caller MUST short-circuit). On success returns `false`.
fn budget_check(
    budget: &TokenBudget,
    pass: Pass,
    tokens: u64,
    ctx: &AuditRunContext,
    finding_id: &str,
    events: &PipelineEventSink,
    fell_back: &Arc<AtomicBool>,
) -> bool {
    match budget.record(pass, tokens) {
        Ok(()) => false,
        Err(BudgetExceeded { pass, used, cap }) => {
            events.emit(
                IntelligentTaskEvent::new("token_budget_exceeded").with_data(json!({
                    "findingId": finding_id,
                    "stage": "hunt",
                    "pass": format!("{pass:?}"),
                    "used": used,
                    "cap": cap,
                })),
            );
            emit_fallback(events, finding_id, "budget_exhausted");
            fell_back.store(true, Ordering::SeqCst);
            ctx.partial_analysis.store(true, Ordering::SeqCst);
            true
        }
    }
}

/// Dispatch ONE retrieval query against the CodeIntelligence backend.
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
        "find_taint_through" => to_value(
            intel
                .find_taint_through(&arg_str("source"), &arg_str("sink"), arg_u32("max_hops", 3))
                .await,
        ),
        "get_callers" => to_value(
            intel
                .get_callers(&arg_str("symbol"), arg_u32("depth", 2))
                .await,
        ),
        "get_callees" => to_value(
            intel
                .get_callees(&arg_str("symbol"), arg_u32("depth", 2))
                .await,
        ),
        "get_context" => to_value(
            intel
                .get_context(&arg_str("file"), arg_u32("line", 1))
                .await,
        ),
        "search_symbol" => to_value(intel.search_symbol(&arg_str("name")).await),
        other => {
            tracing::warn!(tool = %other, "hunt pass1 requested unknown tool; skipping");
            json!({"error": format!("unknown tool: {other}")})
        }
    }
}

fn to_value<T: serde::Serialize>(result: anyhow::Result<T>) -> Value {
    match result {
        Ok(value) => {
            serde_json::to_value(value).unwrap_or_else(|err| json!({"error": err.to_string()}))
        }
        Err(err) => json!({"error": err.to_string()}),
    }
}

/// Walk JSON output looking for `symbol` fields and run them through the
/// sanitizer SoT. First hit wins (sets `sot_hit`).
fn scan_symbols_for_sot(value: &Value, language: &str, sot_hit: &mut Option<String>) {
    if sot_hit.is_some() {
        return;
    }
    match value {
        Value::Object(map) => {
            if let Some(sym) = map.get("symbol").and_then(Value::as_str) {
                if let Some(canonical) = lookup_sanitizer(language, sym) {
                    *sot_hit = Some(canonical.to_string());
                    return;
                }
            }
            for v in map.values() {
                scan_symbols_for_sot(v, language, sot_hit);
                if sot_hit.is_some() {
                    return;
                }
            }
        }
        Value::Array(arr) => {
            for v in arr {
                scan_symbols_for_sot(v, language, sot_hit);
                if sot_hit.is_some() {
                    return;
                }
            }
        }
        _ => {}
    }
}

/// Apply Pass 2 verdict, enforcing the rule_matched override discipline.
///
/// - When `rule_matched_before` is true, the existing dismissal_evidence
///   (RuleMatched / Sanitized / sanitizer_symbols) is preserved; only the
///   `rationale` field is filled from the LLM verdict.
/// - When false, the LLM verdict's category / confidence_source apply. If the
///   finding has a pre-existing path-pattern verdict (from normalize_finding),
///   the LLM may produce a contradictory category — we KEEP the path-pattern
///   verdict's category (PathPattern is also deterministic, plan §AC1.C
///   methodology rule 2.b). The LLM's rationale is still preserved.
/// - When the LLM provides no dismissal_evidence at all and nothing was
///   pre-set, the finding is left with no dismissal verdict (treated as real).
fn apply_pass2_verdict(
    finding: &mut AuditFinding,
    verdict: HuntPass2Verdict,
    rule_matched_before: bool,
) {
    let Some(llm_evidence) = verdict.dismissal_evidence else {
        return;
    };
    match finding.dismissal_evidence.as_mut() {
        Some(existing) => {
            // Pre-set verdict. Drop LLM category/confidence_source override;
            // only the rationale flows through.
            let _ = rule_matched_before; // documented above
            if let Some(rationale) = llm_evidence.rationale {
                if existing.rationale.is_none() {
                    existing.rationale = Some(rationale);
                }
            }
        }
        None => {
            // No pre-set verdict — accept the LLM's full verdict.
            finding.dismissal_evidence = Some(DismissalEvidence {
                category: llm_evidence.category.unwrap_or(DismissalCategory::Real),
                confidence_source: llm_evidence
                    .confidence_source
                    .unwrap_or(ConfidenceSource::LlmInferred),
                path_pattern: None,
                sanitizer_symbols: llm_evidence.sanitizer_symbols.unwrap_or_default(),
                rationale: llm_evidence.rationale,
            });
        }
    }
}

fn build_prompt(template: &str, payload: &Value) -> String {
    format!(
        "{template}\n\nInput:\n{}",
        serde_json::to_string_pretty(payload).unwrap_or_else(|_| "{}".to_string())
    )
}

fn emit_fallback(events: &PipelineEventSink, finding_id: &str, reason: &str) {
    events.emit(IntelligentTaskEvent::new("hunt_fallback").with_data(json!({
        "findingId": finding_id,
        "reason": reason,
    })));
}

/// LLM Pass 1 output: list of structural query requests.
#[derive(Debug, Clone, Deserialize)]
pub struct RetrievalRequest {
    #[serde(default)]
    pub queries: Vec<QueryRequest>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct QueryRequest {
    pub tool: String,
    #[serde(default)]
    pub args: Value,
}

/// LLM Pass 2 output: a dismissal verdict for ONE finding. All fields are
/// optional — the LLM may omit any subset, in which case the runtime fills
/// defaults or preserves a pre-existing verdict (see [`apply_pass2_verdict`]).
#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct HuntPass2Verdict {
    #[serde(default)]
    pub finding_id: String,
    #[serde(default)]
    pub dismissal_evidence: Option<HuntPass2DismissalEvidence>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct HuntPass2DismissalEvidence {
    #[serde(default)]
    pub category: Option<DismissalCategory>,
    #[serde(default)]
    pub confidence_source: Option<ConfidenceSource>,
    #[serde(default)]
    pub sanitizer_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub rationale: Option<String>,
}

/// Test-only re-export: calls `normalize_finding` with no targets and no
/// path verdict, exercising only the field-backfill logic.
#[cfg(test)]
pub fn normalize_finding_for_test(finding: &mut AuditFinding) {
    normalize_finding(finding, &[], None);
}

// ---------------------------------------------------------------------------
// AC2.4 test infrastructure — stub invoker
// ---------------------------------------------------------------------------

#[cfg(test)]
mod stub {
    use async_trait::async_trait;
    use std::sync::{Arc, Mutex};

    use crate::runtime::intelligent::llm::{
        IntelligentLlmInvocation, IntelligentLlmInvocationError, IntelligentLlmInvoker,
    };
    use crate::runtime::intelligent::{
        config::IntelligentLlmConfig,
        types::{now_rfc3339, IntelligentTaskEvent},
    };

    /// A stub invoker whose responses are pre-queued.
    /// Each call pops the front of the queue: `Ok(content)` or `Err(msg)`.
    pub struct QueuedStubInvoker {
        pub queue: Arc<Mutex<std::collections::VecDeque<Result<String, String>>>>,
    }

    impl QueuedStubInvoker {
        pub fn new(responses: Vec<Result<String, String>>) -> Self {
            Self {
                queue: Arc::new(Mutex::new(responses.into_iter().collect())),
            }
        }
    }

    #[async_trait]
    impl IntelligentLlmInvoker for QueuedStubInvoker {
        async fn invoke(
            &self,
            _prompt: &str,
            _config: &IntelligentLlmConfig,
        ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
            let entry = self
                .queue
                .lock()
                .unwrap()
                .pop_front()
                .unwrap_or(Err("queue empty".to_string()));
            match entry {
                Ok(content) => Ok(IntelligentLlmInvocation {
                    content,
                    finished_at: now_rfc3339(),
                    attempt_event: IntelligentTaskEvent::new("llm_attempt"),
                }),
                Err(msg) => Err(IntelligentLlmInvocationError {
                    stage: "llm_request",
                    redacted_message: msg,
                    attempt_event: IntelligentTaskEvent::new("llm_attempt"),
                }),
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::stub::QueuedStubInvoker;
    use super::*;
    use crate::runtime::intelligent::audit_pipeline::{
        context::{AuditRunContext, PipelineEventSink},
        repo::ProjectArchive,
        types::HuntTask,
    };
    use crate::runtime::intelligent::config::{IntelligentLlmConfig, IntelligentLlmProvider};
    use std::sync::Arc;
    use tokio::sync::broadcast;

    fn make_test_llm_config() -> IntelligentLlmConfig {
        IntelligentLlmConfig {
            row_id: "test".to_string(),
            provider: IntelligentLlmProvider::OpenAiCompatible,
            model: "gpt-test".to_string(),
            base_url: reqwest::Url::parse("https://api.example.com/v1/").unwrap(),
            api_key: "sk-test".to_string(),
            fingerprint: "sha256:test".to_string(),
            timeout_ms: 5000,
            temperature: 0.0,
            max_tokens_per_call: 128,
            first_token_timeout_seconds: 5,
            stream_timeout_seconds: 10,
            custom_header_names: vec![],
            auth_kind: "openai_compatible_bearer",
        }
    }

    fn make_test_sink() -> PipelineEventSink {
        let (broadcast_tx, _) = broadcast::channel(64);
        PipelineEventSink::new(broadcast_tx).0
    }

    fn make_hunt_task(id: &str) -> HuntTask {
        HuntTask {
            task_id: id.to_string(),
            target_files: vec!["src/dummy.rs".to_string()],
            ..Default::default()
        }
    }

    /// AC2.4: when one hunt task fails, the stage returns Ok with findings
    /// from the remaining successful tasks.
    #[tokio::test]
    async fn hunt_run_tolerates_single_task_failure() {
        // 3 tasks: task-ok-a succeeds (1 finding), task-fail errors, task-ok-b succeeds (1 finding).
        // invoke_json calls invoker.invoke() once per task (no repair needed since JSON is valid).
        let ok_response_a = r#"{"findings":[{"findingId":"f-a","file":"src/a.rs","lineStart":10,"lineEnd":10,"vulnClass":"sqli","severity":"high","description":"desc-a","evidence":"ev-a","confidence":0.8}]}"#;
        let ok_response_b = r#"{"findings":[{"findingId":"f-b","file":"src/b.rs","lineStart":20,"lineEnd":20,"vulnClass":"xss","severity":"medium","description":"desc-b","evidence":"ev-b","confidence":0.7}]}"#;

        let invoker = Arc::new(QueuedStubInvoker::new(vec![
            Ok(ok_response_a.to_string()),
            Err("HTTP 429 rate limited".to_string()),
            Ok(ok_response_b.to_string()),
        ]));

        let archive = ProjectArchive::new("/nonexistent", "test.zip");
        let ctx = AuditRunContext::new(
            "task-test".to_string(),
            "proj-test".to_string(),
            "Test Project".to_string(),
            archive,
            vec![],
            make_test_llm_config(),
            invoker,
        );

        let tasks = vec![
            make_hunt_task("task-ok-a"),
            make_hunt_task("task-fail"),
            make_hunt_task("task-ok-b"),
        ];

        let sink = make_test_sink();
        let result = run(&ctx, &tasks, 3, &sink, None, &[]).await;

        assert!(
            result.is_ok(),
            "hunt run must return Ok even when one task fails: {result:?}"
        );
        let output = result.unwrap();
        // Should have findings from both successful tasks.
        assert_eq!(
            output.findings.len(),
            2,
            "expected 2 findings from 2 successful tasks, got {}",
            output.findings.len()
        );
        let ids: Vec<&str> = output
            .findings
            .iter()
            .map(|f| f.finding_id.as_str())
            .collect();
        assert!(ids.contains(&"f-a"), "missing finding f-a");
        assert!(ids.contains(&"f-b"), "missing finding f-b");
    }

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
        let path_verdict = path_classify_for_task(&targets);
        normalize_finding(&mut finding, &targets, path_verdict.as_ref());
        let evidence = finding
            .dismissal_evidence
            .expect("test path must produce dismissal_evidence");
        assert_eq!(evidence.category, DismissalCategory::Test);
        assert_eq!(evidence.confidence_source, ConfidenceSource::PathPattern);
        assert_eq!(evidence.path_pattern.as_deref(), Some("tests/"));
        assert!(evidence.sanitizer_symbols.is_empty());
        assert!(evidence.rationale.is_none());
    }

    /// Real code single target leaves dismissal_evidence None.
    #[test]
    fn normalize_finding_leaves_real_code_evidence_none() {
        let mut finding = base_finding();
        finding.file = "src/handler.rs".to_string();
        let targets = vec!["src/handler.rs".to_string()];
        let path_verdict = path_classify_for_task(&targets);
        normalize_finding(&mut finding, &targets, path_verdict.as_ref());
        assert!(finding.dismissal_evidence.is_none());
    }

    /// Vendor path produces Vendor category + PathPattern source.
    #[test]
    fn normalize_finding_writes_vendor_evidence() {
        let mut finding = base_finding();
        finding.file = "vendor/lib/foo.go".to_string();
        let targets = vec!["vendor/lib/foo.go".to_string()];
        let path_verdict = path_classify_for_task(&targets);
        normalize_finding(&mut finding, &targets, path_verdict.as_ref());
        let evidence = finding
            .dismissal_evidence
            .expect("vendor path must produce dismissal_evidence");
        assert_eq!(evidence.category, DismissalCategory::Vendor);
        assert_eq!(evidence.confidence_source, ConfidenceSource::PathPattern);
        assert_eq!(evidence.path_pattern.as_deref(), Some("vendor/"));
    }

    /// Multi-target tasks bypass path_classifier (returns None verdict).
    #[test]
    fn path_classify_skips_multi_target() {
        let targets = vec!["tests/a.rs".to_string(), "tests/b.rs".to_string()];
        assert!(path_classify_for_task(&targets).is_none());
    }

    /// Empty target_files: no verdict.
    #[test]
    fn path_classify_skips_empty_targets() {
        let targets: Vec<String> = vec![];
        assert!(path_classify_for_task(&targets).is_none());
    }

    /// Pre-existing dismissal_evidence is not overwritten by normalize_finding.
    #[test]
    fn normalize_finding_preserves_existing_evidence() {
        let mut finding = base_finding();
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::Sanitized,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
            sanitizer_symbols: vec!["psycopg2.sql.SQL".to_string()],
            rationale: None,
        });
        let targets = vec!["tests/something.rs".to_string()];
        let path_verdict = path_classify_for_task(&targets);
        normalize_finding(&mut finding, &targets, path_verdict.as_ref());
        let evidence = finding.dismissal_evidence.expect("preserved");
        assert_eq!(evidence.category, DismissalCategory::Sanitized);
        assert_eq!(evidence.confidence_source, ConfidenceSource::RuleMatched);
        assert_eq!(evidence.sanitizer_symbols, vec!["psycopg2.sql.SQL"]);
    }

    /// SoT hit → RuleMatched verdict; LLM Pass 2 attempt to flip
    /// category/confidence_source is dropped, only rationale survives.
    #[test]
    fn apply_pass2_verdict_rule_matched_blocks_category_override() {
        let mut finding = base_finding();
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::Sanitized,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
            sanitizer_symbols: vec!["psycopg2.sql.SQL".to_string()],
            rationale: None,
        });
        let verdict = HuntPass2Verdict {
            finding_id: "f1".to_string(),
            dismissal_evidence: Some(HuntPass2DismissalEvidence {
                category: Some(DismissalCategory::Real),
                confidence_source: Some(ConfidenceSource::LlmInferred),
                sanitizer_symbols: Some(vec![]),
                rationale: Some("LLM thinks this is real (should be ignored)".to_string()),
            }),
        };
        apply_pass2_verdict(&mut finding, verdict, /*rule_matched_before=*/ true);
        let evidence = finding.dismissal_evidence.expect("preserved");
        // The category/confidence_source MUST NOT flip.
        assert_eq!(evidence.category, DismissalCategory::Sanitized);
        assert_eq!(evidence.confidence_source, ConfidenceSource::RuleMatched);
        assert_eq!(evidence.sanitizer_symbols, vec!["psycopg2.sql.SQL"]);
        // Rationale flows through.
        assert!(evidence.rationale.is_some());
        assert!(evidence
            .rationale
            .unwrap()
            .contains("LLM thinks this is real"));
    }

    /// No SoT hit + path-pattern present → category stays PathPattern; LLM
    /// rationale flows through.
    #[test]
    fn apply_pass2_verdict_path_pattern_preserved() {
        let mut finding = base_finding();
        finding.dismissal_evidence = Some(DismissalEvidence {
            category: DismissalCategory::Test,
            confidence_source: ConfidenceSource::PathPattern,
            path_pattern: Some("tests/".to_string()),
            sanitizer_symbols: Vec::new(),
            rationale: None,
        });
        let verdict = HuntPass2Verdict {
            finding_id: "f1".to_string(),
            dismissal_evidence: Some(HuntPass2DismissalEvidence {
                category: Some(DismissalCategory::Real),
                confidence_source: Some(ConfidenceSource::LlmInferred),
                sanitizer_symbols: None,
                rationale: Some("caller lives in tests/".to_string()),
            }),
        };
        apply_pass2_verdict(&mut finding, verdict, /*rule_matched_before=*/ false);
        let evidence = finding.dismissal_evidence.expect("preserved");
        // The path_pattern category stays — apply_pass2_verdict mutates only
        // the rationale slot when there's a pre-set verdict.
        assert_eq!(evidence.category, DismissalCategory::Test);
        assert_eq!(evidence.confidence_source, ConfidenceSource::PathPattern);
        assert_eq!(evidence.path_pattern.as_deref(), Some("tests/"));
        assert_eq!(
            evidence.rationale.as_deref(),
            Some("caller lives in tests/")
        );
    }

    /// No pre-set verdict + LLM verdict → LLM verdict applied fully.
    #[test]
    fn apply_pass2_verdict_accepts_llm_when_no_preset() {
        let mut finding = base_finding();
        finding.file = "src/handler.rs".to_string();
        finding.dismissal_evidence = None;
        let verdict = HuntPass2Verdict {
            finding_id: "f1".to_string(),
            dismissal_evidence: Some(HuntPass2DismissalEvidence {
                category: Some(DismissalCategory::Sanitized),
                confidence_source: Some(ConfidenceSource::LlmInferred),
                sanitizer_symbols: Some(vec!["custom_validator".to_string()]),
                rationale: Some("LLM observed a custom validator".to_string()),
            }),
        };
        apply_pass2_verdict(&mut finding, verdict, /*rule_matched_before=*/ false);
        let evidence = finding.dismissal_evidence.expect("set");
        assert_eq!(evidence.category, DismissalCategory::Sanitized);
        assert_eq!(evidence.confidence_source, ConfidenceSource::LlmInferred);
        assert_eq!(evidence.sanitizer_symbols, vec!["custom_validator"]);
        assert_eq!(
            evidence.rationale.as_deref(),
            Some("LLM observed a custom validator")
        );
    }

    /// SoT scan finds a Python sanitizer symbol from a nested call-chain JSON.
    #[test]
    fn scan_symbols_for_sot_finds_python_psycopg2() {
        let outcome = json!({
            "nodes": [
                {"symbol": "handle_lookup", "file": "app.py", "line": 10, "hopIndex": 0},
                {"symbol": "psycopg2.sql.SQL", "file": "db.py", "line": 12, "hopIndex": 1}
            ],
            "truncated": false,
            "sinkReached": true
        });
        let mut hit = None;
        scan_symbols_for_sot(&outcome, "python", &mut hit);
        assert_eq!(hit.as_deref(), Some("psycopg2.sql.SQL"));
    }

    /// SoT scan miss: no matching symbol leaves hit=None.
    #[test]
    fn scan_symbols_for_sot_miss() {
        let outcome = json!({
            "nodes": [
                {"symbol": "build_query", "file": "db.py", "line": 7},
                {"symbol": "run_query", "file": "db.py", "line": 10}
            ]
        });
        let mut hit = None;
        scan_symbols_for_sot(&outcome, "python", &mut hit);
        assert!(hit.is_none());
    }

    /// Java fully-qualified PreparedStatement is recognised via suffix match.
    #[test]
    fn scan_symbols_for_sot_java_prepared_statement_qualified() {
        let outcome = json!({
            "nodes": [
                {"symbol": "java.sql.PreparedStatement", "file": "X.java", "line": 1}
            ]
        });
        let mut hit = None;
        scan_symbols_for_sot(&outcome, "java", &mut hit);
        assert_eq!(hit.as_deref(), Some("PreparedStatement"));
    }
}
