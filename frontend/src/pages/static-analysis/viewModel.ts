import { getEstimatedTaskProgressPercent } from "@/features/tasks/services/taskProgress";
import {
	normalizeStaticAnalysisSeverity,
	type NormalizedSeverity,
} from "@/shared/utils/staticAnalysisSeverity";

export type Engine = "opengrep" | "gitleaks" | "bandit";
export type EngineFilter = "all" | Engine;
export type FindingStatus = "open" | "verified" | "false_positive" | "fixed";
export type StatusFilter = "all" | FindingStatus;
export type ConfidenceFilter = "all" | "HIGH" | "MEDIUM" | "LOW";
export type SeverityFilter = "all" | NormalizedSeverity;
export type NormalizedConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface StaticAnalysisProgressTaskLike {
  id: string;
  project_id: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
}

export interface StaticAnalysisSummaryTaskLike
  extends StaticAnalysisProgressTaskLike {
  scan_duration_ms?: number | null;
  total_findings?: number | null;
  files_scanned?: number | null;
}

export interface StaticAnalysisProgressSummary {
  progressPercent: number;
}

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

type MinimalBanditFinding = {
  id: string;
  scan_task_id?: string | null;
  test_id?: string | null;
  test_name?: string | null;
  issue_severity?: string | null;
  issue_confidence?: string | null;
  file_path?: string | null;
  line_number?: unknown;
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

const STATIC_ANALYSIS_TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "interrupted",
  "cancelled",
  "aborted",
]);

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

function normalizeStaticAnalysisStatus(status?: string | null): string {
  return String(status || "").trim().toLowerCase();
}

function toStaticAnalysisTimestampMs(value?: string | null): number | null {
  const timestamp = new Date(String(value || "")).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

export function toStaticAnalysisSafeMetric(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function getStaticAnalysisTaskDisplayDurationMs(
  task: StaticAnalysisSummaryTaskLike | null,
  nowMs = Date.now(),
): number {
  if (!task) return 0;

  const persistedDurationMs = toStaticAnalysisSafeMetric(task.scan_duration_ms);
  const createdAtMs = toStaticAnalysisTimestampMs(task.created_at);
  const updatedAtMs = toStaticAnalysisTimestampMs(task.updated_at);
  const status = normalizeStaticAnalysisStatus(task.status);

  if (status === "pending" || status === "running") {
    const elapsedMs =
      createdAtMs === null ? 0 : Math.max(0, Math.floor(nowMs - createdAtMs));
    return Math.max(persistedDurationMs, elapsedMs, 0);
  }

  if (STATIC_ANALYSIS_TERMINAL_STATUSES.has(status)) {
    if (persistedDurationMs > 0) {
      return persistedDurationMs;
    }
    if (createdAtMs !== null && updatedAtMs !== null) {
      return Math.max(0, Math.floor(updatedAtMs - createdAtMs));
    }
  }

  return persistedDurationMs;
}

export function getStaticAnalysisTotalDisplayDurationMs(input: {
  opengrepTask: StaticAnalysisSummaryTaskLike | null;
  gitleaksTask: StaticAnalysisSummaryTaskLike | null;
  banditTask: StaticAnalysisSummaryTaskLike | null;
  nowMs?: number;
}): number {
  return (
    getStaticAnalysisTaskDisplayDurationMs(input.opengrepTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.gitleaksTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.banditTask, input.nowMs)
  );
}

export function buildStaticAnalysisProgressSummary(input: {
  opengrepTask: StaticAnalysisProgressTaskLike | null;
  gitleaksTask: StaticAnalysisProgressTaskLike | null;
  banditTask: StaticAnalysisProgressTaskLike | null;
  nowMs?: number;
}): StaticAnalysisProgressSummary {
  const primaryTask =
    input.opengrepTask || input.gitleaksTask || input.banditTask || null;
  if (!primaryTask) {
    return { progressPercent: 0 };
  }

  return {
    progressPercent: getEstimatedTaskProgressPercent(
      {
        status: primaryTask.status,
        createdAt: primaryTask.created_at,
        startedAt: primaryTask.created_at,
      },
      input.nowMs,
    ),
  };
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
  banditFindings: MinimalBanditFinding[];
  opengrepTaskId: string;
  gitleaksTaskId: string;
  banditTaskId: string;
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

  const banditRows = input.banditFindings.map((finding) => {
    const severity = normalizeStaticAnalysisSeverity(finding.issue_severity);
    const confidence = normalizeStaticAnalysisConfidence(finding.issue_confidence);
    const testId = String(finding.test_id || "").trim();
    const testName = String(finding.test_name || "").trim();
    const rule = [testId, testName].filter(Boolean).join(" · ");
    return {
      key: `bandit:${finding.id}`,
      id: finding.id,
      taskId: finding.scan_task_id || input.banditTaskId,
      engine: "bandit" as const,
      rule: rule || "-",
      filePath: normalizeStaticAnalysisPath(finding.file_path),
      line: toStaticAnalysisPositiveLine(finding.line_number),
      severity,
      severityScore: SEVERITY_SCORE[severity],
      confidence,
      confidenceScore: CONFIDENCE_SCORE[confidence],
      status: String(finding.status || "open").trim().toLowerCase(),
    };
  });

  return [...opengrepRows, ...gitleaksRows, ...banditRows];
}

export function buildStaticAnalysisListState(input: {
  rows: UnifiedFindingRow[];
  engineFilter: EngineFilter;
  statusFilter: StatusFilter;
  severityFilter: SeverityFilter;
  confidenceFilter: ConfidenceFilter;
  page: number;
  pageSize?: number;
}) {
  const pageSize = input.pageSize ?? 10;
  const filteredRows = input.rows
    .filter((row) => input.engineFilter === "all" || row.engine === input.engineFilter)
    .filter((row) => input.statusFilter === "all" || row.status === input.statusFilter)
    .filter((row) => {
      if (input.severityFilter === "all") return true;
      return row.severity === input.severityFilter;
    })
    .filter((row) => {
      if (input.confidenceFilter === "all") return true;
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
