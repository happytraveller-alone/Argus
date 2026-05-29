use std::collections::HashSet;

use serde::{Deserialize, Serialize};

use crate::runtime::intelligent::types::{FindingScopeType, IntelligentTaskFinding};

use super::repo::ArchiveEntry;

/// Rewrite any duplicate or empty `id` values in `findings` so each entry has a
/// unique, non-empty identifier. The LLM may emit colliding `findingId` strings
/// across parallel hunt tasks (`HUNT-001`, `f1`, …); without this normalization
/// the frontend verdict handler — which uses `findIndex` on `id` — would
/// silently mutate the first matching row when the user clicks a later one.
///
/// Renames are conservative: the first occurrence of each original ID keeps
/// its identity, and rewrite candidates skip over any other row's original ID
/// so we never steal a real finding's identifier.
pub fn ensure_unique_finding_ids(findings: &mut [IntelligentTaskFinding]) {
    // Pre-pass: record which non-empty IDs appear in the input. Used so the
    // suffixing loop below never picks a candidate that shadows another row's
    // original identifier.
    let mut original_ids: HashSet<String> = HashSet::new();
    for finding in findings.iter() {
        let trimmed = finding.id.trim();
        if !trimmed.is_empty() {
            original_ids.insert(trimmed.to_string());
        }
    }

    let mut taken: HashSet<String> = HashSet::new();
    for (idx, finding) in findings.iter_mut().enumerate() {
        let trimmed = finding.id.trim();
        let base: String = if trimmed.is_empty() {
            format!("finding-{}", idx + 1)
        } else {
            trimmed.to_string()
        };
        if taken.insert(base.clone()) {
            finding.id = base;
            continue;
        }
        let mut suffix = 2_usize;
        loop {
            let candidate = format!("{base}-{suffix}");
            if !original_ids.contains(&candidate) && taken.insert(candidate.clone()) {
                finding.id = candidate;
                break;
            }
            suffix += 1;
        }
    }
}

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

/// Why each field carries `alias = "snake_case_name"`:
/// the recon (`prompts.rs:266`) and feedback (`prompts.rs:295`) prompts both
/// declare HuntTask in snake_case (`attack_class`, `scope_hint`, ...), but
/// the struct uses `rename_all = "camelCase"` so the wire format stays
/// camelCase for downstream consumers (event_log, frontend). Without
/// aliases, the LLM-supplied snake_case keys would be silently dropped to
/// defaults — yielding empty `attack_class`/`scope_hint` and orphan
/// follow-up hunts that produce zero findings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HuntTask {
    /// May be empty after deserialization when the LLM omits the field
    /// (observed in feedback-stage `new_tasks` at 2026-05-26). Callers that
    /// need a non-empty id — notably `hunt::run` which uses it to backfill
    /// `finding.task_id` at `stages/hunt.rs:111` — MUST synthesize a value
    /// (see `stages::feedback::run`).
    #[serde(
        default,
        alias = "task_id",
        deserialize_with = "deserialize_string_lenient"
    )]
    pub task_id: String,
    #[serde(
        default = "default_source",
        deserialize_with = "deserialize_string_lenient"
    )]
    pub source: String,
    #[serde(
        default,
        alias = "attack_class",
        deserialize_with = "deserialize_string_lenient"
    )]
    pub attack_class: String,
    #[serde(
        default,
        alias = "scope_hint",
        deserialize_with = "deserialize_string_lenient"
    )]
    pub scope_hint: String,
    #[serde(default, alias = "target_files")]
    pub target_files: Vec<String>,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
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
fn deserialize_option_string_lenient<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
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

/// `Vec<String>` deserializer that accepts the array shape the schema declares
/// AND the object-array shape the LLM occasionally emits when the prompt
/// example showed objects. Object items round-trip to compact JSON strings so
/// content survives instead of failing the whole stage.
///
/// Why this exists: the feedback prompt at `prompts.rs:301` shows `patterns`
/// as `[{"pattern_name":..., "description":..., "grep_hint":...}]`, but
/// `FeedbackOutput.patterns` is declared as `Vec<String>`. The LLM follows
/// the prompt example and returns objects — without this adapter the whole
/// feedback stage dies with `invalid type: map, expected a string`,
/// short-circuiting the feedback → hunt → validate → dedupe → trace loop.
/// Null and scalar items coerce the same way as `deserialize_string_lenient`.
/// A bare string (instead of an array) wraps to a single-element vector;
/// other compound shapes round-trip to a single JSON-encoded item.
fn deserialize_string_list_lenient<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = serde_json::Value::deserialize(deserializer)?;
    Ok(match value {
        serde_json::Value::Null => Vec::new(),
        serde_json::Value::Array(items) => items
            .into_iter()
            .map(|item| match item {
                serde_json::Value::String(s) => s,
                serde_json::Value::Null => String::new(),
                serde_json::Value::Bool(b) => b.to_string(),
                serde_json::Value::Number(n) => n.to_string(),
                other => serde_json::to_string(&other).unwrap_or_default(),
            })
            .filter(|item| !item.is_empty())
            .collect(),
        serde_json::Value::String(s) => {
            if s.trim().is_empty() {
                Vec::new()
            } else {
                vec![s]
            }
        }
        serde_json::Value::Bool(b) => vec![b.to_string()],
        serde_json::Value::Number(n) => vec![n.to_string()],
        other => vec![serde_json::to_string(&other).unwrap_or_default()],
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

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceCodeSnippet {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
    // Aliases preserve compatibility with LLM outputs / persisted records that
    // emit snake_case keys (the original serialization shape before the
    // camelCase rename was applied).
    #[serde(default, skip_serializing_if = "Option::is_none", alias = "line_start")]
    pub line_start: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none", alias = "line_end")]
    pub line_end: Option<u32>,
    #[serde(default)]
    pub code: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct CallHop {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub line: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub snippet: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,
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
    #[serde(default, deserialize_with = "deserialize_option_string_lenient")]
    pub cwe_id: Option<String>,
    #[serde(default)]
    pub scope_type: Option<FindingScopeType>,
    #[serde(default, deserialize_with = "deserialize_option_string_lenient")]
    pub module: Option<String>,
    #[serde(
        default = "default_severity",
        deserialize_with = "deserialize_string_lenient"
    )]
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
    pub evidence_code_snippets: Vec<EvidenceCodeSnippet>,
    #[serde(default, deserialize_with = "deserialize_evidence_prose_compat")]
    pub evidence_prose: Option<String>,
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
            cwe_id: None,
            scope_type: None,
            module: None,
            severity: default_severity(),
            description: String::new(),
            evidence: String::new(),
            evidence_code_snippets: vec![],
            evidence_prose: None,
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
    /// `alias = "new_tasks"`: gapfill prompt (`prompts.rs:264`) uses
    /// snake_case keys. Same hazard as `FeedbackOutput`: missing alias would
    /// silently drop the LLM's task list to empty.
    #[serde(default, alias = "new_tasks")]
    pub new_tasks: Vec<HuntTask>,
    #[serde(default, deserialize_with = "deserialize_string_lenient")]
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
    #[serde(default)]
    pub call_chain: Vec<CallHop>,
    #[serde(default)]
    pub entry_point: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct FeedbackOutput {
    /// `alias = "new_tasks"`: feedback prompt (`prompts.rs:293`) declares the
    /// schema in snake_case; LLM follows the prompt example. Without the
    /// alias, the entire `new_tasks` array is silently dropped to empty,
    /// terminating the feedback → hunt loop at `mod.rs:273`.
    #[serde(default, alias = "new_tasks")]
    pub new_tasks: Vec<HuntTask>,
    #[serde(default, deserialize_with = "deserialize_string_list_lenient")]
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
            summary: "智能审计已完成。".to_string(),
            findings: vec![],
            recommendations: vec![],
        }
    }
}

/// Normalize a finding's `file` path to a project-root-relative form for the
/// frontend's `resolved_file_path` field.
///
/// 1. Strip leading sandbox/workspace prefixes that some upstream stages emit
///    (when findings come back referencing the sandbox container layout).
/// 2. If a project root anchor is supplied AND the trimmed path begins with
///    it, strip that prefix too — yielding a project-root-relative path.
/// 3. Otherwise return the trimmed path unchanged.
pub(crate) fn normalize_resolved_path(raw: &str, project_root: Option<&str>) -> String {
    // Strip sandbox/workspace prefix from raw first.
    let trimmed = raw
        .strip_prefix("/workspace/")
        .or_else(|| raw.strip_prefix("/sandbox/"))
        .unwrap_or(raw);
    // Normalize project_root the same way so the anchor matches even when stored
    // as an absolute sandbox path (e.g. "/workspace/argus-src" → "argus-src").
    if let Some(root) = project_root {
        let normalized_root = root
            .strip_prefix("/workspace/")
            .or_else(|| root.strip_prefix("/sandbox/"))
            .unwrap_or(root);
        let normalized_root = normalized_root.trim_end_matches('/');
        if !normalized_root.is_empty() {
            if let Some(rest) = trimmed.strip_prefix(normalized_root) {
                return rest.trim_start_matches('/').to_string();
            }
        }
    }
    trimmed.to_string()
}

fn deserialize_evidence_prose_compat<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    // Read evidence_prose as Option<String>; serde's #[serde(default)] handles absent
    // value at the struct-field level by skipping this deserializer entirely. When this
    // deserializer IS invoked, the JSON key is present — we accept null or string.
    Option::<String>::deserialize(deserializer)
}

/// Construct an `IntelligentTaskFinding` from the canonical `AuditFinding` plus
/// optional trace/validation overlays. Centralises every field assignment so
/// the 3 conversion sites in `PipelineOutputs` cannot drift out of sync (Phase B).
fn build_intelligent_finding(
    finding: &AuditFinding,
    trace: Option<&TraceResult>,
    validation: Option<&ValidatedFinding>,
    project_root: Option<&str>,
) -> IntelligentTaskFinding {
    IntelligentTaskFinding {
        id: finding.finding_id.clone(),
        severity: finding.severity.clone(),
        summary: finding.description.clone(),
        evidence: enrich_evidence(finding, trace),
        file: Some(finding.file.clone()),
        line_start: Some(finding.line_start),
        line_end: Some(finding.line_end),
        vuln_class: Some(finding.vuln_class.clone()),
        cwe_id: finding.cwe_id.clone(),
        scope_type: finding.scope_type,
        module: finding.module.clone(),
        resolved_file_path: Some(normalize_resolved_path(&finding.file, project_root)),
        confidence: finding.confidence,
        validation_status: validation.map(|v| v.validation_status.clone()),
        reachable: trace.map(|t| t.reachable),
        trace_summary: trace.map(|t| t.rationale.clone()),
        poc_result: finding
            .poc_result
            .as_ref()
            .map(|p| serde_json::to_value(p).unwrap_or_default()),
        user_verdict: None,
        evidence_code_snippets: finding.evidence_code_snippets.clone(),
        evidence_prose: finding.evidence_prose.clone(),
        reachability_chain: trace
            .map(|t| t.call_chain.clone())
            .filter(|v| !v.is_empty()),
        reachability_entry_point: trace.and_then(|t| t.entry_point.clone()),
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
    /// Project root anchor used by `normalize_resolved_path` when building
    /// per-finding `resolved_file_path` values. Set at pipeline entry from the
    /// archive's storage path; `None` falls back to sandbox/workspace prefix
    /// stripping only.
    pub project_root: Option<String>,
}

impl PipelineOutputs {
    /// Update the project root anchor used during finalize-stage normalization.
    pub fn set_project_root(&mut self, root: Option<String>) {
        self.project_root = root;
    }
}

impl PipelineOutputs {
    /// Convert all current hunt findings to `IntelligentTaskFinding` for
    /// incremental flush. Findings the validate stage classified as anything
    /// other than `confirmed` (`rejected` / `needs_more_info`) are discarded so
    /// the frontend never renders unverified risk points; only the pre-validate
    /// hunt snapshot keeps un-classified entries (no validation has run yet).
    #[must_use]
    pub fn to_incremental_findings(&self) -> Vec<IntelligentTaskFinding> {
        let deduped_ids: std::collections::HashSet<&str> = self
            .dedupe
            .groups
            .iter()
            .flat_map(|g| g.finding_ids.iter().map(|s| s.as_str()))
            .collect();
        let trace_by_id = self
            .trace
            .traces
            .iter()
            .map(|trace| (trace.finding_id.as_str(), trace))
            .collect::<std::collections::BTreeMap<_, _>>();

        let mut findings: Vec<IntelligentTaskFinding> = if self.validate.findings.is_empty() {
            // Before validate: convert raw hunt findings directly.
            self.hunt
                .findings
                .iter()
                .filter(|f| deduped_ids.is_empty() || deduped_ids.contains(f.finding_id.as_str()))
                .map(|finding| {
                    build_intelligent_finding(finding, None, None, self.project_root.as_deref())
                })
                .collect()
        } else {
            self.validate
                .findings
                .iter()
                .filter(|vf| {
                    deduped_ids.is_empty() || deduped_ids.contains(vf.finding.finding_id.as_str())
                })
                .filter(|vf| vf.validation_status == "confirmed")
                .filter_map(|validated| {
                    let finding = &validated.finding;
                    let trace = trace_by_id.get(finding.finding_id.as_str());
                    // Once the trace stage has issued a verdict for this
                    // finding, drop it if the reachability analysis says the
                    // sink cannot be triggered. Findings without a trace
                    // verdict yet (early flushes before trace runs) are kept.
                    if let Some(t) = trace {
                        if !t.reachable {
                            return None;
                        }
                    }
                    Some(build_intelligent_finding(
                        finding,
                        trace.copied(),
                        Some(validated),
                        self.project_root.as_deref(),
                    ))
                })
                .collect()
        };
        ensure_unique_finding_ids(&mut findings);
        findings
    }

    #[must_use]
    pub fn to_task_findings(&self) -> Vec<IntelligentTaskFinding> {
        let trace_by_id = self
            .trace
            .traces
            .iter()
            .map(|trace| (trace.finding_id.as_str(), trace))
            .collect::<std::collections::BTreeMap<_, _>>();
        let mut findings: Vec<IntelligentTaskFinding> = self
            .validate
            .findings
            .iter()
            .filter(|finding| finding.validation_status == "confirmed")
            .filter_map(|validated| {
                let finding = &validated.finding;
                let trace = trace_by_id.get(finding.finding_id.as_str());
                // Final task record never carries unreachable risk points: if
                // trace classified the sink as unreachable, the finding is
                // discarded for both the persisted record and the UI.
                if let Some(t) = trace {
                    if !t.reachable {
                        return None;
                    }
                }
                Some(build_intelligent_finding(
                    finding,
                    trace.copied(),
                    Some(validated),
                    self.project_root.as_deref(),
                ))
            })
            .collect();
        ensure_unique_finding_ids(&mut findings);
        findings
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::intelligent::types::IntelligentTaskFinding;

    fn finding_with_id(id: &str) -> IntelligentTaskFinding {
        IntelligentTaskFinding {
            id: id.to_string(),
            severity: "medium".to_string(),
            summary: String::new(),
            evidence: String::new(),
            file: None,
            line_start: None,
            line_end: None,
            vuln_class: None,
            cwe_id: None,
            scope_type: None,
            module: None,
            resolved_file_path: None,
            confidence: None,
            validation_status: None,
            reachable: None,
            trace_summary: None,
            poc_result: None,
            user_verdict: None,
            evidence_code_snippets: vec![],
            evidence_prose: None,
            reachability_chain: None,
            reachability_entry_point: None,
        }
    }

    #[test]
    fn ensure_unique_finding_ids_rewrites_duplicates_and_empties() {
        let mut findings = vec![
            finding_with_id("HUNT-001"),
            finding_with_id("HUNT-001"),
            finding_with_id(""),
            finding_with_id("HUNT-001"),
            finding_with_id("HUNT-001-2"), // pre-existing — rewrites must not shadow it
        ];
        ensure_unique_finding_ids(&mut findings);
        let ids: Vec<&str> = findings.iter().map(|f| f.id.as_str()).collect();
        // First occurrence wins; later duplicates take suffixes that skip past
        // any other row's original identifier. The pre-existing "HUNT-001-2"
        // at idx 4 keeps its identity untouched.
        assert_eq!(ids[0], "HUNT-001");
        assert_eq!(ids[1], "HUNT-001-3");
        assert_eq!(ids[2], "finding-3");
        assert_eq!(ids[3], "HUNT-001-4");
        assert_eq!(ids[4], "HUNT-001-2");
        // All IDs must be unique and non-empty.
        let unique: std::collections::HashSet<&str> = ids.iter().copied().collect();
        assert_eq!(unique.len(), ids.len(), "ids must be unique: {ids:?}");
        for id in &ids {
            assert!(!id.is_empty());
        }
    }

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
        assert_eq!(
            output_c.findings[0].language, "",
            "language absent → empty before normalize"
        );
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
        assert_eq!(
            poc.stdout,
            "VULNERABILITY CONFIRMED - arbitrary read achievable."
        );
        assert_eq!(
            poc.language, "",
            "string-form PocResult leaves language empty"
        );
        assert!(
            !poc.reproduced,
            "string-form PocResult does not assert reproduction"
        );
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

    /// Regression: feedback-stage LLM returned `patterns` as `Vec<Object>`
    /// (the prompt example at prompts.rs:301 shows objects) while the struct
    /// declared `Vec<String>`. Pre-fix: `invalid type: map, expected a string`
    /// → whole audit short-circuited (incident 2026-05-26).
    #[test]
    fn feedback_output_accepts_object_array_in_patterns() {
        let raw = r#"{
            "newTasks": [],
            "patterns": [
                {"pattern_name": "UninitializedSymbolTableEntry",
                 "description": "Symbol table fields used before init.",
                 "grep_hint": "id\\s*= mk|Class\\s*=|Val\\s*="},
                {"pattern_name": "IntOverflowInLiteralParsing",
                 "description": "val = val * 10 + digit without overflow check.",
                 "grep_hint": "val\\s*=\\s*val\\s*\\*"}
            ]
        }"#;
        let output: FeedbackOutput =
            serde_json::from_str(raw).expect("object-array patterns must deserialize");
        assert_eq!(output.patterns.len(), 2);
        assert!(
            output.patterns[0].contains("UninitializedSymbolTableEntry"),
            "object pattern preserved as JSON string: {}",
            output.patterns[0]
        );
        assert!(
            output.patterns[1].contains("IntOverflowInLiteralParsing"),
            "object pattern preserved as JSON string: {}",
            output.patterns[1]
        );
    }

    /// Schema-conformant `Vec<String>` patterns still deserialize unchanged.
    #[test]
    fn feedback_output_accepts_string_array_in_patterns() {
        let raw = r#"{
            "newTasks": [],
            "patterns": ["uninit_symbol", "int_overflow", "untrusted_addr"]
        }"#;
        let output: FeedbackOutput =
            serde_json::from_str(raw).expect("string-array patterns must deserialize");
        assert_eq!(
            output.patterns,
            vec!["uninit_symbol", "int_overflow", "untrusted_addr"]
        );
    }

    /// Regression: HuntTask in feedback `new_tasks` omits `task_id` (prompt
    /// schema at prompts.rs:293 doesn't include it). Pre-fix:
    /// `missing field 'task_id'` → whole feedback stage failed. Post-fix:
    /// deserialize succeeds with empty id; `stages::feedback::run`
    /// synthesizes `hunt-fb-{idx}` after deserialize.
    #[test]
    fn hunt_task_deserializes_without_task_id() {
        let raw = r#"{
            "attack_class": "Uninitialized Symbol Table Fields",
            "scope_hint": "Search all paths that create symbol entries.",
            "target_files": ["c4.c"],
            "rationale": "Inspired by HUNT-002 finding."
        }"#;
        let task: HuntTask =
            serde_json::from_str(raw).expect("HuntTask without task_id must deserialize");
        assert_eq!(task.task_id, "", "task_id absent → empty string");
        assert_eq!(task.attack_class, "Uninitialized Symbol Table Fields");
        assert_eq!(task.source, "recon", "source absent → default 'recon'");
        assert_eq!(task.priority, 3, "priority absent → default 3");
    }

    /// Regression: full feedback-stage payload from the 2026-05-26 incident
    /// — `new_tasks` items missing `task_id`, `patterns` as `Vec<Object>`.
    /// Both bugs at once; this is the exact LLM output that broke the stage.
    #[test]
    fn feedback_output_accepts_incident_payload_2026_05_26() {
        let raw = r#"{
            "new_tasks": [
                {"attack_class": "Uninitialized Symbol Table Fields",
                 "scope_hint": "search symbol entry init paths",
                 "target_files": ["c4.c"],
                 "rationale": "HUNT-002 inspired"},
                {"attack_class": "Unsafe Numeric Literal Parsing",
                 "scope_hint": "tokenizer overflow checks",
                 "target_files": ["c4.c"],
                 "rationale": "HUNT-003 inspired"}
            ],
            "patterns": [
                {"pattern_name": "UninitializedSymbolTableEntry",
                 "description": "fields used before init",
                 "grep_hint": "Class\\s*="},
                {"pattern_name": "IntegerOverflowInLiteralParsing",
                 "description": "signed arithmetic without overflow detect",
                 "grep_hint": "val\\s*=\\s*val\\s*\\*"}
            ]
        }"#;
        let output: FeedbackOutput =
            serde_json::from_str(raw).expect("incident payload must deserialize after fix");
        assert_eq!(output.new_tasks.len(), 2);
        assert_eq!(output.patterns.len(), 2);
        // task_id is empty until feedback::run synthesizes one.
        assert!(output.new_tasks.iter().all(|t| t.task_id.is_empty()));
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
        let reachable_label = if trace.reachable { "可达" } else { "不可达" };
        evidence.push_str(&format!("\n可达性：{reachable_label}。{}", trace.rationale));
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

/// Per-request overrides for `AuditPipelineConfig` tuning knobs.
///
/// Callers (e.g. the API handler) may supply a partial override; any `None`
/// field falls back to the base config value via `into_config`.
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AuditConfigOverride {
    #[serde(default)]
    pub path_blacklist_extra: Option<Vec<String>>,
    #[serde(default)]
    pub reflection_iterations: Option<usize>,
}

/// Per-task config override bounds — protects against authenticated-DoS via
/// oversized vectors or runaway reflection loops (security M1).
pub const PATH_BLACKLIST_EXTRA_MAX_ENTRIES: usize = 64;
pub const PATH_BLACKLIST_EXTRA_MAX_ENTRY_LEN: usize = 128;
pub const REFLECTION_ITERATIONS_MAX: usize = 10;

impl AuditConfigOverride {
    /// Merge override onto a base config, producing a new config.
    pub fn into_config(self, base: &super::AuditPipelineConfig) -> super::AuditPipelineConfig {
        let mut cfg = base.clone();
        if let Some(extra) = self.path_blacklist_extra {
            cfg.path_blacklist_extra = extra;
        }
        if let Some(n) = self.reflection_iterations {
            cfg.reflection_iterations = n;
        }
        cfg
    }

    /// Validate user-supplied bounds. Returns Err with a stable string message
    /// suitable for surfacing as a 400 Bad Request.
    pub fn validate(&self) -> Result<(), &'static str> {
        if let Some(extra) = &self.path_blacklist_extra {
            if extra.len() > PATH_BLACKLIST_EXTRA_MAX_ENTRIES {
                return Err("path_blacklist_extra: too many entries (max 64)");
            }
            for s in extra {
                if s.is_empty() {
                    return Err("path_blacklist_extra: empty entry not allowed");
                }
                if s.len() > PATH_BLACKLIST_EXTRA_MAX_ENTRY_LEN {
                    return Err("path_blacklist_extra: entry too long (max 128 chars)");
                }
                if s.contains('\0') {
                    return Err("path_blacklist_extra: NUL byte not allowed");
                }
                if s.contains('/') || s.contains('\\') {
                    return Err(
                        "path_blacklist_extra: entry must be a single path component (no slashes)",
                    );
                }
                if s == ".." || s.contains("..") {
                    return Err("path_blacklist_extra: '..' not allowed");
                }
            }
        }
        if let Some(n) = self.reflection_iterations {
            if n == 0 {
                return Err("reflection_iterations: must be >= 1");
            }
            if n > REFLECTION_ITERATIONS_MAX {
                return Err("reflection_iterations: max 10");
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod audit_config_override_tests {
    use super::*;

    #[test]
    fn validate_accepts_valid_input() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["custom_dir".to_string(), "extra".to_string()]),
            reflection_iterations: Some(5),
        };
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn validate_accepts_none_fields() {
        let cfg = AuditConfigOverride::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn validate_rejects_oversized_extra_vec() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["x".to_string(); PATH_BLACKLIST_EXTRA_MAX_ENTRIES + 1]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("too many entries"));
    }

    #[test]
    fn validate_rejects_nul_byte() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["bad\0entry".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("NUL byte"));
    }

    #[test]
    fn validate_rejects_slash() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["foo/bar".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("single path component"));
    }

    #[test]
    fn validate_rejects_backslash() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["foo\\bar".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("single path component"));
    }

    #[test]
    fn validate_rejects_dotdot() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["..".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains(".."));
    }

    #[test]
    fn validate_rejects_dotdot_substring() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["foo..bar".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains(".."));
    }

    #[test]
    fn validate_rejects_empty_entry() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["".to_string()]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("empty"));
    }

    #[test]
    fn validate_rejects_oversized_entry() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: Some(vec!["a".repeat(PATH_BLACKLIST_EXTRA_MAX_ENTRY_LEN + 1)]),
            reflection_iterations: None,
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("too long"));
    }

    #[test]
    fn validate_rejects_iterations_above_max() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: None,
            reflection_iterations: Some(REFLECTION_ITERATIONS_MAX + 1),
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("max 10"));
    }

    #[test]
    fn validate_rejects_iterations_zero() {
        let cfg = AuditConfigOverride {
            path_blacklist_extra: None,
            reflection_iterations: Some(0),
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains(">= 1"));
    }
}

// ---------------------------------------------------------------------------
// Phase G tests — backend.normalize.* and backend.audit.*
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests_canonical {
    use super::*;
    use crate::runtime::intelligent::types::FindingScopeType;

    // ── backend.normalize.idempotent (AC10) ─────────────────────────────────
    /// A relative path with no /workspace/ or /sandbox/ prefix is returned unchanged.
    #[test]
    fn backend_normalize_idempotent() {
        let result = normalize_resolved_path("src/auth.rs", None);
        assert_eq!(result, "src/auth.rs", "relative path must not be modified");
    }

    /// Already-normalized path with no project_root anchor is also unchanged.
    #[test]
    fn backend_normalize_no_root_relative_path_unchanged() {
        let result = normalize_resolved_path("backend/src/main.rs", None);
        assert_eq!(result, "backend/src/main.rs");
    }

    // ── backend.normalize.workspace (AC7) ───────────────────────────────────
    /// /workspace/ is stripped first, yielding the project-root-relative part.
    /// The project_root anchor is then matched against the post-strip path.
    /// When project_root is "/workspace/argus-src", the stripped path is
    /// "argus-src/src/db.rs"; the anchor "/workspace/argus-src" does not
    /// match the post-strip path, so the workspace-stripped result is returned.
    ///
    /// To strip down to "src/db.rs", pass the post-workspace project root
    /// (i.e. "argus-src") as the anchor.
    #[test]
    fn backend_normalize_workspace_prefix_stripped() {
        // Case: anchor is the post-workspace path → fully stripped to relative
        let result = normalize_resolved_path(
            "/workspace/argus-src/src/db.rs",
            Some("argus-src"),
        );
        assert_eq!(result, "src/db.rs");
    }

    /// /sandbox/<name>/… is also stripped even without project_root.
    #[test]
    fn backend_normalize_sandbox_prefix_stripped() {
        let result = normalize_resolved_path("/sandbox/mybox/src/foo.rs", None);
        assert_eq!(result, "mybox/src/foo.rs");
    }

    /// workspace prefix stripped; if anchor does not match post-strip path,
    /// returns the workspace-stripped form.
    #[test]
    fn backend_normalize_workspace_then_root_stripped() {
        // Anchor matches post-strip path exactly → further stripped to "src/lib.rs"
        let result = normalize_resolved_path(
            "/workspace/project/src/lib.rs",
            Some("project"),
        );
        assert_eq!(result, "src/lib.rs");
    }

    // ── backend.normalize.noRoot (AC10) ────────────────────────────────────
    /// project_root=None: strip /workspace/ but leave the rest intact.
    #[test]
    fn backend_normalize_no_root_workspace_stripped() {
        let result = normalize_resolved_path("/workspace/some-path/src/util.rs", None);
        assert_eq!(result, "some-path/src/util.rs");
    }

    // ── backend.normalize.absoluteRoot (M1 regression) ──────────────────────
    /// project_root stored as absolute workspace path must be normalized before
    /// prefix-matching the post-strip `trimmed` value.
    ///
    /// Before the fix: step 1 stripped "/workspace/" → "argus-src/src/db.rs";
    /// step 2 checked whether that starts with "/workspace/argus-src" → NO →
    /// returned "argus-src/src/db.rs" (wrong).
    ///
    /// After the fix: project_root is also stripped to "argus-src" before the
    /// prefix check → matches → returns "src/db.rs" (correct).
    #[test]
    fn backend_normalize_absolute_project_root_workspace() {
        let result = normalize_resolved_path(
            "/workspace/argus-src/src/db.rs",
            Some("/workspace/argus-src"),
        );
        assert_eq!(result, "src/db.rs", "absolute workspace project_root must be stripped symmetrically");
    }

    /// Variant: raw is under /sandbox/, project_root is stored under /workspace/.
    /// Both prefixes should be normalised before comparison.
    #[test]
    fn backend_normalize_absolute_project_root_cross_prefix() {
        let result = normalize_resolved_path(
            "/sandbox/foo/src/db.rs",
            Some("/workspace/foo"),
        );
        assert_eq!(result, "src/db.rs", "cross-prefix absolute project_root must resolve correctly");
    }

    // ── backend.audit.deserialize (AC9) ─────────────────────────────────────
    /// AuditFinding deserializes with cwe_id and scope_type (camelCase from LLM JSON).
    #[test]
    fn backend_audit_deserialize_new_fields() {
        let raw = r#"{
            "findingId": "f-001",
            "file": "src/db.rs",
            "lineStart": 10,
            "lineEnd": 15,
            "vulnClass": "sql_injection",
            "severity": "high",
            "description": "SQL injection via user input",
            "evidence": "user input flows into query",
            "cweId": "CWE-89",
            "scopeType": "file"
        }"#;
        let finding: AuditFinding = serde_json::from_str(raw).expect("deserialize must succeed");
        assert_eq!(finding.cwe_id, Some("CWE-89".to_string()));
        assert_eq!(finding.scope_type, Some(FindingScopeType::File));
        assert_eq!(finding.module, None);
    }

    /// AuditFinding with scopeType=module and module field.
    #[test]
    fn backend_audit_deserialize_module_scope() {
        let raw = r#"{
            "findingId": "f-002",
            "file": "",
            "lineStart": 1,
            "lineEnd": 1,
            "vulnClass": "auth_bypass",
            "severity": "critical",
            "description": "Auth bypass in module",
            "evidence": "logic flaw",
            "cweId": "CWE-306",
            "scopeType": "module",
            "module": "auth_service"
        }"#;
        let finding: AuditFinding = serde_json::from_str(raw).expect("deserialize must succeed");
        assert_eq!(finding.scope_type, Some(FindingScopeType::Module));
        assert_eq!(finding.module, Some("auth_service".to_string()));
    }

    // ── backend.audit.passthrough (AC9) ─────────────────────────────────────
    /// AuditFinding missing cweId/scopeType/module deserializes with None defaults
    /// (backward-compat: old LLM output without new fields must not fail).
    #[test]
    fn backend_audit_deserialize_legacy_no_new_fields() {
        let raw = r#"{
            "findingId": "legacy-001",
            "file": "src/old.rs",
            "lineStart": 5,
            "lineEnd": 5,
            "vulnClass": "buffer_overflow",
            "severity": "high",
            "description": "legacy finding",
            "evidence": "evidence"
        }"#;
        let finding: AuditFinding = serde_json::from_str(raw).expect("legacy deserialize must succeed");
        assert_eq!(finding.cwe_id, None, "cwe_id must default to None");
        assert_eq!(finding.scope_type, None, "scope_type must default to None");
        assert_eq!(finding.module, None, "module must default to None");
    }

    // ── backend.task.spawnedTaskProjectRoot (AC7 / Phase A.5) ──────────────
    /// with_project_root builder sets project_root on the record.
    #[test]
    fn backend_task_spawned_task_project_root() {
        use crate::runtime::intelligent::types::IntelligentTaskRecord;

        let record = IntelligentTaskRecord::new_pending(
            "task-001".to_string(),
            "project-001".to_string(),
            "claude-3-5-sonnet".to_string(),
            "fp-abc123".to_string(),
        )
        .with_project_root("/workspace/argus-src");

        assert_eq!(
            record.project_root,
            Some("/workspace/argus-src".to_string()),
            "with_project_root must populate project_root field"
        );
    }

    /// with_project_root accepts any Into<String>.
    #[test]
    fn backend_task_project_root_string_owned() {
        use crate::runtime::intelligent::types::IntelligentTaskRecord;

        let root = "/storage/projects/myproject".to_string();
        let record = IntelligentTaskRecord::new_pending(
            "t2".to_string(),
            "p2".to_string(),
            "model".to_string(),
            "fp".to_string(),
        )
        .with_project_root(root);

        assert_eq!(record.project_root, Some("/storage/projects/myproject".to_string()));
    }

    // ── Phase G backend serde tests (G-B1 … G-B6) ──────────────────────────

    /// G-B1: new `AuditFinding` shape with `evidence_code_snippets` + `evidence_prose`.
    #[test]
    fn g_b1_audit_finding_deserializes_new_shape() {
        let json = r#"{
          "findingId": "f1",
          "vulnClass": "SQL Injection",
          "severity": "high",
          "description": "...",
          "file": "src/a.rs",
          "lineStart": 10,
          "evidence": "",
          "evidenceCodeSnippets": [
            {"file": "src/a.rs", "line_start": 10, "line_end": 15, "code": "fn foo() {}", "language": "rust"}
          ],
          "evidenceProse": "Unsanitized input flows to query"
        }"#;
        let finding: AuditFinding = serde_json::from_str(json).expect("G-B1 deserialize");
        assert_eq!(finding.evidence_code_snippets.len(), 1);
        assert_eq!(finding.evidence_code_snippets[0].file.as_deref(), Some("src/a.rs"));
        assert_eq!(finding.evidence_code_snippets[0].line_start, Some(10));
        assert_eq!(finding.evidence_code_snippets[0].code, "fn foo() {}");
        assert_eq!(finding.evidence_prose.as_deref(), Some("Unsanitized input flows to query"));
        // Round-trip: key fields survive serialize → deserialize
        let serialized = serde_json::to_string(&finding).expect("G-B1 serialize");
        let rt: AuditFinding = serde_json::from_str(&serialized).expect("G-B1 round-trip");
        assert_eq!(rt.evidence_prose.as_deref(), Some("Unsanitized input flows to query"));
        assert_eq!(rt.evidence_code_snippets.len(), 1);
    }

    /// Wire-format regression guard: `EvidenceCodeSnippet` MUST serialize keys
    /// as `lineStart`/`lineEnd` (camelCase) so the frontend's typed reader
    /// (`shared/api/intelligentTasks.ts: interface EvidenceCodeSnippet`) gets
    /// non-undefined values. The original snake_case shape silently broke
    /// related-code line numbering in the vulnerability-detail view — see
    /// `frontend/src/pages/finding-detail/viewModel.ts:buildFullFileDisplayLines`
    /// which falls back to line 1 when lineStart is undefined.
    #[test]
    fn evidence_code_snippet_serializes_camelcase_keys() {
        let snippet = EvidenceCodeSnippet {
            file: Some("src/a.rs".to_string()),
            line_start: Some(122),
            line_end: Some(278),
            code: "fn foo() {}".to_string(),
            language: Some("rust".to_string()),
        };
        let json = serde_json::to_string(&snippet).expect("serialize");
        assert!(
            json.contains("\"lineStart\":122"),
            "expected camelCase lineStart on wire, got: {json}",
        );
        assert!(
            json.contains("\"lineEnd\":278"),
            "expected camelCase lineEnd on wire, got: {json}",
        );
        assert!(
            !json.contains("\"line_start\""),
            "snake_case line_start leaked onto the wire: {json}",
        );
        // Snake-case input still deserializes (alias guard for LLM-emitted snippets).
        let legacy_json = r#"{"file":"src/a.rs","line_start":1,"line_end":2,"code":""}"#;
        let parsed: EvidenceCodeSnippet =
            serde_json::from_str(legacy_json).expect("legacy snake_case still deserializes");
        assert_eq!(parsed.line_start, Some(1));
        assert_eq!(parsed.line_end, Some(2));
    }

    /// G-B2: legacy `AuditFinding` JSON (only `evidence` key, no `evidenceProse`/snippets).
    /// `evidence` round-trips; `evidence_prose` is None; snippets list is empty.
    #[test]
    fn g_b2_audit_finding_legacy_shape_still_works() {
        let json = r#"{
          "findingId": "f1",
          "vulnClass": "xss",
          "severity": "low",
          "description": "...",
          "file": "src/x.rs",
          "lineStart": 42,
          "evidence": "Old narrative with `code` and src/x.rs:42"
        }"#;
        let finding: AuditFinding = serde_json::from_str(json).expect("G-B2 legacy deserialize");
        assert_eq!(finding.evidence, "Old narrative with `code` and src/x.rs:42");
        assert_eq!(finding.evidence_code_snippets.len(), 0);
        assert_eq!(finding.evidence_prose, None);
    }

    /// G-B3: `TraceResult` with `callChain` (PASS1 path).
    #[test]
    fn g_b3_trace_result_call_chain_deserializes() {
        let json = r#"{
          "findingId": "f1",
          "reachable": true,
          "confidence": 0.8,
          "rationale": "...",
          "entryPoint": "http_handler",
          "callChain": [
            {"file": "src/x.rs", "line": 42, "function": "handler", "snippet": "return user.input"}
          ]
        }"#;
        let trace: TraceResult = serde_json::from_str(json).expect("G-B3 deserialize");
        assert_eq!(trace.call_chain.len(), 1);
        assert_eq!(trace.call_chain[0].file.as_deref(), Some("src/x.rs"));
        assert_eq!(trace.call_chain[0].line, Some(42));
        assert_eq!(trace.call_chain[0].function.as_deref(), Some("handler"));
        assert_eq!(trace.entry_point.as_deref(), Some("http_handler"));
    }

    /// G-B4: `TraceResult` PASS2 schema — `callChain` + `entryPoint` both present.
    /// Confirms the struct supports both PASS1 and PASS2 JSON identically.
    #[test]
    fn g_b4_trace_result_pass2_round_trip() {
        let json = r#"{
          "findingId": "f2",
          "reachable": true,
          "confidence": 0.95,
          "rationale": "attacker controlled",
          "entryPoint": "api_route",
          "callChain": [
            {"file": "src/api.rs", "line": 5, "function": "route_handler", "snippet": "handle(req)"},
            {"file": "src/db.rs", "line": 99, "function": "exec_query", "snippet": "db.query(sql)"}
          ]
        }"#;
        let trace: TraceResult = serde_json::from_str(json).expect("G-B4 deserialize");
        assert_eq!(trace.call_chain.len(), 2);
        assert_eq!(trace.entry_point.as_deref(), Some("api_route"));
        // Round-trip
        let serialized = serde_json::to_string(&trace).expect("G-B4 serialize");
        let rt: TraceResult = serde_json::from_str(&serialized).expect("G-B4 round-trip");
        assert_eq!(rt.call_chain.len(), 2);
        assert_eq!(rt.entry_point.as_deref(), Some("api_route"));
    }

    /// G-B5: 12 hops deserialize without truncation (AC12).
    #[test]
    fn g_b5_trace_result_supports_more_than_eight_hops() {
        let hops_json: Vec<String> = (0..12)
            .map(|i| format!(r#"{{"file":"f{i}.rs","line":{i},"function":"fn{i}","snippet":""}}"#))
            .collect();
        let json = format!(
            r#"{{"findingId":"f1","reachable":true,"confidence":0.9,"rationale":"...","callChain":[{}]}}"#,
            hops_json.join(",")
        );
        let trace: TraceResult = serde_json::from_str(&json).expect("G-B5 deserialize 12 hops");
        assert_eq!(trace.call_chain.len(), 12);
    }

    /// G-B6: ellipsis hop `{file:null,line:null,function:"…(4 hops omitted)…",snippet:null}`
    /// round-trips cleanly (AC12).
    #[test]
    fn g_b6_trace_result_accepts_ellipsis_hop() {
        let json = r#"{
          "findingId": "f1",
          "reachable": true,
          "confidence": 0.7,
          "rationale": "...",
          "callChain": [
            {"file": null, "line": null, "function": "…(4 hops omitted)…", "snippet": null}
          ]
        }"#;
        let trace: TraceResult = serde_json::from_str(json).expect("G-B6 ellipsis hop");
        assert_eq!(trace.call_chain.len(), 1);
        assert_eq!(trace.call_chain[0].file, None);
        assert_eq!(
            trace.call_chain[0].function.as_deref(),
            Some("…(4 hops omitted)…")
        );
        // Round-trip preserves the ellipsis marker
        let serialized = serde_json::to_string(&trace).expect("G-B6 serialize");
        let rt: TraceResult = serde_json::from_str(&serialized).expect("G-B6 round-trip");
        assert_eq!(rt.call_chain[0].function.as_deref(), Some("…(4 hops omitted)…"));
    }
}
