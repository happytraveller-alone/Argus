export type Engine = "opengrep" | "gitleaks";
export type EngineFilter = "all" | Engine;
export type FindingStatus = "open" | "verified" | "false_positive" | "fixed";
export type StatusFilter = "all" | FindingStatus;
export type ConfidenceFilter = "all" | "HIGH" | "MEDIUM" | "LOW";
export type NormalizedSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type NormalizedConfidence = "HIGH" | "MEDIUM" | "LOW";

export type UnifiedFindingRow = {
  key: string;
  id: string;
  taskId: string;
  engine: Engine;
  rule: string;
  filePath: string;
  line: number | null;
  severity: NormalizedSeverity;
  severityScore: number;
  confidence: NormalizedConfidence;
  confidenceScore: number;
  status: string;
};

type MinimalOpengrepFinding = {
  id: string;
  scan_task_id?: string | null;
  severity?: string | null;
  confidence?: string | null;
  file_path?: string | null;
  start_line?: unknown;
  status?: string | null;
  rule_name?: string | null;
  rule?: Record<string, unknown> | null;
};

type MinimalGitleaksFinding = {
  id: string;
  scan_task_id?: string | null;
  rule_id?: string | null;
  file_path?: string | null;
  start_line?: unknown;
  status?: string | null;
};

const SEVERITY_SCORE: Record<NormalizedSeverity, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

const CONFIDENCE_SCORE: Record<NormalizedConfidence, number> = {
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

export function decodeStaticAnalysisPathParam(raw: string | undefined): string {
  try {
    return decodeURIComponent(String(raw || "")).trim();
  } catch {
    return String(raw || "").trim();
  }
}

export function normalizeStaticAnalysisPath(path?: string | null): string {
  const raw = String(path || "").trim();
  if (!raw) return "-";
  const unified = raw.replace(/\\/g, "/");
  const tmpIndex = unified.indexOf("/tmp/");
  if (tmpIndex >= 0) {
    const trimmed = unified.slice(tmpIndex + 5);
    const parts = trimmed.split("/").filter(Boolean);
    if (parts.length > 1) {
      return parts.slice(1).join("/");
    }
  }
  return unified.replace(/^\/+/, "") || "-";
}

export function normalizeStaticAnalysisSeverity(
  severity?: string | null,
): NormalizedSeverity {
  const normalized = String(severity || "").trim().toUpperCase();
  if (normalized === "CRITICAL") return "CRITICAL";
  if (normalized === "HIGH") return "HIGH";
  if (
    normalized === "ERROR" ||
    normalized === "WARNING" ||
    normalized === "MEDIUM"
  ) {
    return "MEDIUM";
  }
  return "LOW";
}

export function getStaticAnalysisSeverityLabel(
  severity: NormalizedSeverity,
): string {
  if (severity === "CRITICAL") return "严重";
  if (severity === "HIGH") return "高危";
  if (severity === "MEDIUM") return "中危";
  return "低危";
}

export function getStaticAnalysisSeverityBadgeClass(
  severity: NormalizedSeverity,
): string {
  if (severity === "CRITICAL") {
    return "bg-rose-500/20 text-rose-300 border-rose-500/30";
  }
  if (severity === "HIGH") {
    return "bg-amber-500/20 text-amber-300 border-amber-500/30";
  }
  if (severity === "MEDIUM") {
    return "bg-sky-500/20 text-sky-300 border-sky-500/30";
  }
  return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
}

export function normalizeStaticAnalysisConfidence(
  confidence?: string | null,
): NormalizedConfidence {
  const normalized = String(confidence || "").trim().toUpperCase();
  if (normalized === "HIGH") return "HIGH";
  if (normalized === "LOW") return "LOW";
  return "MEDIUM";
}

export function getStaticAnalysisConfidenceLabel(
  confidence: NormalizedConfidence,
): string {
  if (confidence === "HIGH") return "高";
  if (confidence === "LOW") return "低";
  return "中";
}

export function getStaticAnalysisConfidenceBadgeClass(
  confidence: NormalizedConfidence,
): string {
  if (confidence === "HIGH") {
    return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
  }
  if (confidence === "LOW") {
    return "bg-sky-500/20 text-sky-300 border-sky-500/30";
  }
  return "bg-amber-500/20 text-amber-300 border-amber-500/30";
}

export function formatStaticAnalysisDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainSeconds}s`;
}

export function toStaticAnalysisPositiveLine(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function isStaticAnalysisPollableStatus(status?: string | null): boolean {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "pending" || normalized === "running";
}

export function isStaticAnalysisInterruptibleStatus(
  status?: string | null,
): boolean {
  return isStaticAnalysisPollableStatus(status);
}

export function isStaticAnalysisCompletedStatus(
  status?: string | null,
): boolean {
  return String(status || "").trim().toLowerCase() === "completed";
}

export function toStaticAnalysisSafeMetric(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function getStaticAnalysisOpengrepRuleName(
  finding: MinimalOpengrepFinding,
): string {
  const rule = (finding.rule || {}) as Record<string, unknown>;
  const byField = String(finding.rule_name || "").trim();
  if (byField) return byField;
  const byCheckId = String(rule.check_id || rule.id || "").trim();
  if (byCheckId) return byCheckId;
  return "-";
}

export function buildUnifiedFindingRows(input: {
  opengrepFindings: MinimalOpengrepFinding[];
  gitleaksFindings: MinimalGitleaksFinding[];
  opengrepTaskId: string;
  gitleaksTaskId: string;
}): UnifiedFindingRow[] {
  const opengrepRows = input.opengrepFindings.map((finding) => {
    const severity = normalizeStaticAnalysisSeverity(finding.severity);
    const confidence = normalizeStaticAnalysisConfidence(finding.confidence);
    return {
      key: `opengrep:${finding.id}`,
      id: finding.id,
      taskId: finding.scan_task_id || input.opengrepTaskId,
      engine: "opengrep" as const,
      rule: getStaticAnalysisOpengrepRuleName(finding),
      filePath: normalizeStaticAnalysisPath(finding.file_path),
      line: toStaticAnalysisPositiveLine(finding.start_line),
      severity,
      severityScore: SEVERITY_SCORE[severity],
      confidence,
      confidenceScore: CONFIDENCE_SCORE[confidence],
      status: String(finding.status || "open").trim().toLowerCase(),
    };
  });

  const gitleaksRows = input.gitleaksFindings.map((finding) => ({
    key: `gitleaks:${finding.id}`,
    id: finding.id,
    taskId: finding.scan_task_id || input.gitleaksTaskId,
    engine: "gitleaks" as const,
    rule: String(finding.rule_id || "").trim() || "-",
    filePath: normalizeStaticAnalysisPath(finding.file_path),
    line: toStaticAnalysisPositiveLine(finding.start_line),
    severity: "LOW" as const,
    severityScore: SEVERITY_SCORE.LOW,
    confidence: "MEDIUM" as const,
    confidenceScore: CONFIDENCE_SCORE.MEDIUM,
    status: String(finding.status || "open").trim().toLowerCase(),
  }));

  return [...opengrepRows, ...gitleaksRows];
}

export function buildStaticAnalysisListState(input: {
  rows: UnifiedFindingRow[];
  engineFilter: EngineFilter;
  statusFilter: StatusFilter;
  confidenceFilter: ConfidenceFilter;
  page: number;
  pageSize?: number;
}) {
  const pageSize = input.pageSize ?? 10;
  const filteredRows = input.rows
    .filter((row) => input.engineFilter === "all" || row.engine === input.engineFilter)
    .filter((row) => input.statusFilter === "all" || row.status === input.statusFilter)
    .filter((row) => {
      if (input.confidenceFilter === "all") return true;
      if (row.engine !== "opengrep") return true;
      return row.confidence === input.confidenceFilter;
    })
    .sort((a, b) => {
      if (a.severityScore !== b.severityScore) {
        return b.severityScore - a.severityScore;
      }
      if (a.confidenceScore !== b.confidenceScore) {
        return b.confidenceScore - a.confidenceScore;
      }
      const pathCompare = a.filePath.localeCompare(b.filePath);
      if (pathCompare !== 0) return pathCompare;
      const lineA = a.line ?? Number.MAX_SAFE_INTEGER;
      const lineB = b.line ?? Number.MAX_SAFE_INTEGER;
      if (lineA !== lineB) return lineA - lineB;
      return a.key.localeCompare(b.key);
    });

  const totalRows = filteredRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const clampedPage = Math.min(input.page, totalPages);
  const pageStart = (clampedPage - 1) * pageSize;
  const pagedRows = filteredRows.slice(pageStart, pageStart + pageSize);

  return {
    filteredRows,
    totalRows,
    totalPages,
    clampedPage,
    pageStart,
    pagedRows,
  };
}
