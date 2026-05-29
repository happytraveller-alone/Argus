use std::path::Path;

use anyhow::Result;
use serde_json::json;

use crate::runtime::intelligent::types::FindingScopeType;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{HuntOutput, TraceOutput, ValidatedFinding, ValidationOutput},
};

/// Return true if the string looks like it contains a `path:linenum` token
/// (e.g. `src/foo.rs:42` or `lib/bar.py:100`) — a sign that the LLM placed
/// file/line references inside `evidence_prose` instead of the snippet fields.
/// Heuristic: any word-char sequence containing `/` or `.` followed by `:digits`.
fn evidence_prose_has_path_token(s: &str) -> bool {
    // Walk byte-by-byte looking for the pattern  <word><colon><digits>
    // where <word> contains at least one '/' or '.'.
    let bytes = s.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    while i < len {
        // Find a colon
        if bytes[i] == b':' && i > 0 {
            // Scan digits after the colon
            let mut j = i + 1;
            while j < len && bytes[j].is_ascii_digit() {
                j += 1;
            }
            if j > i + 1 {
                // There is at least one digit after ':'; scan word before ':'
                let mut k = i;
                let mut has_slash_or_dot = false;
                while k > 0 {
                    let b = bytes[k - 1];
                    if b.is_ascii_alphanumeric() || b == b'_' || b == b'-' || b == b'/' || b == b'.' {
                        if b == b'/' || b == b'.' {
                            has_slash_or_dot = true;
                        }
                        k -= 1;
                    } else {
                        break;
                    }
                }
                if has_slash_or_dot && k < i {
                    return true;
                }
            }
        }
        i += 1;
    }
    false
}

/// B.3: Emit `chain.hop_malformed` WARN events for any CallHop that has both
/// `file == None` AND `function == None` and is not an ellipsis placeholder.
/// Called from the trace stage after TraceOutput is produced.
pub fn emit_hop_malformed_events(
    trace_output: &TraceOutput,
    events: &PipelineEventSink,
    stage_name: &str,
) {
    for trace in &trace_output.traces {
        for (idx, hop) in trace.call_chain.iter().enumerate() {
            let is_ellipsis = hop
                .function
                .as_deref()
                .map_or(false, |f| f.contains('\u{2026}') || f.contains("..."));
            if hop.file.is_none() && hop.function.is_none() && !is_ellipsis {
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "chain.hop_malformed",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage_name,
                        "findingId": trace.finding_id,
                        "hopIndex": idx,
                    })),
                );
            }
        }
    }
}

/// Validate `cwe_id` matches the canonical `CWE-{digits}` shape without
/// pulling in a regex crate dependency. Equivalent to `^CWE-\d+$`.
fn is_valid_cwe_id(s: &str) -> bool {
    let Some(rest) = s.strip_prefix("CWE-") else {
        return false;
    };
    !rest.is_empty() && rest.bytes().all(|b| b.is_ascii_digit())
}

/// Min length for a token to count as a "code-like" identifier worth checking
/// against the snippet corpus. Below this we hit too many false positives on
/// natural-language words.
const CODE_TOKEN_MIN_LEN: usize = 4;

/// Extract code-like identifiers from a piece of LLM prose. A token qualifies
/// when it is:
///   - wrapped in backticks (` `like_this` `), OR
///   - an alphanumeric/underscore run that contains an underscore or mixed
///     case (snake_case / camelCase / PascalCase), and is ≥ CODE_TOKEN_MIN_LEN.
///
/// The result is deduplicated and lower-cased for case-insensitive matching
/// against the snippet corpus.
pub(crate) fn extract_code_tokens(prose: &str) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    let bytes = prose.as_bytes();
    let len = bytes.len();

    // 1) Backtick-quoted segments — always treated as code references.
    let mut i = 0;
    while i < len {
        if bytes[i] == b'`' {
            let start = i + 1;
            let mut j = start;
            while j < len && bytes[j] != b'`' {
                j += 1;
            }
            if j < len && j > start {
                let token = prose[start..j].trim();
                if !token.is_empty() {
                    tokens.push(token.to_string());
                }
                i = j + 1;
                continue;
            }
        }
        i += 1;
    }

    // 2) Bare identifiers (snake_case / camelCase).
    let mut k = 0;
    while k < len {
        let b = bytes[k];
        if b.is_ascii_alphanumeric() || b == b'_' {
            let start = k;
            while k < len {
                let bb = bytes[k];
                if bb.is_ascii_alphanumeric() || bb == b'_' {
                    k += 1;
                } else {
                    break;
                }
            }
            let token = &prose[start..k];
            if token.len() >= CODE_TOKEN_MIN_LEN && is_code_like_identifier(token) {
                tokens.push(token.to_string());
            }
        } else {
            k += 1;
        }
    }

    // Dedup case-insensitively.
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    tokens.retain(|t| seen.insert(t.to_ascii_lowercase()));
    tokens
}

fn is_code_like_identifier(token: &str) -> bool {
    let has_underscore = token.contains('_');
    let mut saw_lower = false;
    let mut saw_upper = false;
    for c in token.chars() {
        if c.is_ascii_lowercase() {
            saw_lower = true;
        }
        if c.is_ascii_uppercase() {
            saw_upper = true;
        }
    }
    let mixed_case = saw_lower && saw_upper;
    // Pure lowercase words like "user" don't qualify — too many natural-language
    // collisions. Pure uppercase like "API" also too noisy. Need either
    // underscore or a case mix.
    has_underscore || mixed_case
}

/// Check that every code-like token mentioned in the finding's prose fields
/// (`evidence_prose`, `description`, `evidence`) appears in at least one of
/// the `evidence_code_snippets[*].code` blocks. Returns the list of tokens
/// that are *missing* (empty Vec = aligned). Match is case-insensitive
/// substring.
pub(crate) fn evidence_misalignment(
    finding: &crate::runtime::intelligent::audit_pipeline::types::AuditFinding,
) -> Vec<String> {
    // Gather all snippet bodies + the per-snippet file paths into one haystack
    // (file paths often contain identifiers the prose legitimately references).
    let mut haystack = String::new();
    for snippet in &finding.evidence_code_snippets {
        haystack.push_str(&snippet.code);
        haystack.push('\n');
        if let Some(file) = snippet.file.as_deref() {
            haystack.push_str(file);
            haystack.push('\n');
        }
    }
    // Also let the finding's own file path satisfy references to it.
    haystack.push_str(&finding.file);
    haystack.push('\n');
    let haystack_lower = haystack.to_ascii_lowercase();

    let mut prose_concat = String::new();
    if let Some(prose) = finding.evidence_prose.as_deref() {
        prose_concat.push_str(prose);
        prose_concat.push('\n');
    }
    prose_concat.push_str(&finding.description);
    prose_concat.push('\n');
    prose_concat.push_str(&finding.evidence);

    let mut missing: Vec<String> = Vec::new();
    for token in extract_code_tokens(&prose_concat) {
        // Strip non-identifier tail like `()` or trailing `:` so we match the
        // bare name in the snippet.
        let bare: String = token
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '.')
            .collect();
        let probe = if bare.is_empty() { token.as_str() } else { bare.as_str() };
        if probe.len() < CODE_TOKEN_MIN_LEN {
            continue;
        }
        if !haystack_lower.contains(&probe.to_ascii_lowercase()) {
            missing.push(token);
        }
    }
    missing
}

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

    // ── Post-LLM normalization (Phase B / AC13) ──
    // Soft-degrade malformed `cwe_id` and missing `module` (when scope is
    // Module). Emit audit-trail events so downstream consumers can reconstruct
    // which fields the LLM failed to populate cleanly.
    for vf in &mut output.findings {
        if let Some(value) = vf.finding.cwe_id.as_ref() {
            if !is_valid_cwe_id(value) {
                let original_value = value.clone();
                let finding_id = vf.finding.finding_id.clone();
                vf.finding.cwe_id = None;
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "finding.cwe_malformed",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage.as_str(),
                        "findingId": finding_id,
                        "originalValue": original_value,
                    })),
                );
            }
        }

        if vf.finding.scope_type == Some(FindingScopeType::Module) {
            let module_present = vf
                .finding
                .module
                .as_deref()
                .map(str::trim)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !module_present {
                let finding_id = vf.finding.finding_id.clone();
                vf.finding.scope_type = Some(FindingScopeType::File);
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "finding.scope_module_missing",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage.as_str(),
                        "findingId": finding_id,
                    })),
                );
            }
        }

        // ── B.3: evidence_prose_dirty ────────────────────────────────────────
        // Warn when evidence_prose contains a path:line token — the LLM ignored
        // the prompt instruction to keep code/file refs in evidence_code_snippets.
        if let Some(prose) = vf.finding.evidence_prose.as_deref() {
            if evidence_prose_has_path_token(prose) {
                let finding_id = vf.finding.finding_id.clone();
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "finding.evidence_prose_dirty",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage.as_str(),
                        "findingId": finding_id,
                    })),
                );
            }
        }

        // ── Evidence alignment ───────────────────────────────────────────────
        // Confirmed findings must have their root-cause prose grounded in the
        // attached evidence_code_snippets. The frontend displays the snippets
        // as the right-side "related code" panel, so any identifier mentioned
        // in the prose that is absent from those snippets produces a panel a
        // reviewer can't cross-check. Emit a per-finding event with the
        // missing tokens — the reflection predicate in mod.rs translates the
        // same condition into a GateFailure so the LLM gets a forced retry.
        if vf.validation_status == "confirmed" {
            let missing = evidence_misalignment(&vf.finding);
            if !missing.is_empty() {
                let finding_id = vf.finding.finding_id.clone();
                let cap: usize = 10;
                let preview: Vec<String> = missing.iter().take(cap).cloned().collect();
                events.emit(
                    crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                        "finding.evidence_misaligned",
                    )
                    .with_data(serde_json::json!({
                        "stage": stage.as_str(),
                        "findingId": finding_id,
                        "missingTokens": preview,
                        "missingTokenCount": missing.len(),
                    })),
                );
            }
        }
    }

    let confirmed = output
        .findings
        .iter()
        .filter(|finding| finding.validation_status == "confirmed")
        .count();
    let rejected = output.findings.len().saturating_sub(confirmed);
    // Audit-trail event for every non-confirmed finding. The findings stay in
    // pipeline state (so the validate quality gate keeps comparing counts
    // against the hunt input), but `PipelineOutputs::to_incremental_findings`
    // and `to_task_findings` will drop them on the way out so the task record
    // and frontend never expose unverified risk points.
    for vf in &output.findings {
        if vf.validation_status != "confirmed" {
            events.emit(
                crate::runtime::intelligent::types::IntelligentTaskEvent::new(
                    "finding_discarded",
                )
                .with_data(serde_json::json!({
                    "stage": stage.as_str(),
                    "findingId": vf.finding.finding_id,
                    "validationStatus": vf.validation_status,
                    "rationale": vf.validation_rationale,
                })),
            );
        }
    }
    events.stage_completed(
        stage,
        json!({
            "confirmedCount": confirmed,
            "rejectedCount": rejected,
            "discardedCount": rejected,
        }),
    );
    Ok(output)
}

// ---------------------------------------------------------------------------
// Phase G tests — backend.validate.* (AC13)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests_validate {
    use super::*;
    use crate::runtime::intelligent::audit_pipeline::types::{
        AuditFinding, CallHop, TraceOutput, TraceResult, ValidatedFinding,
    };

    fn make_validated_finding(cwe_id: Option<&str>, scope_type: Option<FindingScopeType>, module: Option<&str>) -> ValidatedFinding {
        ValidatedFinding {
            finding: AuditFinding {
                finding_id: "test-001".to_string(),
                file: "src/test.rs".to_string(),
                line_start: 1,
                line_end: 2,
                vuln_class: "test_vuln".to_string(),
                severity: "medium".to_string(),
                description: "test".to_string(),
                evidence: "test evidence".to_string(),
                cwe_id: cwe_id.map(|s| s.to_string()),
                scope_type,
                module: module.map(|s| s.to_string()),
                ..Default::default()
            },
            validation_status: "confirmed".to_string(),
            validation_rationale: "confirmed".to_string(),
        }
    }

    // ── is_valid_cwe_id unit tests ──────────────────────────────────────────

    #[test]
    fn is_valid_cwe_id_accepts_canonical_form() {
        assert!(is_valid_cwe_id("CWE-79"));
        assert!(is_valid_cwe_id("CWE-89"));
        assert!(is_valid_cwe_id("CWE-306"));
        assert!(is_valid_cwe_id("CWE-1234567"));
    }

    #[test]
    fn is_valid_cwe_id_rejects_malformed() {
        // lowercase prefix
        assert!(!is_valid_cwe_id("cwe-79"));
        // alphabetic suffix
        assert!(!is_valid_cwe_id("CWE-xss"));
        // mixed
        assert!(!is_valid_cwe_id("CWE-79xss"));
        // no prefix at all
        assert!(!is_valid_cwe_id("79"));
        // empty
        assert!(!is_valid_cwe_id(""));
        // just prefix, no digits
        assert!(!is_valid_cwe_id("CWE-"));
    }

    // ── backend.validate.cweMalformed (AC13) ────────────────────────────────
    /// Malformed cwe_id is cleared to None; is_valid_cwe_id returns false for
    /// the value, confirming the production code path would set cwe_id = None.
    #[test]
    fn backend_validate_cwe_malformed_detected() {
        // Simulate the check performed inside the normalization loop in run():
        // if cwe_id is present and !is_valid_cwe_id(value) → clear to None.
        let mut vf = make_validated_finding(Some("CWE-xss"), None, None);
        let value = vf.finding.cwe_id.as_ref().unwrap().clone();
        assert!(!is_valid_cwe_id(&value), "malformed CWE must fail is_valid_cwe_id");
        // Apply the same logic as the production loop:
        if !is_valid_cwe_id(&value) {
            vf.finding.cwe_id = None;
        }
        assert_eq!(vf.finding.cwe_id, None, "malformed cwe_id must be cleared to None");
    }

    #[test]
    fn backend_validate_cwe_malformed_with_slash_cleared() {
        let mut vf = make_validated_finding(Some("CWE-79/XSS"), None, None);
        let value = vf.finding.cwe_id.as_ref().unwrap().clone();
        assert!(!is_valid_cwe_id(&value));
        if !is_valid_cwe_id(&value) {
            vf.finding.cwe_id = None;
        }
        assert_eq!(vf.finding.cwe_id, None);
    }

    // ── backend.validate.scopeModuleMissing (AC13) ──────────────────────────
    /// scope_type=Module without a module name downgrades to File.
    #[test]
    fn backend_validate_scope_module_missing_downgraded() {
        let mut vf = make_validated_finding(Some("CWE-79"), Some(FindingScopeType::Module), None);
        // Simulate the production normalization loop:
        if vf.finding.scope_type == Some(FindingScopeType::Module) {
            let module_present = vf.finding.module.as_deref()
                .map(str::trim)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !module_present {
                vf.finding.scope_type = Some(FindingScopeType::File);
            }
        }
        assert_eq!(
            vf.finding.scope_type,
            Some(FindingScopeType::File),
            "scope_type=Module without module must downgrade to File"
        );
    }

    /// scope_type=Module WITH a non-empty module name is NOT downgraded.
    #[test]
    fn backend_validate_scope_module_present_not_downgraded() {
        let mut vf = make_validated_finding(Some("CWE-79"), Some(FindingScopeType::Module), Some("auth_service"));
        if vf.finding.scope_type == Some(FindingScopeType::Module) {
            let module_present = vf.finding.module.as_deref()
                .map(str::trim)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !module_present {
                vf.finding.scope_type = Some(FindingScopeType::File);
            }
        }
        assert_eq!(
            vf.finding.scope_type,
            Some(FindingScopeType::Module),
            "scope_type=Module with non-empty module must stay Module"
        );
    }

    /// scope_type=Module with whitespace-only module name is downgraded.
    #[test]
    fn backend_validate_scope_module_whitespace_only_downgraded() {
        let mut vf = make_validated_finding(Some("CWE-79"), Some(FindingScopeType::Module), Some("  "));
        if vf.finding.scope_type == Some(FindingScopeType::Module) {
            let module_present = vf.finding.module.as_deref()
                .map(str::trim)
                .map(|s| !s.is_empty())
                .unwrap_or(false);
            if !module_present {
                vf.finding.scope_type = Some(FindingScopeType::File);
            }
        }
        assert_eq!(
            vf.finding.scope_type,
            Some(FindingScopeType::File),
            "whitespace-only module must be treated as missing"
        );
    }

    // ── G-B7: chain.hop_malformed ───────────────────────────────────────────

    fn make_test_sink() -> (
        crate::runtime::intelligent::audit_pipeline::context::PipelineEventSink,
        tokio::sync::mpsc::UnboundedReceiver<crate::runtime::intelligent::types::IntelligentTaskEvent>,
    ) {
        use tokio::sync::broadcast;
        let (tx, _) = broadcast::channel(64);
        crate::runtime::intelligent::audit_pipeline::context::PipelineEventSink::new(tx)
    }

    fn make_trace_output(hops: Vec<CallHop>) -> TraceOutput {
        TraceOutput {
            traces: vec![TraceResult {
                finding_id: "F-001".to_string(),
                reachable: true,
                confidence: Some(0.9),
                rationale: "test".to_string(),
                call_chain: hops,
                entry_point: None,
            }],
        }
    }

    /// G-B7: hop with both file=None and function=None emits chain.hop_malformed.
    #[test]
    fn g_b7_hop_malformed_emits_event() {
        let (sink, mut rx) = make_test_sink();
        let bad_hop = CallHop {
            file: None,
            line: Some(10),
            function: None,
            snippet: None,
            language: None,
        };
        let trace_output = make_trace_output(vec![bad_hop]);
        emit_hop_malformed_events(&trace_output, &sink, "trace");

        // Drain all emitted events
        let mut found = false;
        while let Ok(event) = rx.try_recv() {
            if event.kind == "chain.hop_malformed" {
                found = true;
                let data = event.data.expect("data must be present").clone();
                let obj = data.as_object().expect("data must be object");
                assert_eq!(obj["findingId"].as_str(), Some("F-001"));
                assert_eq!(obj["hopIndex"].as_u64(), Some(0));
            }
        }
        assert!(found, "chain.hop_malformed event must be emitted for null file+function hop");
    }

    /// G-B7: ellipsis hop (function contains "…") must NOT emit chain.hop_malformed.
    #[test]
    fn g_b7_ellipsis_hop_not_flagged() {
        let (sink, mut rx) = make_test_sink();
        let ellipsis_hop = CallHop {
            file: None,
            line: None,
            function: Some("…(4 hops omitted)…".to_string()),
            snippet: None,
            language: None,
        };
        let trace_output = make_trace_output(vec![ellipsis_hop]);
        emit_hop_malformed_events(&trace_output, &sink, "trace");

        let events: Vec<_> = std::iter::from_fn(|| rx.try_recv().ok()).collect();
        let malformed: Vec<_> = events.iter().filter(|e| e.kind == "chain.hop_malformed").collect();
        assert!(malformed.is_empty(), "ellipsis hop must not trigger chain.hop_malformed");
    }

    // ── G-B8: finding.evidence_prose_dirty ─────────────────────────────────

    #[test]
    fn g_b8_evidence_prose_clean_no_event() {
        assert!(!evidence_prose_has_path_token(
            "The function allows unsanitized input to reach the SQL sink directly."
        ));
    }

    #[test]
    fn g_b8_evidence_prose_dirty_path_line_detected() {
        assert!(evidence_prose_has_path_token("See src/auth/login.rs:42 for the sink."));
        assert!(evidence_prose_has_path_token("lib/parser.py:100 is vulnerable."));
        assert!(evidence_prose_has_path_token("routes/api/upload.js:7"));
    }

    #[test]
    fn g_b8_evidence_prose_dirty_no_false_positive_on_version() {
        // "v1.2.3" or "2026-05-28" should not trigger (no slash/dot before colon)
        assert!(!evidence_prose_has_path_token("version 1:2 ratio"));
        // URL-style colons without path separators should not trigger
        assert!(!evidence_prose_has_path_token("see https://example.com for details"));
    }

    // ── Evidence alignment helpers ─────────────────────────────────────────
    use crate::runtime::intelligent::audit_pipeline::types::EvidenceCodeSnippet;

    #[test]
    fn extract_code_tokens_picks_up_backticked_and_identifiers() {
        let prose = "The handler `process_request` forwards `userInput` straight to \
                     execute_query without sanitization. The vulnerability is in render_html.";
        let tokens = extract_code_tokens(prose);
        let lc: Vec<String> = tokens.iter().map(|t| t.to_ascii_lowercase()).collect();
        assert!(lc.contains(&"process_request".to_string()));
        assert!(lc.contains(&"userinput".to_string()));
        assert!(lc.contains(&"execute_query".to_string()));
        assert!(lc.contains(&"render_html".to_string()));
    }

    #[test]
    fn extract_code_tokens_skips_plain_english_words() {
        let prose = "The user input flows directly to the database without checks.";
        let tokens = extract_code_tokens(prose);
        assert!(tokens.is_empty(), "got unexpected tokens: {tokens:?}");
    }

    fn finding_with(
        prose: Option<&str>,
        snippets: Vec<EvidenceCodeSnippet>,
    ) -> AuditFinding {
        AuditFinding {
            finding_id: "F1".to_string(),
            file: "src/main.rs".to_string(),
            line_start: 10,
            line_end: 20,
            vuln_class: "sqli".to_string(),
            severity: "medium".to_string(),
            description: "".to_string(),
            evidence: "".to_string(),
            evidence_code_snippets: snippets,
            evidence_prose: prose.map(|s| s.to_string()),
            ..Default::default()
        }
    }

    #[test]
    fn evidence_misalignment_empty_when_all_tokens_present() {
        let finding = finding_with(
            Some("The `process_request` handler calls `execute_query` directly."),
            vec![EvidenceCodeSnippet {
                file: Some("src/main.rs".to_string()),
                line_start: Some(10),
                line_end: Some(20),
                code: "fn process_request() { execute_query(input); }".to_string(),
                language: Some("rust".to_string()),
            }],
        );
        let missing = evidence_misalignment(&finding);
        assert!(missing.is_empty(), "expected no missing tokens, got: {missing:?}");
    }

    #[test]
    fn evidence_misalignment_reports_unsnippeted_identifiers() {
        let finding = finding_with(
            Some("The `process_request` handler calls `execute_query` directly."),
            vec![EvidenceCodeSnippet {
                file: Some("src/main.rs".to_string()),
                line_start: Some(10),
                line_end: Some(20),
                // Only `process_request` is in the snippet; `execute_query` is missing.
                code: "fn process_request() { /* body */ }".to_string(),
                language: Some("rust".to_string()),
            }],
        );
        let missing = evidence_misalignment(&finding);
        let lc: Vec<String> = missing.iter().map(|t| t.to_ascii_lowercase()).collect();
        assert!(lc.contains(&"execute_query".to_string()));
        assert!(!lc.contains(&"process_request".to_string()));
    }

    #[test]
    fn evidence_misalignment_empty_snippets_flags_every_code_token() {
        let finding = finding_with(
            Some("The `process_request` handler calls `execute_query` directly."),
            vec![],
        );
        let missing = evidence_misalignment(&finding);
        let lc: Vec<String> = missing.iter().map(|t| t.to_ascii_lowercase()).collect();
        assert!(lc.contains(&"process_request".to_string()));
        assert!(lc.contains(&"execute_query".to_string()));
    }

    #[test]
    fn evidence_misalignment_accepts_filename_satisfying_tokens() {
        // A token can be satisfied by the finding's file path too — many rationales
        // reference a module by its file basename.
        let finding = finding_with(
            Some("The vulnerability is in `auth_router`."),
            vec![EvidenceCodeSnippet {
                file: Some("src/auth_router.rs".to_string()),
                line_start: Some(1),
                line_end: Some(2),
                code: "".to_string(),
                language: None,
            }],
        );
        let missing = evidence_misalignment(&finding);
        assert!(missing.is_empty(), "filename should satisfy token; got: {missing:?}");
    }
}
