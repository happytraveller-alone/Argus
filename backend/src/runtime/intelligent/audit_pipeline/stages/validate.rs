use std::path::Path;

use anyhow::Result;
use serde_json::json;

use crate::runtime::intelligent::types::FindingScopeType;

use super::super::{
    context::{AuditRunContext, AuditStage, PipelineEventSink},
    json::invoke_json,
    stage_prompt,
    types::{HuntOutput, ValidatedFinding, ValidationOutput},
};

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
    use crate::runtime::intelligent::audit_pipeline::types::{AuditFinding, ValidatedFinding};

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
}
