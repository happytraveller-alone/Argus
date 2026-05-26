use serde::{Deserialize, Serialize};

use crate::runtime::intelligent::types::IntelligentTaskFinding;

use super::repo::ArchiveEntry;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ReconOutput {
    #[serde(default)]
    pub architecture_summary: String,
    #[serde(default)]
    pub subsystems: Vec<Subsystem>,
    #[serde(default)]
    pub initial_tasks: Vec<HuntTask>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Subsystem {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub purpose: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HuntTask {
    pub task_id: String,
    #[serde(default = "default_source")]
    pub source: String,
    pub attack_class: String,
    pub scope_hint: String,
    #[serde(default)]
    pub target_files: Vec<String>,
    #[serde(default)]
    pub rationale: String,
    #[serde(default = "default_priority")]
    pub priority: u8,
}

impl Default for HuntTask {
    fn default() -> Self {
        Self {
            task_id: String::new(),
            source: default_source(),
            attack_class: String::new(),
            scope_hint: String::new(),
            target_files: vec![],
            rationale: String::new(),
            priority: default_priority(),
        }
    }
}

fn default_source() -> String {
    "recon".to_string()
}

fn default_priority() -> u8 {
    3
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct HuntOutput {
    #[serde(default)]
    pub findings: Vec<AuditFinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct PocResult {
    pub language: String,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub reproduced: bool,
}

/// Accept `pocResult` as either:
///   * a free-form string (current hunt prompt at prompts.rs:58 — LLM returns
///     the Exec stdout verbatim, e.g. `"Heap buffer overflow triggered..."`), or
///   * a structured object matching [`PocResult`] (legacy / future PoC runner).
///
/// Without this adapter the LLM's string form makes serde fail the entire
/// `HuntOutput` deserialize → `hunt task failed; skipping task findings` →
/// the whole audit silently produces zero findings.
fn deserialize_poc_result<'de, D>(deserializer: D) -> Result<Option<PocResult>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value: Option<serde_json::Value> = Option::deserialize(deserializer)?;
    match value {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(serde_json::Value::String(s)) => {
            if s.trim().is_empty() {
                Ok(None)
            } else {
                Ok(Some(PocResult {
                    stdout: s,
                    ..PocResult::default()
                }))
            }
        }
        Some(other) => serde_json::from_value::<PocResult>(other)
            .map(Some)
            .map_err(serde::de::Error::custom),
    }
}

/// Accept a `String` LLM-output field as either:
///   * a JSON string (the schema we asked for),
///   * a number / bool / null (coerce to display form / empty), or
///   * an object / array (round-trip back to a compact JSON string so the
///     content survives instead of failing the whole stage).
///
/// LLMs occasionally emit structured data in fields that the prompt requested
/// as strings — e.g. `evidence: {"snippet": "...", "lineRange": [10, 20]}`
/// or `severity: {"level": "high", "score": 9.8}`. Without this adapter,
/// serde fails the whole `HuntOutput` deserialize with
/// `invalid type: map, expected a string`, taking down the entire hunt task
/// and producing zero findings (see prompts.rs:58 — the hunt prompt explicitly
/// redirects `pocResult` narrative content into `evidence`/`description`).
fn deserialize_string_lenient<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = serde_json::Value::deserialize(deserializer)?;
    Ok(match value {
        serde_json::Value::String(s) => s,
        serde_json::Value::Null => String::new(),
        serde_json::Value::Bool(b) => b.to_string(),
        serde_json::Value::Number(n) => n.to_string(),
        // Compound types: round-trip through JSON. `to_string` on a Value
        // that already deserialized cannot fail.
        other => serde_json::to_string(&other).unwrap_or_default(),
    })
}

/// `Option<String>` counterpart to [`deserialize_string_lenient`]. Maps absent
/// or `null` → `None`; other JSON shapes coerce to `Some(string)`.
fn deserialize_option_string_lenient<'de, D>(
    deserializer: D,
) -> Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value: Option<serde_json::Value> = Option::deserialize(deserializer)?;
    Ok(match value {
        None | Some(serde_json::Value::Null) => None,
        Some(serde_json::Value::String(s)) => Some(s),
        Some(serde_json::Value::Bool(b)) => Some(b.to_string()),
        Some(serde_json::Value::Number(n)) => Some(n.to_string()),
        Some(other) => Some(serde_json::to_string(&other).unwrap_or_default()),
    })
}

/// Dismissal classification category for an `AuditFinding`.
///
/// Phase 0 scope: written deterministically by `path_classifier` when a finding's
/// single target file matches a known test/vendor path component. Phase 1 will
/// extend writers to include `rule_matched` (SoT) and `llm_inferred` (Hunt Pass 2).
///
/// v0.3.b adds `DeadCode` — written deterministically by `code_intel::dead_code`
/// when the finding's `line_start` lives inside an unreachable region
/// (`if False:` block, `#[cfg(test)]` gate, code after an unconditional return,
/// `if (false) {` branch, etc.). Always paired with `confidence_source ==
/// RuleMatched` and the pattern name (e.g. `"if_false_branch"`) in
/// `sanitizer_symbols[0]`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DismissalCategory {
    Real,
    Sanitized,
    Test,
    Vendor,
    DeadCode,
}

/// Provenance for a dismissal verdict — records WHICH evidence channel produced it.
///
/// Phase 0 emits only `PathPattern` (deterministic glob match). Phase 1 will add
/// SoT-driven `RuleMatched` and Hunt-Pass-2 driven `LlmInferred`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConfidenceSource {
    RuleMatched,
    LlmInferred,
    PathPattern,
}

/// Structured dismissal evidence attached to an `AuditFinding`.
///
/// Phase 0 scope — fields limited to what `path_classifier` can populate:
///   - `category`: which dismissal bucket
///   - `confidence_source`: provenance (Phase 0 always `PathPattern`)
///   - `path_pattern`: the matched glob fragment (e.g. `"tests/"`, `"vendor/"`)
///
/// Phase 1 (Hunt 2-pass) additively adds:
///   - `sanitizer_symbols`: canonical SoT symbols observed on the call chain
///     (only populated when `confidence_source == RuleMatched`).
///   - `rationale`: 1-2 sentence explanation from Hunt Pass 2.
///
/// Both fields are `#[serde(default)]`-defaulted so Phase 0 records (and
/// legacy producers) deserialize unchanged.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DismissalEvidence {
    pub category: DismissalCategory,
    pub confidence_source: ConfidenceSource,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path_pattern: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub sanitizer_symbols: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rationale: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AuditFinding {
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
    pub finding_id: String,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
    pub file: String,
    #[serde(default = "default_line")]
    pub line_start: u32,
    #[serde(default = "default_line")]
    pub line_end: u32,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
    pub vuln_class: String,
    #[serde(default = "default_severity", deserialize_with = "deserialize_string_lenient")]
    pub severity: String,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
    pub description: String,
    #[serde(
        default,
        alias = "evidence_snippet",
        deserialize_with = "deserialize_string_lenient"
    )]
    pub evidence: String,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default, deserialize_with = "deserialize_option_string_lenient")]
    pub task_id: Option<String>,
    #[serde(default, deserialize_with = "deserialize_option_string_lenient")]
    pub poc_code: Option<String>,
    #[serde(default, deserialize_with = "deserialize_poc_result")]
    pub poc_result: Option<PocResult>,
    #[serde(default)]
    pub hedged_language: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dismissal_evidence: Option<DismissalEvidence>,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
    pub language: String,
}

impl Default for AuditFinding {
    fn default() -> Self {
        Self {
            finding_id: String::new(),
            file: String::new(),
            line_start: default_line(),
            line_end: default_line(),
            vuln_class: String::new(),
            severity: default_severity(),
            description: String::new(),
            evidence: String::new(),
            confidence: None,
            task_id: None,
            poc_code: None,
            poc_result: None,
            hedged_language: None,
            dismissal_evidence: None,
            language: String::new(),
        }
    }
}

fn default_line() -> u32 {
    1
}

fn default_severity() -> String {
    "medium".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ValidationOutput {
    #[serde(default)]
    pub findings: Vec<ValidatedFinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidatedFinding {
    #[serde(flatten)]
    pub finding: AuditFinding,
    #[serde(default = "default_validation_status")]
    pub validation_status: String,
    #[serde(default)]
    pub validation_rationale: String,
}

fn default_validation_status() -> String {
    "confirmed".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct GapfillOutput {
    #[serde(default)]
    pub new_tasks: Vec<HuntTask>,
    #[serde(default)]
    pub rationale: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct DedupeOutput {
    #[serde(default)]
    pub groups: Vec<DedupeGroup>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct DedupeGroup {
    pub group_id: String,
    pub canonical_finding_id: String,
    #[serde(default)]
    pub finding_ids: Vec<String>,
    #[serde(default)]
    pub root_cause: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct TraceOutput {
    #[serde(default)]
    pub traces: Vec<TraceResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct TraceResult {
    pub finding_id: String,
    #[serde(default)]
    pub reachable: bool,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default)]
    pub rationale: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct FeedbackOutput {
    #[serde(default)]
    pub new_tasks: Vec<HuntTask>,
    #[serde(default)]
    pub patterns: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReportOutput {
    pub summary: String,
    #[serde(default)]
    pub findings: Vec<AuditFinding>,
    #[serde(default)]
    pub recommendations: Vec<String>,
}

impl Default for ReportOutput {
    fn default() -> Self {
        Self {
            summary: "8-agent intelligent audit completed.".to_string(),
            findings: vec![],
            recommendations: vec![],
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct PipelineOutputs {
    pub recon: ReconOutput,
    pub hunt: HuntOutput,
    pub validate: ValidationOutput,
    pub gapfill: GapfillOutput,
    pub dedupe: DedupeOutput,
    pub trace: TraceOutput,
    pub feedback: FeedbackOutput,
    pub report: ReportOutput,
}

impl PipelineOutputs {
    #[must_use]
    pub fn to_task_findings(&self) -> Vec<IntelligentTaskFinding> {
        let trace_by_id = self
            .trace
            .traces
            .iter()
            .map(|trace| (trace.finding_id.as_str(), trace))
            .collect::<std::collections::BTreeMap<_, _>>();
        self.validate
            .findings
            .iter()
            .filter(|finding| finding.validation_status == "confirmed")
            .map(|validated| {
                let finding = &validated.finding;
                let trace = trace_by_id.get(finding.finding_id.as_str());
                IntelligentTaskFinding {
                    id: finding.finding_id.clone(),
                    severity: finding.severity.clone(),
                    summary: finding.description.clone(),
                    evidence: enrich_evidence(finding, trace.copied()),
                    file: Some(finding.file.clone()),
                    line_start: Some(finding.line_start),
                    line_end: Some(finding.line_end),
                    vuln_class: Some(finding.vuln_class.clone()),
                    confidence: finding.confidence,
                    validation_status: Some(validated.validation_status.clone()),
                    reachable: trace.map(|trace| trace.reachable),
                    trace_summary: trace.map(|trace| trace.rationale.clone()),
                    poc_result: finding
                        .poc_result
                        .as_ref()
                        .map(|p| serde_json::to_value(p).unwrap_or_default()),
                }
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// AC0.G — Back-compat: legacy `AuditFinding` JSON (pre Phase 0) MUST
    /// deserialize cleanly with `dismissal_evidence == None`. No panic, no error.
    #[test]
    fn test_dismissal_evidence_backcompat_deserialize() {
        // Hardcoded legacy JSON (camelCase, missing dismissalEvidence field).
        let legacy_json = r#"{
            "findingId": "legacy-001",
            "file": "src/legacy.rs",
            "lineStart": 10,
            "lineEnd": 12,
            "vulnClass": "sql_injection",
            "severity": "high",
            "description": "Legacy finding from pre-Phase-0 pipeline.",
            "evidence": "format!(\"SELECT * FROM users WHERE id = {}\", input)"
        }"#;

        let finding: AuditFinding =
            serde_json::from_str(legacy_json).expect("legacy AuditFinding JSON must deserialize");
        assert_eq!(finding.finding_id, "legacy-001");
        assert!(
            finding.dismissal_evidence.is_none(),
            "missing dismissal_evidence field must deserialize to None"
        );
    }

    /// Round-trip: a finding with `dismissal_evidence: None` must NOT emit the
    /// field on serialize (skip_serializing_if), keeping wire payloads stable.
    #[test]
    fn test_dismissal_evidence_skip_serializing_when_none() {
        let finding = AuditFinding {
            finding_id: "no-evidence".to_string(),
            file: "src/main.rs".to_string(),
            vuln_class: "xss".to_string(),
            severity: "low".to_string(),
            description: "stub".to_string(),
            evidence: "stub".to_string(),
            ..Default::default()
        };
        let serialized = serde_json::to_string(&finding).unwrap();
        assert!(
            !serialized.contains("dismissalEvidence"),
            "dismissal_evidence: None must be omitted, got: {serialized}"
        );
    }

    /// AC1 — US-002: `HuntOutput` with a finding missing `language`, `severity`,
    /// `confidence`, `lineEnd`, and `evidence` MUST deserialize without error,
    /// and after `normalize_finding` the backfilled values must be sensible.
    #[test]
    fn hunt_output_missing_optional_fields_deserializes_and_normalizes() {
        use crate::runtime::intelligent::audit_pipeline::stages::hunt::normalize_finding_for_test;

        let raw = r#"{
            "findings": [{
                "findingId": "ac1-001",
                "file": "src/plist.c",
                "lineStart": 42,
                "vulnClass": "buffer_overflow",
                "description": "Unchecked memcpy length"
            }]
        }"#;

        let mut output: super::HuntOutput =
            serde_json::from_str(raw).expect("HuntOutput with minimal fields must deserialize");

        assert_eq!(output.findings.len(), 1);
        let f = &output.findings[0];
        // Serde defaults applied pre-normalize.
        assert_eq!(f.finding_id, "ac1-001");
        assert_eq!(f.severity, "medium", "severity must default to 'medium'");
        // lineEnd absent → serde default_line() = 1; normalize will fix to lineStart.
        assert_eq!(f.line_end, 1, "lineEnd absent → serde default 1");
        assert!(f.confidence.is_none(), "confidence absent = None");
        assert_eq!(f.evidence, "", "evidence absent = empty string");

        // After normalize_finding the backfill runs.
        normalize_finding_for_test(&mut output.findings[0]);
        let f = &output.findings[0];
        assert_eq!(f.severity, "medium");
        assert_eq!(f.line_end, 42, "lineEnd backfilled to lineStart=42");
        assert_eq!(f.confidence, Some(0.5), "confidence backfilled to 0.5");

        // AC1.2 — language backfill from file extension.
        let raw_c = r#"{
            "findings": [{
                "findingId": "ac1-002",
                "file": "src/parse_string_node.c",
                "lineStart": 10,
                "vulnClass": "buffer_overflow",
                "description": "Unchecked memcpy"
            }]
        }"#;
        let mut output_c: super::HuntOutput =
            serde_json::from_str(raw_c).expect("C finding must deserialize");
        assert_eq!(output_c.findings[0].language, "", "language absent → empty before normalize");
        normalize_finding_for_test(&mut output_c.findings[0]);
        assert_eq!(
            output_c.findings[0].language, "c",
            "language backfilled to 'c' from .c extension"
        );
    }

    /// Regression: when the hunt LLM returns `pocResult` as a free-form string
    /// (matching the old prompt schema and what we observed in production:
    /// `"Heap buffer overflow triggered when…"`), `HuntOutput` MUST still
    /// deserialize. Pre-fix this raised `invalid type: string ..., expected
    /// struct PocResult` and the entire hunt task was dropped via
    /// `hunt task failed; skipping task findings`, producing 0 findings.
    #[test]
    fn audit_finding_accepts_poc_result_as_string() {
        let raw = r#"{
            "findings": [{
                "findingId": "regression-001",
                "file": "src/vm.c",
                "lineStart": 10,
                "vulnClass": "out_of_bounds_read",
                "description": "VM opcode dereferences arbitrary address",
                "pocResult": "VULNERABILITY CONFIRMED - arbitrary read achievable."
            }]
        }"#;
        let output: HuntOutput =
            serde_json::from_str(raw).expect("string pocResult must deserialize");
        let poc = output.findings[0]
            .poc_result
            .as_ref()
            .expect("string pocResult must produce Some(PocResult)");
        assert_eq!(poc.stdout, "VULNERABILITY CONFIRMED - arbitrary read achievable.");
        assert_eq!(poc.language, "", "string-form PocResult leaves language empty");
        assert!(!poc.reproduced, "string-form PocResult does not assert reproduction");
    }

    /// Regression: when the LLM returns `pocResult` as a *partial* object that
    /// omits `language` (or any other required field), `HuntOutput` MUST still
    /// deserialize. Pre-fix this raised `missing field 'language'` and dropped
    /// the entire hunt task.
    #[test]
    fn audit_finding_accepts_poc_result_object_missing_fields() {
        let raw = r#"{
            "findings": [{
                "findingId": "regression-002",
                "file": "src/heap.c",
                "lineStart": 99,
                "vulnClass": "heap_overflow",
                "description": "Pool overflow",
                "pocResult": {"stdout": "ok", "reproduced": true}
            }]
        }"#;
        let output: HuntOutput =
            serde_json::from_str(raw).expect("partial pocResult object must deserialize");
        let poc = output.findings[0]
            .poc_result
            .as_ref()
            .expect("partial object must produce Some(PocResult)");
        assert!(poc.reproduced);
        assert_eq!(poc.stdout, "ok");
        assert_eq!(poc.language, "", "missing language must default to empty");
        assert_eq!(poc.exit_code, 0, "missing exit_code must default to 0");
    }

    /// Round-trip with Some(DismissalEvidence): field present + snake_case enum tags.
    #[test]
    fn test_dismissal_evidence_roundtrip_some() {
        let finding = AuditFinding {
            finding_id: "test-finding".to_string(),
            file: "tests/integration.rs".to_string(),
            vuln_class: "sql_injection".to_string(),
            severity: "high".to_string(),
            description: "stub".to_string(),
            evidence: "stub".to_string(),
            dismissal_evidence: Some(DismissalEvidence {
                category: DismissalCategory::Test,
                confidence_source: ConfidenceSource::PathPattern,
                path_pattern: Some("tests/".to_string()),
                sanitizer_symbols: Vec::new(),
                rationale: None,
            }),
            ..Default::default()
        };
        let serialized = serde_json::to_string(&finding).unwrap();
        assert!(serialized.contains("\"category\":\"test\""));
        assert!(serialized.contains("\"confidenceSource\":\"path_pattern\""));
        assert!(serialized.contains("\"pathPattern\":\"tests/\""));

        let round_tripped: AuditFinding = serde_json::from_str(&serialized).unwrap();
        assert_eq!(round_tripped.dismissal_evidence, finding.dismissal_evidence);
    }

    /// Regression: when the hunt LLM emits an object in fields that the
    /// schema declares as `String` (most commonly `evidence` or `description`
    /// because prompts.rs:58 redirects `pocResult` narrative content there),
    /// `HuntOutput` MUST still deserialize. Pre-fix this raised
    /// `invalid type: map, expected a string` and the entire hunt task was
    /// dropped via `hunt task failed; skipping task findings`, producing 0
    /// findings (audit_pipeline_failed at 2026-05-26T09:42:26Z).
    #[test]
    fn audit_finding_accepts_object_in_string_fields() {
        let raw = r#"{
            "findings": [{
                "findingId": "regression-003",
                "file": "src/parser.c",
                "lineStart": 42,
                "vulnClass": {"type": "buffer_overflow", "category": "memory"},
                "severity": {"level": "high", "score": 9.8},
                "description": {"summary": "OOB write", "details": "memcpy with attacker-controlled len"},
                "evidence": {"snippet": "memcpy(dst, src, len);", "lineRange": [40, 44]}
            }]
        }"#;
        let output: HuntOutput =
            serde_json::from_str(raw).expect("object-shaped string fields must deserialize");
        let f = &output.findings[0];
        assert_eq!(f.finding_id, "regression-003");
        // Compound shapes round-trip to compact JSON strings so content survives.
        assert!(
            f.vuln_class.contains("buffer_overflow"),
            "vuln_class object preserved: {}",
            f.vuln_class
        );
        assert!(
            f.severity.contains("high"),
            "severity object preserved: {}",
            f.severity
        );
        assert!(
            f.description.contains("OOB write"),
            "description object preserved: {}",
            f.description
        );
        assert!(
            f.evidence.contains("memcpy"),
            "evidence object preserved: {}",
            f.evidence
        );
    }

    /// Regression: scalar coercion — numbers, bools, and null in string fields
    /// must not break deserialization either.
    #[test]
    fn audit_finding_accepts_scalar_coercion_in_string_fields() {
        let raw = r#"{
            "findings": [{
                "findingId": 42,
                "file": "src/x.c",
                "vulnClass": true,
                "severity": null,
                "description": 3.14,
                "evidence": "ok",
                "taskId": {"nested": "id"},
                "pocCode": 7
            }]
        }"#;
        let output: HuntOutput =
            serde_json::from_str(raw).expect("scalar coercion must deserialize");
        let f = &output.findings[0];
        assert_eq!(f.finding_id, "42", "number coerces to string");
        assert_eq!(f.vuln_class, "true", "bool coerces to string");
        assert_eq!(f.severity, "", "null coerces to empty string");
        assert_eq!(f.description, "3.14", "float coerces to string");
        assert_eq!(f.evidence, "ok");
        assert_eq!(
            f.task_id.as_deref(),
            Some(r#"{"nested":"id"}"#),
            "Option<String> object preserved as JSON"
        );
        assert_eq!(
            f.poc_code.as_deref(),
            Some("7"),
            "Option<String> number coerces"
        );
    }
}

fn enrich_evidence(finding: &AuditFinding, trace: Option<&TraceResult>) -> String {
    let mut evidence = format!(
        "{}:{}-{} [{}] {}",
        finding.file, finding.line_start, finding.line_end, finding.vuln_class, finding.evidence
    );
    if let Some(trace) = trace {
        evidence.push_str(&format!(
            "\nReachable: {}. {}",
            trace.reachable, trace.rationale
        ));
    }
    evidence
}

#[must_use]
pub fn fallback_recon(entries: &[ArchiveEntry]) -> ReconOutput {
    let target_files: Vec<String> = entries
        .iter()
        .take(20)
        .map(|entry| entry.path.clone())
        .collect();
    ReconOutput {
        architecture_summary: format!(
            "Archive contains {} files. Recon fallback generated focused hunt tasks from archive metadata.",
            entries.len()
        ),
        subsystems: vec![Subsystem {
            name: "project_archive".to_string(),
            path: "/".to_string(),
            purpose: "Uploaded project archive".to_string(),
        }],
        initial_tasks: vec![
            HuntTask {
                task_id: "hunt-input-validation".to_string(),
                source: "recon".to_string(),
                attack_class: "input_validation".to_string(),
                scope_hint: "Search for untrusted input reaching sensitive operations.".to_string(),
                target_files: target_files.clone(),
                rationale: "Baseline agent task generated because recon returned no tasks.".to_string(),
                priority: 1,
            },
            HuntTask {
                task_id: "hunt-authz".to_string(),
                source: "recon".to_string(),
                attack_class: "authorization".to_string(),
                scope_hint: "Search for missing authorization checks across handlers and services.".to_string(),
                target_files,
                rationale: "Baseline agent task generated because recon returned no tasks.".to_string(),
                priority: 2,
            },
        ],
    }
}
