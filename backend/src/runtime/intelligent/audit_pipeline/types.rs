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
#[serde(rename_all = "camelCase")]
pub struct PocResult {
    pub language: String,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub reproduced: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AuditFinding {
    pub finding_id: String,
    pub file: String,
    #[serde(default = "default_line")]
    pub line_start: u32,
    #[serde(default = "default_line")]
    pub line_end: u32,
    pub vuln_class: String,
    pub severity: String,
    pub description: String,
    #[serde(alias = "evidence_snippet")]
    pub evidence: String,
    #[serde(default)]
    pub confidence: Option<f64>,
    #[serde(default)]
    pub task_id: Option<String>,
    #[serde(default)]
    pub poc_code: Option<String>,
    #[serde(default)]
    pub poc_result: Option<PocResult>,
    #[serde(default)]
    pub hedged_language: Option<bool>,
}

impl Default for AuditFinding {
    fn default() -> Self {
        Self {
            finding_id: String::new(),
            file: String::new(),
            line_start: 1,
            line_end: 1,
            vuln_class: String::new(),
            severity: "medium".to_string(),
            description: String::new(),
            evidence: String::new(),
            confidence: None,
            task_id: None,
            poc_code: None,
            poc_result: None,
            hedged_language: None,
        }
    }
}

fn default_line() -> u32 {
    1
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
                    poc_result: finding.poc_result.as_ref().map(|p| serde_json::to_value(p).unwrap_or_default()),
                }
            })
            .collect()
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
