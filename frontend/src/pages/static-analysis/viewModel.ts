import { getEstimatedTaskProgressPercent } from "@/features/tasks/services/taskProgress";
import { resolveStaticScanGroupStatus } from "@/features/tasks/services/staticScanGrouping";
import {
  formatTaskDuration,
  getTaskDisplayStatusSummary,
} from "@/features/tasks/services/taskDisplay";
import {
	normalizeStaticAnalysisSeverity,
	type NormalizedSeverity,
} from "@/shared/utils/staticAnalysisSeverity";

export type Engine = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "pmd";
export type EngineFilter = "all" | Engine;
export type FindingStatus = "open" | "verified" | "false_positive";
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
  error_message?: string | null;
  diagnostics_summary?: string | null;
}

export interface StaticAnalysisProgressSummary {
  progressPercent: number;
}

export type StaticAnalysisAggregateStatus =
  | "completed"
  | "running"
  | "pending"
  | "failed"
  | "interrupted";

export interface StaticAnalysisFailureReason {
  engine: Engine;
  engineLabel: string;
  message: string;
  isTimeout: boolean;
}

export interface StaticAnalysisEngineStatus {
  engine: Engine;
  engineLabel: string;
  status: string;
  statusLabel: string;
}

export interface StaticAnalysisTaskStatusSummary {
  aggregateStatus: StaticAnalysisAggregateStatus;
  aggregateLabel: string;
  progressHint: string;
  engineStatuses: StaticAnalysisEngineStatus[];
  failureReasons: StaticAnalysisFailureReason[];
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

type MinimalPhpstanFinding = {
  id: string;
  scan_task_id?: string | null;
  file_path?: string | null;
  line?: unknown;
  message?: string | null;
  identifier?: string | null;
  status?: string | null;
};

type MinimalPmdFinding = {
  id: string;
  scan_task_id?: string | null;
  file_path?: string | null;
  begin_line?: unknown;
  end_line?: unknown;
  rule?: string | null;
  ruleset?: string | null;
  priority?: unknown;
  message?: string | null;
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
  if (unified.startsWith("/scan/project/")) {
    return unified.slice("/scan/project/".length) || "-";
  }
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

export function getStaticAnalysisFindingStatusLabel(status?: string | null): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "verified") return "确报";
  if (normalized === "false_positive") return "误报";
  return "待验证";
}

export function getStaticAnalysisFindingStatusBadgeClass(status?: string | null): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "verified") {
    return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
  }
  if (normalized === "false_positive") {
    return "bg-rose-500/20 text-rose-300 border-rose-500/30";
  }
  return "bg-muted text-muted-foreground border-border";
}

export function formatStaticAnalysisDuration(ms: number): string {
  return formatTaskDuration(ms, { showMsWhenSubSecond: true });
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

function getEngineLabel(engine: Engine): string {
  if (engine === "opengrep") return "Opengrep";
  if (engine === "gitleaks") return "Gitleaks";
  if (engine === "bandit") return "Bandit";
  if (engine === "phpstan") return "PHPStan";
  return "PMD";
}

function getStaticAnalysisStatusLabel(status: string): string {
  return getTaskDisplayStatusSummary(status).statusLabel;
}

export function getStaticAnalysisStatusBadgeClassName(status: string): string {
  return getTaskDisplayStatusSummary(status).badgeClassName;
}

export function getStaticAnalysisProgressAccentClassName(status: string): string {
  const progressBarClass = getTaskDisplayStatusSummary(status).progressBarClassName;
  if (progressBarClass === "bg-emerald-400") return "[&>div]:bg-emerald-500";
  if (progressBarClass === "bg-sky-400") return "[&>div]:bg-sky-500";
  if (progressBarClass === "bg-rose-400") return "[&>div]:bg-rose-500";
  if (progressBarClass === "bg-orange-400") return "[&>div]:bg-amber-500";
  return "[&>div]:bg-muted-foreground";
}

function buildStaticAnalysisProgressHint(
  status: StaticAnalysisAggregateStatus,
): string {
  if (status === "completed") return "扫描已结束，全部引擎已完成";
  if (status === "running") return "扫描进行中，仍有引擎正在执行";
  if (status === "pending") return "扫描排队中，等待引擎启动";
  if (status === "failed") return "扫描已结束，至少一个引擎失败";
  return "扫描已结束，任务已中断";
}

function getStaticAnalysisFailureFallbackMessage(status: string): string {
  return normalizeStaticAnalysisStatus(status) === "failed"
    ? "任务已失败，请查看后端日志获取更多信息。"
    : "任务已中断。";
}

function isTimeoutLikeText(text?: string | null): boolean {
  const normalized = String(text || "").trim().toLowerCase();
  if (!normalized) return false;
  return (
    normalized.includes("超时") ||
    normalized.includes("timeout") ||
    normalized.includes("timed out") ||
    normalized.includes("超出设定时间")
  );
}

function normalizeReasonText(value?: string | null): string | null {
  const text = String(value || "").trim();
  return text || null;
}

function resolveTaskFailureReason(task: StaticAnalysisSummaryTaskLike): string {
  const errorMessage = normalizeReasonText(task.error_message);
  if (errorMessage) return errorMessage;
  const diagnosticsSummary = normalizeReasonText(task.diagnostics_summary);
  if (diagnosticsSummary) return diagnosticsSummary;

  return getStaticAnalysisFailureFallbackMessage(task.status);
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
  phpstanTask: StaticAnalysisSummaryTaskLike | null;
  pmdTask?: StaticAnalysisSummaryTaskLike | null;
  nowMs?: number;
}): number {
  const pmdTask = input.pmdTask ?? null;
  return (
    getStaticAnalysisTaskDisplayDurationMs(input.opengrepTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.gitleaksTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.banditTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.phpstanTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(pmdTask, input.nowMs)
  );
}

export function buildStaticAnalysisTaskStatusSummary(input: {
  opengrepTask: StaticAnalysisSummaryTaskLike | null;
  gitleaksTask: StaticAnalysisSummaryTaskLike | null;
  banditTask: StaticAnalysisSummaryTaskLike | null;
  phpstanTask: StaticAnalysisSummaryTaskLike | null;
  pmdTask?: StaticAnalysisSummaryTaskLike | null;
}): StaticAnalysisTaskStatusSummary {
  const pmdTask = input.pmdTask ?? null;
  const engineEntries = [
    { engine: "opengrep" as const, task: input.opengrepTask },
    { engine: "gitleaks" as const, task: input.gitleaksTask },
    { engine: "bandit" as const, task: input.banditTask },
    { engine: "phpstan" as const, task: input.phpstanTask },
    { engine: "pmd" as const, task: pmdTask },
  ].filter(
    (entry): entry is { engine: Engine; task: StaticAnalysisSummaryTaskLike } =>
      Boolean(entry.task),
  );

  const aggregateStatus =
    engineEntries.length > 0
      ? resolveStaticScanGroupStatus({
          opengrepTask: input.opengrepTask ?? undefined,
          gitleaksTask: input.gitleaksTask ?? undefined,
          banditTask: input.banditTask ?? undefined,
          phpstanTask: input.phpstanTask ?? undefined,
          pmdTask: pmdTask ?? undefined,
        })
      : "failed";

  const failureReasons: StaticAnalysisFailureReason[] = engineEntries
    .filter(({ task }) => {
      const normalized = normalizeStaticAnalysisStatus(task.status);
      return (
        normalized === "failed" ||
        normalized === "cancelled" ||
        normalized === "interrupted" ||
        normalized === "aborted"
      );
    })
    .map(({ engine, task }) => {
      const message = resolveTaskFailureReason(task);
      return {
        engine,
        engineLabel: getEngineLabel(engine),
        message,
        isTimeout: isTimeoutLikeText(message),
      };
    });

  const failureReasonByEngine = new Map(
    failureReasons.map((reason) => [reason.engine, reason]),
  );

  const engineStatuses = engineEntries.map(({ engine, task }) => {
    const failureReason = failureReasonByEngine.get(engine);
    const normalizedStatus = normalizeStaticAnalysisStatus(task.status);
    const timeoutFailed =
      normalizedStatus === "failed" && Boolean(failureReason?.isTimeout);
    return {
      engine,
      engineLabel: getEngineLabel(engine),
      status: normalizedStatus,
      statusLabel: timeoutFailed
        ? "超出设定时间"
        : getStaticAnalysisStatusLabel(task.status),
    };
  });

  const hasTimeoutFailure = failureReasons.some((reason) => reason.isTimeout);
  const hasNonTimeoutFailure = failureReasons.some((reason) => !reason.isTimeout);
  const timeoutOnlyFailure =
    aggregateStatus === "failed" && hasTimeoutFailure && !hasNonTimeoutFailure;

  const aggregateLabel = timeoutOnlyFailure
    ? "超出设定时间"
    : getStaticAnalysisStatusLabel(aggregateStatus);
  const progressHint = timeoutOnlyFailure
    ? "扫描已结束，至少一个引擎超出设定时间"
    : buildStaticAnalysisProgressHint(aggregateStatus);

  return {
    aggregateStatus,
    aggregateLabel,
    progressHint,
    engineStatuses,
    failureReasons,
  };
}

export function buildStaticAnalysisProgressSummary(input: {
  opengrepTask: StaticAnalysisProgressTaskLike | null;
  gitleaksTask: StaticAnalysisProgressTaskLike | null;
  banditTask: StaticAnalysisProgressTaskLike | null;
  phpstanTask: StaticAnalysisProgressTaskLike | null;
  pmdTask?: StaticAnalysisProgressTaskLike | null;
  nowMs?: number;
}): StaticAnalysisProgressSummary {
  const pmdTask = input.pmdTask ?? null;
  const tasks = [
    input.opengrepTask,
    input.gitleaksTask,
    input.banditTask,
    input.phpstanTask,
    pmdTask,
  ].filter(Boolean) as StaticAnalysisProgressTaskLike[];
  if (tasks.length === 0) {
    return { progressPercent: 0 };
  }

  const createdAt = [...tasks]
    .map((task) => task.created_at)
    .sort((a, b) => {
      const left = toStaticAnalysisTimestampMs(a) ?? 0;
      const right = toStaticAnalysisTimestampMs(b) ?? 0;
      return left - right;
    })[0];
  const statusSummary = buildStaticAnalysisTaskStatusSummary({
    opengrepTask: input.opengrepTask,
    gitleaksTask: input.gitleaksTask,
    banditTask: input.banditTask,
    phpstanTask: input.phpstanTask,
    pmdTask,
  });

  return {
    progressPercent: getEstimatedTaskProgressPercent(
      {
        status: statusSummary.aggregateStatus,
        createdAt,
        startedAt: createdAt,
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
  opengrepTaskId: string;
}): UnifiedFindingRow[] {
  return input.opengrepFindings.map((finding) => {
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
