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

export type Engine = "opengrep" | "codeql";
export type EngineFilter = "all" | Engine;
export type FindingStatus = "open" | "verified" | "false_positive";
export type StatusFilter = "all" | FindingStatus;
export type ConfidenceFilter = "all" | "HIGH" | "MEDIUM" | "LOW";
export type SeverityFilter = "all" | NormalizedSeverity;
export type NormalizedConfidence = "HIGH" | "MEDIUM" | "LOW";

export interface StaticAnalysisProgressTaskLike {
  id: string;
  project_id: string;
  project_name?: string | null;
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

export interface StaticAnalysisHeaderSummary {
  projectName: string;
  statusLabel: string;
  progressPercent: number;
  durationLabel: string;
  totalFindings: number;
  aggregateStatus: StaticAnalysisAggregateStatus | "pending";
}

export interface CodeqlExplorationProgressEventLike {
  timestamp?: string | null;
  event_type?: string | null;
  stage?: string | null;
  progress?: number | null;
  round?: number | null;
  redaction?: {
    applied?: boolean;
    patterns?: string[];
  } | Record<string, unknown> | null;
  payload?: Record<string, unknown> | null;
}

export interface CodeqlExplorationTimelineRow {
  key: string;
  timestamp: string;
  label: string;
  detail: string;
  command: string | null;
  stdout: string | null;
  stderr: string | null;
  exitCode: number | null;
  failureCategory: string | null;
  dependencyInstallation: string | null;
  reuseReason: string | null;
  redacted: boolean;
}

export function countCodeqlReasoningRounds(
  events: CodeqlExplorationProgressEventLike[],
): number {
  const seen = new Set<number>();
  for (const event of events) {
    if (event.round != null) {
      seen.add(event.round);
    }
  }
  return seen.size;
}

export function resolveStaticAnalysisProjectNameFallback(input: {
  taskProjectName?: string | null;
  resolvedProjectName?: string | null;
  projectId?: string | null;
}): string {
  return (
    String(
      input.taskProjectName ||
        input.resolvedProjectName ||
        input.projectId ||
        "-",
    ).trim() || "-"
  );
}

function isStaticAnalysisBootstrapPending(input: {
  opengrepTask: StaticAnalysisSummaryTaskLike | null;
  codeqlTask: StaticAnalysisSummaryTaskLike | null;
  enabledEngines: Engine[];
  loadingInitial?: boolean;
}): boolean {
  const tasksByEngine: Record<Engine, StaticAnalysisSummaryTaskLike | null> = {
    opengrep: input.opengrepTask,
    codeql: input.codeqlTask,
  };
  const hasAnyLoadedTask = Object.values(tasksByEngine).some(Boolean);
  const loadedEnabledEngineCount = input.enabledEngines.filter((engine) =>
    Boolean(tasksByEngine[engine]),
  ).length;
  return Boolean(
    input.loadingInitial &&
      input.enabledEngines.length > 0 &&
      (!hasAnyLoadedTask || loadedEnabledEngineCount < input.enabledEngines.length),
  );
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
const OPENGREP_INTERNAL_RULE_PREFIX = "opengrep-rules.internal.";

function formatStaticAnalysisOpengrepRuleName(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "-";

  if (normalized.startsWith(OPENGREP_INTERNAL_RULE_PREFIX)) {
    const scopedRuleName = normalized.slice(OPENGREP_INTERNAL_RULE_PREFIX.length);
    const languageSeparatorIndex = scopedRuleName.indexOf(".");

    if (
      languageSeparatorIndex >= 0 &&
      languageSeparatorIndex < scopedRuleName.length - 1
    ) {
      return scopedRuleName.slice(languageSeparatorIndex + 1);
    }
  }

  return normalized;
}

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

export function shouldRefreshStaticAnalysisResultsAfterCompletion(options: {
  taskId: string;
  status?: string | null;
  refreshedTaskId?: string | null;
}): boolean {
  return Boolean(
    options.taskId &&
      isStaticAnalysisCompletedStatus(options.status) &&
      options.refreshedTaskId !== options.taskId,
  );
}

function normalizeStaticAnalysisStatus(status?: string | null): string {
  return String(status || "").trim().toLowerCase();
}

function getEngineLabel(engine: Engine): string {
  if (engine === "opengrep") return "Opengrep";
  return "CodeQL";
}

function stringifyTimelineValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function getTimelinePayloadString(
  payload: Record<string, unknown>,
  keys: string[],
): string | null {
  for (const key of keys) {
    const value = stringifyTimelineValue(payload[key]);
    if (value) return value;
  }
  return null;
}

function getCodeqlExplorationStageLabel(event: CodeqlExplorationProgressEventLike): string {
  const stage = String(event.stage || event.event_type || "").trim();
  switch (stage) {
    case "build_plan_reuse_check":
      return "复用检查";
    case "build_plan_reused":
      return "复用构建方案";
    case "build_plan_reset":
      return "重置构建方案";
    case "llm_round_started":
      return "LLM 轮次";
    case "sandbox_command_completed":
    case "compile_sandbox":
      return "沙箱命令";
    case "dependency_installation_detected":
      return "依赖安装";
    case "codeql_capture_validation":
    case "database_create":
      return "捕获验证";
    case "build_plan_accepted":
      return "方案接受";
    case "cancelled_cleanup_completed":
      return "取消清理";
    case "failed":
      return "失败";
    default:
      return stage || "CodeQL 探索";
  }
}

export function buildCodeqlExplorationTimelineRows(
  events: CodeqlExplorationProgressEventLike[] = [],
): CodeqlExplorationTimelineRow[] {
  return events.map((event, index) => {
    const payload = event.payload ?? {};
    const label = getCodeqlExplorationStageLabel(event);
    const detail =
      getTimelinePayloadString(payload, [
        "reasoning_summary",
        "message",
        "reuse_reason",
        "failure_category",
      ]) || label;
    const dependencyInstallation = getTimelinePayloadString(payload, [
      "dependency_installation",
      "dependency_installation_detected",
    ]);
    const exitCodeValue = payload.exit_code;
    const exitCode =
      typeof exitCodeValue === "number" && Number.isFinite(exitCodeValue)
        ? exitCodeValue
        : null;
    const redaction = event.redaction as { applied?: boolean } | null | undefined;

    return {
      key: `${event.timestamp || "event"}:${index}`,
      timestamp: String(event.timestamp || ""),
      label,
      detail,
      command: getTimelinePayloadString(payload, ["command", "commands"]),
      stdout: getTimelinePayloadString(payload, ["stdout"]),
      stderr: getTimelinePayloadString(payload, ["stderr"]),
      exitCode,
      failureCategory: getTimelinePayloadString(payload, ["failure_category"]),
      dependencyInstallation,
      reuseReason: getTimelinePayloadString(payload, ["reuse_reason"]),
      redacted: Boolean(redaction?.applied),
    };
  });
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
  codeqlTask: StaticAnalysisSummaryTaskLike | null;
  nowMs?: number;
}): number {
  return (
    getStaticAnalysisTaskDisplayDurationMs(input.opengrepTask, input.nowMs) +
    getStaticAnalysisTaskDisplayDurationMs(input.codeqlTask, input.nowMs)
  );
}

export function buildStaticAnalysisTaskStatusSummary(input: {
  opengrepTask: StaticAnalysisSummaryTaskLike | null;
  codeqlTask: StaticAnalysisSummaryTaskLike | null;
}): StaticAnalysisTaskStatusSummary {
  const engineEntries = [
    { engine: "opengrep" as const, task: input.opengrepTask },
    { engine: "codeql" as const, task: input.codeqlTask },
  ].filter(
    (entry): entry is { engine: Engine; task: StaticAnalysisSummaryTaskLike } =>
      Boolean(entry.task),
  );

  const aggregateStatus =
    engineEntries.length > 0
      ? resolveStaticScanGroupStatus({
          opengrepTask: input.opengrepTask ?? undefined,
          codeqlTask: input.codeqlTask ?? undefined,
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
  codeqlTask: StaticAnalysisProgressTaskLike | null;
  nowMs?: number;
}): StaticAnalysisProgressSummary {
  const tasks = [input.opengrepTask, input.codeqlTask].filter(
    Boolean,
  ) as StaticAnalysisProgressTaskLike[];
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
    codeqlTask: input.codeqlTask,
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

export function buildStaticAnalysisHeaderSummary(input: {
  opengrepTask: StaticAnalysisSummaryTaskLike | null;
  codeqlTask: StaticAnalysisSummaryTaskLike | null;
  enabledEngines: Engine[];
  loadingInitial?: boolean;
  nowMs?: number;
  fallbackProjectName?: string | null;
}): StaticAnalysisHeaderSummary {
  const isBootstrapping = isStaticAnalysisBootstrapPending(input);
  const statusSummary = isBootstrapping
    ? {
        aggregateStatus: "pending" as const,
        aggregateLabel: getTaskDisplayStatusSummary("pending").statusLabel,
      }
    : buildStaticAnalysisTaskStatusSummary({
        opengrepTask: input.opengrepTask,
        codeqlTask: input.codeqlTask,
      });
  const progressSummary = isBootstrapping
    ? { progressPercent: 0 }
    : buildStaticAnalysisProgressSummary({
        opengrepTask: input.opengrepTask,
        codeqlTask: input.codeqlTask,
        nowMs: input.nowMs,
      });
  const totalScanDurationMs = getStaticAnalysisTotalDisplayDurationMs({
    opengrepTask: input.opengrepTask,
    codeqlTask: input.codeqlTask,
    nowMs: input.nowMs,
  });
  const totalFindings =
    toStaticAnalysisSafeMetric(input.opengrepTask?.total_findings) +
    toStaticAnalysisSafeMetric(input.codeqlTask?.total_findings);
  const projectName =
    String(
      input.opengrepTask?.project_name ||
        input.codeqlTask?.project_name ||
        input.fallbackProjectName ||
        "-",
    ).trim() || "-";

  return {
    projectName,
    statusLabel: statusSummary.aggregateLabel,
    progressPercent: progressSummary.progressPercent,
    durationLabel: formatStaticAnalysisDuration(totalScanDurationMs),
    totalFindings,
    aggregateStatus: statusSummary.aggregateStatus,
  };
}

export function getStaticAnalysisOpengrepRuleName(
  finding: MinimalOpengrepFinding,
): string {
  const rule = (finding.rule || {}) as Record<string, unknown>;
  const byField = String(finding.rule_name || "").trim();
  if (byField) return formatStaticAnalysisOpengrepRuleName(byField);
  const byCheckId = String(rule.check_id || rule.id || "").trim();
  if (byCheckId) return formatStaticAnalysisOpengrepRuleName(byCheckId);
  return "-";
}

export function buildUnifiedFindingRows(input: {
  opengrepFindings: MinimalOpengrepFinding[];
  opengrepTaskId: string;
  codeqlFindings?: MinimalOpengrepFinding[];
  codeqlTaskId?: string;
}): UnifiedFindingRow[] {
  const buildRowsForEngine = (
    engine: "opengrep" | "codeql",
    findings: MinimalOpengrepFinding[],
    fallbackTaskId: string,
  ): UnifiedFindingRow[] => findings.flatMap((finding) => {
    const severity = normalizeStaticAnalysisSeverity(finding.severity);
    if (!severity) return [];
    const confidence = normalizeStaticAnalysisConfidence(finding.confidence);
    return {
      key: `${engine}:${finding.id}`,
      id: finding.id,
      taskId: finding.scan_task_id || fallbackTaskId,
      engine,
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
  return [
    ...buildRowsForEngine("opengrep", input.opengrepFindings, input.opengrepTaskId),
    ...buildRowsForEngine("codeql", input.codeqlFindings ?? [], input.codeqlTaskId ?? ""),
  ];
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
