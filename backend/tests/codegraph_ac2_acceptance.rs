//! AC2 acceptance test — Plan Phase 2 / v0.2 + v0.3.b production thresholds.
//!
//! Drives the codegraph fixtures through the deterministic dismissal
//! channels (path-pattern from `path_classifier`, rule-matched from
//! `sanitizer_sot`, and v0.3.b dead-code from `code_intel::dead_code`) and
//! asserts the production gate:
//!
//! ## Fixture matrix (v0.3.b: N = 7 total = 3 real + 4 negative)
//!
//! Real-label (cross-file unsanitized chains — must surface as real):
//!   1. `python_sqli/`            — Flask cross-file SQLi
//!   2. `java_path_traversal/`    — Spring cross-file path traversal
//!   3. `ts_proto_pollution/`     — Express cross-file prototype pollution
//!
//! Negative (must be deterministically dismissed pre-Pass-2):
//!   4. `python_sqli_sanitized_negative/`        — sanitized via SoT rule_matched
//!   5. `java_path_traversal_test_negative/`     — test path_pattern
//!   6. `python_sqli_vendor_negative/`           — vendor path_pattern
//!   7. `python_sqli_dead_code_negative/`        — dead-code rule_matched (v0.3.b)
//!
//! ## v0.2 thresholds (`AC2.C` — production gate)
//!
//! - **Real recall ≥ 90%** (was 80% in v0.1). With N=3 real fixtures the
//!   smallest discrete count satisfying ≥ 90% is `ceil(0.9 × 3) = 3`, so the
//!   effective gate is **3/3 real fixtures surface as real (100%)**.
//! - **Sanitized precision ≥ 80%** (was 70% in v0.1). With N=1 sanitized
//!   fixture, the gate is unchanged at 1/1 (100%).
//! - **Test path classification = 100%**. With N=1 test fixture: 1/1.
//! - **Vendor path classification = 100%** (new in Phase 2). With N=1 vendor
//!   fixture: 1/1.
//! - **FPR ≤ 20%** (was 30% in v0.1). With N=3 negative fixtures the largest
//!   discrete count satisfying ≤ 20% is `floor(0.2 × 3) = 0`, so the effective
//!   gate is **0/3 negatives may flip to real**.
//! - **Schema completeness 100%** — every negative fixture must produce
//!   `dismissal_evidence.is_some()`.
//!
//! The "% threshold on tiny N" reduces to discrete counts: at N=3 the only
//! arithmetic-feasible gates are 100% or 67%, and we pick the stricter one
//! that still allows the v0.2 percentages on the larger v0.3 corpus.
//!
//! ## Test methodology
//!
//! The test deliberately bypasses LLM Pass 1 / Pass 2 (which require live
//! model access) and stages the deterministic pre-Pass-2 verdict the
//! runtime would compute: path_classifier verdict + SoT scan over an
//! expected_call_chain stub. This is the same evidence the prompt-injection-
//! safe rule_matched path uses.

use std::path::{Path, PathBuf};

use backend_rust::runtime::intelligent::audit_pipeline::types::{
    ConfidenceSource, DismissalCategory, DismissalEvidence,
};
use backend_rust::runtime::intelligent::code_intel::dead_code::detect_dead_code;
use backend_rust::runtime::intelligent::code_intel::lookup_sanitizer;
use backend_rust::runtime::intelligent::code_intel::path_classifier::{
    classify_path, PathCategory,
};
use serde_json::Value;

fn fixtures_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("codegraph_fixtures")
}

#[derive(Debug)]
struct FixtureCase {
    dir: PathBuf,
    finding: Value,
}

fn load_fixture(name: &str) -> FixtureCase {
    let dir = fixtures_root().join(name);
    let finding_path = dir.join("finding.json");
    let raw = std::fs::read_to_string(&finding_path)
        .unwrap_or_else(|e| panic!("read {}: {e}", finding_path.display()));
    let finding: Value = serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("parse {}: {e}", finding_path.display()));
    FixtureCase { dir, finding }
}

/// Detect language from the finding's `file` extension. Mirrors hunt.rs's
/// `map_extension_to_language` so the test exercises the same SoT codepath.
fn language_for(file: &str) -> Option<&'static str> {
    let lower = file.to_ascii_lowercase();
    let dot = lower.rfind('.')?;
    let ext = lower[dot + 1..].to_string();
    Some(match ext.as_str() {
        "py" => "python",
        "java" => "java",
        "ts" | "tsx" => "typescript",
        _ => return None,
    })
}

/// Apply the deterministic dismissal channels (path_classifier first, then SoT
/// over `expected_call_chain`). Returns the same `DismissalEvidence` shape the
/// runtime would write before LLM Pass 2.
fn deterministic_dismissal_for(case: &FixtureCase) -> Option<DismissalEvidence> {
    let file = case
        .finding
        .get("file")
        .and_then(Value::as_str)
        .expect("finding.file");

    // 1. path_classifier — applies to the finding's reported file path. The
    //    runtime feeds the upstream HuntTask's target_files, but for fixtures
    //    the seeded finding's file IS the target — they are 1:1.
    let (cat, pat) = classify_path(Path::new(file));
    let path_verdict = match cat {
        PathCategory::Test => Some((DismissalCategory::Test, pat)),
        PathCategory::Vendor => Some((DismissalCategory::Vendor, pat)),
        PathCategory::RealCode => None,
    };

    // 2. SoT — scan the fixture's expected_call_chain (a stand-in for what
    //    Pass 1 retrieval would surface) for sanitizer hits.
    let lang = language_for(file);
    let mut sot_hit: Option<String> = None;
    if let Some(lang) = lang {
        if let Some(chain) = case
            .finding
            .get("expected_call_chain")
            .and_then(Value::as_array)
        {
            for node in chain {
                if let Some(sym) = node.as_str() {
                    if let Some(matched) = lookup_sanitizer(lang, sym) {
                        sot_hit = Some(matched.to_string());
                        break;
                    }
                }
            }
        }
        // The python_sqli_sanitized_negative fixture's call chain lists the
        // call-site function names, but the actual sanitizer symbol
        // (psycopg2.sql.SQL) appears in the evidence text. We additionally
        // scan the `evidence` field, since that's what the LLM Pass 1
        // get_context tool would surface inside the function body.
        if sot_hit.is_none() {
            if let Some(evidence) = case.finding.get("evidence").and_then(Value::as_str) {
                // Tokenise on common code separators.
                for token in evidence.split(|c: char| {
                    matches!(c, ' ' | '(' | ')' | ',' | '"' | '\'' | '`' | '[' | ']' | '\n')
                }) {
                    if token.is_empty() {
                        continue;
                    }
                    // SoT entries can be dotted paths (psycopg2.sql.SQL) or
                    // bare names — try both.
                    if let Some(matched) = lookup_sanitizer(lang, token) {
                        sot_hit = Some(matched.to_string());
                        break;
                    }
                }
            }
        }
    }

    // Rule_matched wins over PathPattern (per AC1.C order — SoT is the most
    // specific channel; if both fire, prefer the canonical sanitizer match).
    if let Some(sym) = sot_hit {
        return Some(DismissalEvidence {
            category: DismissalCategory::Sanitized,
            confidence_source: ConfidenceSource::RuleMatched,
            path_pattern: None,
            sanitizer_symbols: vec![sym],
            rationale: None,
        });
    }
    if let Some((category, pat)) = path_verdict {
        return Some(DismissalEvidence {
            category,
            confidence_source: ConfidenceSource::PathPattern,
            path_pattern: pat,
            sanitizer_symbols: Vec::new(),
            rationale: None,
        });
    }

    // v0.3.b: dead-code channel. Same ordering as the runtime: runs ONLY when
    // neither SoT nor path-pattern fired. Source is read from the fixture
    // directory (fixtures are unpacked on disk for the test runner).
    let line_start = case
        .finding
        .get("line_start")
        .and_then(Value::as_u64)
        .unwrap_or(1) as u32;
    if let (Some(lang), Ok(source)) = (lang, std::fs::read_to_string(case.dir.join(file))) {
        if let Some(pattern) = detect_dead_code(&source, line_start, lang) {
            return Some(DismissalEvidence {
                category: DismissalCategory::DeadCode,
                confidence_source: ConfidenceSource::RuleMatched,
                path_pattern: None,
                sanitizer_symbols: vec![pattern.to_string()],
                rationale: None,
            });
        }
    }
    None
}

fn expected_classification(case: &FixtureCase) -> &str {
    case.finding
        .get("expected_classification")
        .and_then(Value::as_str)
        .expect("fixture must declare expected_classification")
}

fn expected_confidence_source(case: &FixtureCase) -> Option<&str> {
    case.finding
        .get("expected_confidence_source")
        .and_then(Value::as_str)
}

#[test]
fn ac2_acceptance_real_recall_sanitized_test_classification() {
    // ── Load all 7 fixtures (v0.3.b matrix: 3 real + 4 negative) ───────────
    let real_python = load_fixture("python_sqli");
    let real_java = load_fixture("java_path_traversal");
    let real_ts = load_fixture("ts_proto_pollution");
    let san = load_fixture("python_sqli_sanitized_negative");
    let test = load_fixture("java_path_traversal_test_negative");
    let vendor = load_fixture("python_sqli_vendor_negative");
    let dead = load_fixture("python_sqli_dead_code_negative");

    let fixtures = [&real_python, &real_java, &real_ts, &san, &test, &vendor, &dead];
    let mut real_recall_count = 0usize;
    let mut sanitized_correct_count = 0usize;
    let mut test_correct_count = 0usize;
    let mut vendor_correct_count = 0usize;
    let mut dead_correct_count = 0usize;
    let mut fpr_count = 0usize;

    for case in fixtures.iter() {
        let verdict = deterministic_dismissal_for(case);
        let expected = expected_classification(case);
        let dir_name = case
            .dir
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("<?>");

        eprintln!(
            "fixture={dir_name} expected={expected} verdict={:?}",
            verdict.as_ref().map(|v| (v.category, v.confidence_source))
        );

        match expected {
            "real" => {
                // A real fixture must have NO deterministic dismissal verdict —
                // it survives to Pass 2 as real. Equivalent to verdict.is_none()
                // OR (when present) category == Real (no Real producer yet, but
                // future-proof the assertion).
                let surfaces_as_real = verdict.is_none()
                    || verdict
                        .as_ref()
                        .map(|v| v.category == DismissalCategory::Real)
                        .unwrap_or(false);
                assert!(
                    surfaces_as_real,
                    "real fixture {dir_name} got dismissed: {verdict:?}"
                );
                real_recall_count += 1;
            }
            "sanitized" => {
                let v = verdict
                    .as_ref()
                    .expect("sanitized fixture must produce dismissal_evidence");
                assert_eq!(v.category, DismissalCategory::Sanitized);
                assert_eq!(v.confidence_source, ConfidenceSource::RuleMatched);
                let want_syms = case
                    .finding
                    .get("expected_sanitizer_symbols")
                    .and_then(Value::as_array)
                    .expect("sanitized fixture must declare expected_sanitizer_symbols");
                for want in want_syms {
                    let want = want.as_str().unwrap();
                    assert!(
                        v.sanitizer_symbols.iter().any(|s| s == want),
                        "expected sanitizer_symbols to contain {want:?} got {:?}",
                        v.sanitizer_symbols
                    );
                }
                sanitized_correct_count += 1;
            }
            "test" | "vendor" => {
                let v = verdict
                    .as_ref()
                    .expect("test/vendor fixture must produce dismissal_evidence");
                assert_eq!(v.confidence_source, ConfidenceSource::PathPattern);
                let want_cat = if expected == "test" {
                    DismissalCategory::Test
                } else {
                    DismissalCategory::Vendor
                };
                assert_eq!(v.category, want_cat);
                if let Some(want_source) = expected_confidence_source(case) {
                    assert_eq!(want_source, "path_pattern");
                }
                if expected == "test" {
                    test_correct_count += 1;
                } else {
                    vendor_correct_count += 1;
                }
            }
            "dead_code" => {
                let v = verdict
                    .as_ref()
                    .expect("dead_code fixture must produce dismissal_evidence");
                assert_eq!(v.category, DismissalCategory::DeadCode);
                assert_eq!(v.confidence_source, ConfidenceSource::RuleMatched);
                let want_syms = case
                    .finding
                    .get("expected_sanitizer_symbols")
                    .and_then(Value::as_array)
                    .expect("dead_code fixture must declare expected_sanitizer_symbols");
                for want in want_syms {
                    let want = want.as_str().unwrap();
                    assert!(
                        v.sanitizer_symbols.iter().any(|s| s == want),
                        "expected sanitizer_symbols to contain {want:?} got {:?}",
                        v.sanitizer_symbols
                    );
                }
                dead_correct_count += 1;
            }
            other => panic!("unexpected expected_classification: {other}"),
        }

        // FPR: count cases where a *negative* fixture was misclassified as real.
        if expected != "real" {
            let is_real_label = verdict.is_none()
                || verdict
                    .as_ref()
                    .map(|v| v.category == DismissalCategory::Real)
                    .unwrap_or(false);
            if is_real_label {
                fpr_count += 1;
            }
            // Schema completeness for negatives: dismissal_evidence MUST be set.
            assert!(
                verdict.is_some(),
                "negative fixture {dir_name} must surface dismissal_evidence"
            );
        }
    }

    // AC2.C / v0.3.b production-gate assertions (per fixture matrix doc above).
    // N=3 real: ceil(0.9 × 3) = 3 → all 3 must recall.
    assert_eq!(
        real_recall_count, 3,
        "real recall ≥90% on N=3 = 3/3; got {real_recall_count}"
    );
    // N=1 sanitized: 1/1.
    assert_eq!(
        sanitized_correct_count, 1,
        "sanitized precision must be 1/1"
    );
    // N=1 test: 1/1.
    assert_eq!(test_correct_count, 1, "test precision must be 1/1");
    // N=1 vendor: 1/1.
    assert_eq!(vendor_correct_count, 1, "vendor precision must be 1/1");
    // N=1 dead_code: 1/1 (v0.3.b new).
    assert_eq!(
        dead_correct_count, 1,
        "v0.3.b dead_code precision must be 1/1"
    );
    // N=4 negative: floor(0.2 × 4) = 0 → no flip allowed (FPR still 0).
    assert_eq!(
        fpr_count, 0,
        "FPR ≤20% on N=4 = 0/4 flips; got {fpr_count}"
    );
}

/// AC1.G schema completeness: each negative fixture's finding.json declares
/// the new Phase 1 fields and they parse cleanly via our types.
#[test]
fn ac2_acceptance_fixture_schemas_parse_cleanly() {
    for name in [
        "python_sqli",
        "java_path_traversal",
        "ts_proto_pollution",
        "python_sqli_sanitized_negative",
        "java_path_traversal_test_negative",
        "python_sqli_vendor_negative",
        "python_sqli_dead_code_negative",
    ] {
        let case = load_fixture(name);
        let classification = expected_classification(&case);
        assert!(
            matches!(
                classification,
                "real" | "sanitized" | "test" | "vendor" | "dead_code"
            ),
            "fixture {name}: invalid expected_classification {classification}"
        );
        let source = expected_confidence_source(&case);
        if classification != "real" {
            assert!(
                matches!(source, Some("rule_matched" | "path_pattern" | "llm_inferred")),
                "negative fixture {name}: missing or invalid expected_confidence_source"
            );
        }
    }
}
