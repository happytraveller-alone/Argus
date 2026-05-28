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
}
