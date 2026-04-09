import { normalizeReturnToPath } from "../../shared/utils/findingRoute";
import { getEstimatedTaskProgressPercent } from "../../features/tasks/services/taskProgress";
import { resolveCweDisplay } from "../../shared/security/cweCatalog";

export interface AgentAuditFindingFilters {
  keyword: string;
  severity: string;
}

export interface TokenUsageAccumulator {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  seenSequences: Set<number>;
}

export interface RealtimeFindingLike {
  id: string;
  title?: string | null;
  display_title?: string | null;
  vulnerability_type?: string | null;
  cwe_id?: string | null;
  severity?: string | null;
  display_severity?: string | null;
  verification_progress?: string | null;
  file_path?: string | null;
  line_start?: number | null;
  confidence?: number | null;
  is_verified?: boolean;
  fingerprint?: string | null;
  timestamp?: string | null;
  status?: string | null;
  verification_status?: string | null;
  verdict?: string | null;
  authenticity?: string | null;
  detailMode?: "detail" | "false_positive_reason" | null;
}

export interface TaskStatsLike {
  status?: string | null;
  created_at?: string | null;
  progress_percentage?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  findings_count?: number | null;
  verified_count?: number | null;
  false_positive_count?: number | null;
  critical_count?: number | null;
  high_count?: number | null;
  medium_count?: number | null;
  low_count?: number | null;
  verified_critical_count?: number | null;
  verified_high_count?: number | null;
  verified_medium_count?: number | null;
  verified_low_count?: number | null;
  defect_summary?: AgentAuditDefectSummaryLike | null;
  total_iterations?: number | null;
  tool_calls_count?: number | null;
  tokens_used?: number | null;
}

export interface AgentAuditDefectSummaryLike {
  scope?: "all_findings" | null;
  total_count?: number | null;
  severity_counts?: Partial<AgentAuditSeverityCounts> | null;
  status_counts?: Partial<AgentAuditStatusCounts> | null;
}

export interface AgentAuditStatusCounts {
  pending: number;
  verified: number;
  false_positive: number;
}

export interface AgentAuditSeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface AgentAuditVerifiedSeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface AgentAuditFindingSummary {
  totalCount: number;
  findingsCount: number;
  verifiedCount: number;
  falsePositiveCount: number;
  statusCounts: AgentAuditStatusCounts;
  severityCounts: AgentAuditSeverityCounts;
  effectiveSeverityCounts: AgentAuditSeverityCounts;
  verifiedSeverityCounts: AgentAuditVerifiedSeverityCounts;
}

export interface AgentAuditTaskFindingCountersPatch {
  findings_count: number;
  verified_count: number;
  false_positive_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  verified_critical_count: number;
  verified_high_count: number;
  verified_medium_count: number;
  verified_low_count: number;
  defect_summary: {
    scope: "all_findings";
    total_count: number;
    severity_counts: AgentAuditSeverityCounts;
    status_counts: AgentAuditStatusCounts;
  };
}

export interface AgentAuditStatsSummary {
  progressPercent: number;
  durationMs: number | null;
  totalFindings: number;
  effectiveFindings: number;
  falsePositiveFindings: number;
  iterations: number;
  toolCalls: number;
  tokensTotal: number;
  tokensInput: number | null;
  tokensOutput: number | null;
}

export const AGENT_AUDIT_FINDINGS_PAGE_SIZE = 3;
export const AGENT_AUDIT_FINDINGS_TABLE_HEADER_HEIGHT = 88;
export const AGENT_AUDIT_FINDINGS_TABLE_ROW_HEIGHT = 56;
export const AGENT_AUDIT_FINDINGS_PAGE_PARAM = "findingsPage";
export const AGENT_AUDIT_FINDINGS_PAGE_SIZE_PARAM = "findingsPageSize";

export interface AgentAuditPaginationState {
  page: number;
  pageSize: number;
}

export type AgentAuditPaginationSource = "user" | "layout";

function normalizeReturnToMode(returnTo: string | null | undefined): "intelligent" | "hybrid" | null {
  const normalized = String(returnTo || "").trim().toLowerCase();
  if (!normalized) return null;
  if (normalized.startsWith("/tasks/hybrid")) return "hybrid";
  if (normalized.startsWith("/tasks/intelligent")) return "intelligent";
  return null;
}

function normalizeTaskMetaMode(
  name: string | null | undefined,
  description: string | null | undefined,
): "intelligent" | "hybrid" {
  const normalized = `${String(name || "").trim().toLowerCase()} ${String(description || "")
    .trim()
    .toLowerCase()}`;
  if (normalized.includes("[hybrid]") || normalized.includes("混合扫描")) {
    return "hybrid";
  }
  if (normalized.includes("[intelligent]")) {
    return "intelligent";
  }
  return "intelligent";
}

export function resolveAgentAuditDetailTitle(input: {
  returnTo?: string | null;
  name?: string | null;
  description?: string | null;
}): string {
  const mode =
    normalizeReturnToMode(input.returnTo) ||
    normalizeTaskMetaMode(input.name, input.description);
  return mode === "hybrid" ? "混合扫描详情" : "智能扫描详情";
}

export function resolveAgentAuditBackTarget(
  returnTo: string | null | undefined,
  hasHistory: boolean,
): string | -1 {
  const normalized = normalizeReturnToPath(returnTo);
  if (normalized) {
    return normalized;
  }
  if (hasHistory) return -1;
  return "/dashboard";
}

export interface FindingTableRow {
  id: string;
  title: string;
  typeLabel: string;
  typeTooltip?: string | null;
  severity: string;
  severityLabel: string;
  severityScore: number;
  confidence: number | null;
  confidenceLabel: string | null;
  confidenceScore: number;
  statusValue: AgentAuditFindingDisplayStatus;
  statusLabel: string;
  statusClassName: string;
  filePath: string;
  line: number | null;
  location: string;
  raw: RealtimeFindingLike;
  stableKey: string;
}

export type AgentAuditFindingDisplayStatus =
  | "open"
  | "verified"
  | "false_positive";

export interface FindingTableState {
  allRows: RealtimeFindingLike[];
  filteredRows: FindingTableRow[];
  rows: FindingTableRow[];
  hasVisibleConfidence: boolean;
  totalRows: number;
  totalPages: number;
  page: number;
  pageStart: number;
}

export function calculateResponsiveFindingsPageSize(
  availableHeight: number,
): number {
  const normalizedHeight = Math.max(toFiniteNumber(availableHeight), 0);
  const rowsHeight = Math.max(
    normalizedHeight - AGENT_AUDIT_FINDINGS_TABLE_HEADER_HEIGHT,
    AGENT_AUDIT_FINDINGS_TABLE_ROW_HEIGHT,
  );
  return Math.max(
    1,
    Math.floor(rowsHeight / AGENT_AUDIT_FINDINGS_TABLE_ROW_HEIGHT),
  );
}

function toFiniteNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function createEmptyStatusCounts(): AgentAuditStatusCounts {
  return {
    pending: 0,
    verified: 0,
    false_positive: 0,
  };
}

function createEmptySeverityCounts(): AgentAuditSeverityCounts {
  return {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  };
}

function createEmptyVerifiedSeverityCounts(): AgentAuditVerifiedSeverityCounts {
  return {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };
}

function toPositiveNumberOrNull(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function toPositiveIntegerOrNull(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.floor(parsed);
}

export function readAgentAuditFindingsPagination(
  params: URLSearchParams,
): { page: number; pageSize: number } {
  return {
    page:
      toPositiveIntegerOrNull(params.get(AGENT_AUDIT_FINDINGS_PAGE_PARAM)) ?? 1,
    pageSize:
      toPositiveIntegerOrNull(
        params.get(AGENT_AUDIT_FINDINGS_PAGE_SIZE_PARAM),
      ) ?? AGENT_AUDIT_FINDINGS_PAGE_SIZE,
  };
}

export function resolveAgentAuditPaginationTransition(input: {
  current: AgentAuditPaginationState;
  update: Partial<AgentAuditPaginationState>;
  source: AgentAuditPaginationSource;
}): {
  state: AgentAuditPaginationState;
  routeSync: AgentAuditPaginationState | null;
} {
  const state = {
    page:
      toPositiveIntegerOrNull(input.update.page) ?? input.current.page,
    pageSize:
      toPositiveIntegerOrNull(input.update.pageSize) ??
      input.current.pageSize,
  };

  return {
    state,
    routeSync: input.source === "layout" ? null : state,
  };
}

export function writeAgentAuditFindingsPagination(
  params: URLSearchParams,
  pagination: { page: number; pageSize: number },
): URLSearchParams {
  const next = new URLSearchParams(params);
  const page = toPositiveIntegerOrNull(pagination.page) ?? 1;
  const pageSize =
    toPositiveIntegerOrNull(pagination.pageSize) ??
    AGENT_AUDIT_FINDINGS_PAGE_SIZE;

  if (page === 1) {
    next.delete(AGENT_AUDIT_FINDINGS_PAGE_PARAM);
  } else {
    next.set(AGENT_AUDIT_FINDINGS_PAGE_PARAM, String(page));
  }

  if (pageSize === AGENT_AUDIT_FINDINGS_PAGE_SIZE) {
    next.delete(AGENT_AUDIT_FINDINGS_PAGE_SIZE_PARAM);
  } else {
    next.set(AGENT_AUDIT_FINDINGS_PAGE_SIZE_PARAM, String(pageSize));
  }

  return next;
}

function hasDisplayableConfidence(item: RealtimeFindingLike): boolean {
  return typeof item.confidence === "number" && Number.isFinite(item.confidence);
}

function normalizeFindingStatusToken(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
}

export function isFalsePositiveFinding(item: RealtimeFindingLike): boolean {
  return normalizeFindingStatusToken(item.status) === "false_positive";
}

export function isVerifiedFinding(item: RealtimeFindingLike): boolean {
  return getAgentAuditFindingDisplayStatus(item) === "verified";
}

function normalizeSummarySeverity(
  item: RealtimeFindingLike,
): keyof AgentAuditSeverityCounts | null {
  const severity = String(item.severity || item.display_severity || "")
    .trim()
    .toLowerCase();
  if (
    severity === "critical" ||
    severity === "high" ||
    severity === "medium" ||
    severity === "low" ||
    severity === "info"
  ) {
    return severity;
  }
  return null;
}

export function summarizeAgentAuditFindings(
  findings: RealtimeFindingLike[],
): AgentAuditFindingSummary {
  const statusCounts = createEmptyStatusCounts();
  const severityCounts = createEmptySeverityCounts();
  const effectiveSeverityCounts = createEmptySeverityCounts();
  const verifiedSeverityCounts = createEmptyVerifiedSeverityCounts();

  for (const finding of findings) {
    const severity = normalizeSummarySeverity(finding);
    const falsePositive = isFalsePositiveFinding(finding);
    const verified = !falsePositive && isVerifiedFinding(finding);

    if (severity) {
      severityCounts[severity] += 1;
      if (!falsePositive) {
        effectiveSeverityCounts[severity] += 1;
      }
      if (
        verified &&
        (severity === "critical" ||
          severity === "high" ||
          severity === "medium" ||
          severity === "low")
      ) {
        verifiedSeverityCounts[severity] += 1;
      }
    }

    if (falsePositive) {
      statusCounts.false_positive += 1;
    } else if (verified) {
      statusCounts.verified += 1;
    } else {
      statusCounts.pending += 1;
    }
  }

  return {
    totalCount: findings.length,
    findingsCount: statusCounts.pending + statusCounts.verified,
    verifiedCount: statusCounts.verified,
    falsePositiveCount: statusCounts.false_positive,
    statusCounts,
    severityCounts,
    effectiveSeverityCounts,
    verifiedSeverityCounts,
  };
}

export function buildAgentAuditTaskFindingCountersPatch(input: {
  task: TaskStatsLike | null | undefined;
  findings: RealtimeFindingLike[];
}): AgentAuditTaskFindingCountersPatch {
  const { task, findings } = input;
  const summary = summarizeAgentAuditFindings(findings);

  return {
    findings_count: summary.findingsCount,
    verified_count: summary.verifiedCount,
    false_positive_count: summary.falsePositiveCount,
    critical_count: summary.effectiveSeverityCounts.critical,
    high_count: summary.effectiveSeverityCounts.high,
    medium_count: summary.effectiveSeverityCounts.medium,
    low_count: summary.effectiveSeverityCounts.low,
    verified_critical_count: summary.verifiedSeverityCounts.critical,
    verified_high_count: summary.verifiedSeverityCounts.high,
    verified_medium_count: summary.verifiedSeverityCounts.medium,
    verified_low_count: summary.verifiedSeverityCounts.low,
    defect_summary: {
      scope: task?.defect_summary?.scope === "all_findings" ? "all_findings" : "all_findings",
      total_count: summary.totalCount,
      severity_counts: summary.severityCounts,
      status_counts: summary.statusCounts,
    },
  };
}

export function isVisibleVerifiedVulnerability(item: RealtimeFindingLike): boolean {
  return (
    isVerifiedFinding(item) &&
    !isFalsePositiveFinding(item) &&
    hasDisplayableConfidence(item)
  );
}

export function isVisibleManagedFinding(item: RealtimeFindingLike): boolean {
  return !isFalsePositiveFinding(item);
}

export function getAgentAuditFindingDisplayStatus(
  item: RealtimeFindingLike,
): AgentAuditFindingDisplayStatus {
  const status = normalizeFindingStatusToken(item.status);
  if (status === "false_positive") return "false_positive";
  if (status === "verified") return "verified";
  return "open";
}

export function getAgentAuditFindingStatusLabel(
  status: AgentAuditFindingDisplayStatus,
): string {
  if (status === "verified") return "确报";
  if (status === "false_positive") return "误报";
  return "待确认";
}

export function getAgentAuditFindingStatusBadgeClass(
  status: AgentAuditFindingDisplayStatus,
): string {
  if (status === "verified") {
    return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
  }
  if (status === "false_positive") {
    return "border-rose-500/30 bg-rose-500/15 text-rose-300";
  }
  return "border-border bg-muted text-muted-foreground";
}

function normalizeSeverityKey(item: RealtimeFindingLike): string {
  const display = String(item.display_severity || "").trim().toLowerCase();
  if (display) return display;
  return String(item.severity || "").trim().toLowerCase();
}

const SEVERITY_SCORE: Record<string, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  info: 1,
  invalid: 0,
};

export function createTokenUsageAccumulator(): TokenUsageAccumulator {
  return {
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    seenSequences: new Set<number>(),
  };
}

export function accumulateTokenUsage(
  state: TokenUsageAccumulator,
  event: {
    event_type?: string | null;
    type?: string | null;
    sequence?: number | null;
    metadata?: Record<string, unknown> | null;
  },
): TokenUsageAccumulator {
  const eventType = String(event.event_type || event.type || "").trim().toLowerCase();
  const sequence = Number(event.sequence);
  if (eventType !== "llm_call_complete" || !Number.isFinite(sequence)) {
    return state;
  }
  if (state.seenSequences.has(sequence)) {
    return state;
  }

  const inputTokens = toFiniteNumber(event.metadata?.tokens_input);
  const outputTokens = toFiniteNumber(event.metadata?.tokens_output);
  const nextSeen = new Set(state.seenSequences);
  nextSeen.add(sequence);
  return {
    inputTokens: state.inputTokens + inputTokens,
    outputTokens: state.outputTokens + outputTokens,
    totalTokens: state.totalTokens + inputTokens + outputTokens,
    seenSequences: nextSeen,
  };
}

export function buildStatsSummary(input: {
  task: TaskStatsLike | null;
  displayFindings: RealtimeFindingLike[];
  tokenUsage: TokenUsageAccumulator;
  now: Date;
}): AgentAuditStatsSummary {
  const { task, displayFindings, tokenUsage, now } = input;
  const managedFindings = displayFindings.filter((item) =>
    isVisibleManagedFinding(item),
  );
  const totalFindings = managedFindings.length
    ? managedFindings.length
    : Math.max(toFiniteNumber(task?.findings_count), 0);
  const falsePositiveFindings = displayFindings.length
    ? displayFindings.filter((item) => isFalsePositiveFinding(item)).length
    : Math.max(toFiniteNumber(task?.false_positive_count), 0);

  const startedAt = task?.started_at ? new Date(task.started_at).getTime() : Number.NaN;
  const completedAt = task?.completed_at ? new Date(task.completed_at).getTime() : Number.NaN;
  let durationMs: number | null = null;
  if (Number.isFinite(startedAt)) {
    const endMs = Number.isFinite(completedAt) ? completedAt : now.getTime();
    const delta = endMs - startedAt;
    durationMs = Number.isFinite(delta) && delta >= 0 ? delta : null;
  }

  const tokensInput = Math.max(toFiniteNumber(tokenUsage.inputTokens), 0);
  const tokensOutput = Math.max(toFiniteNumber(tokenUsage.outputTokens), 0);
  const hasTokenBreakdown =
    tokenUsage.seenSequences.size > 0 || tokensInput > 0 || tokensOutput > 0;
  const tokensTotal = hasTokenBreakdown
    ? tokensInput + tokensOutput
    : Math.max(toFiniteNumber(task?.tokens_used), 0);

  return {
    progressPercent: getEstimatedTaskProgressPercent(
      {
        status: task?.status,
        createdAt: task?.created_at || task?.started_at || null,
        startedAt: task?.started_at,
      },
      now.getTime(),
    ),
    durationMs,
    totalFindings,
    effectiveFindings: totalFindings,
    falsePositiveFindings,
    iterations: Math.max(toFiniteNumber(task?.total_iterations), 0),
    toolCalls: Math.max(toFiniteNumber(task?.tool_calls_count), 0),
    tokensTotal,
    tokensInput: hasTokenBreakdown ? tokensInput : null,
    tokensOutput: hasTokenBreakdown ? tokensOutput : null,
  };
}

export function shouldResetFindingPage(
  previous: AgentAuditFindingFilters,
  next: AgentAuditFindingFilters,
): boolean {
  return previous.keyword !== next.keyword || previous.severity !== next.severity;
}

export function shouldSyncFindingPageFromTableState(input: {
  requestedPage: number;
  resolvedPage: number;
  totalRows: number;
  isLoading: boolean;
}): boolean {
  const requestedPage = Math.max(Math.floor(toFiniteNumber(input.requestedPage) || 1), 1);
  const resolvedPage = Math.max(Math.floor(toFiniteNumber(input.resolvedPage) || 1), 1);
  if (requestedPage === resolvedPage) return false;
  if (input.isLoading && Math.max(toFiniteNumber(input.totalRows), 0) === 0) {
    return false;
  }
  return true;
}

function getSeverityLabel(key: string): string {
  if (key === "critical") return "严重";
  if (key === "high") return "高危";
  if (key === "medium") return "中危";
  if (key === "low") return "低危";
  if (key === "invalid") return "无效";
  return "提示";
}

function getConfidenceScore(confidence: number | null): number {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) return 0;
  return confidence;
}

function getConfidenceLabel(
  confidence: number | null,
): string | null {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) return null;
  if (confidence >= 0.85) return "高";
  if (confidence >= 0.5) return "中";
  return "低";
}

function getTypeDisplay(item: RealtimeFindingLike): {
  label: string;
  tooltip: string | null;
} {
  const cweDisplay = resolveCweDisplay({
    cwe: item.cwe_id,
    fallbackLabel: String(item.vulnerability_type || "").trim(),
  });
  if (cweDisplay.label && cweDisplay.label !== "-") {
    return {
      label: cweDisplay.label,
      tooltip: cweDisplay.tooltip,
    };
  }

  const vulnerabilityType = String(item.vulnerability_type || "").trim();
  if (vulnerabilityType) {
    return {
      label: vulnerabilityType,
      tooltip: null,
    };
  }
  return {
    label: String(item.display_title || item.title || "未命名漏洞").trim(),
    tooltip: null,
  };
}

function getLocation(item: RealtimeFindingLike): string {
  const path = String(item.file_path || "").trim();
  const line = toPositiveNumberOrNull(item.line_start);
  if (!path) return "-";
  if (line) return `${path}:${line}`;
  return path;
}

function buildFindingRow(item: RealtimeFindingLike): FindingTableRow {
  const severity = normalizeSeverityKey(item) || "info";
  const confidence =
    typeof item.confidence === "number" && Number.isFinite(item.confidence)
      ? item.confidence
      : null;
  const statusValue = getAgentAuditFindingDisplayStatus(item);
  const filePath = String(item.file_path || "").trim() || "-";
  const line = toPositiveNumberOrNull(item.line_start);
  const title = String(item.display_title || item.title || "未命名漏洞").trim() || "未命名漏洞";
  const typeDisplay = getTypeDisplay(item);
  return {
    id: item.id,
    title,
    typeLabel: typeDisplay.label,
    typeTooltip: typeDisplay.tooltip,
    severity,
    severityLabel: getSeverityLabel(severity),
    severityScore: SEVERITY_SCORE[severity] ?? 0,
    confidence,
    confidenceLabel: getConfidenceLabel(confidence),
    confidenceScore: getConfidenceScore(confidence),
    statusValue,
    statusLabel: getAgentAuditFindingStatusLabel(statusValue),
    statusClassName: getAgentAuditFindingStatusBadgeClass(statusValue),
    filePath,
    line,
    location: getLocation(item),
    raw: item,
    stableKey: String(item.fingerprint || item.id || title),
  };
}

export function buildFindingTableState(input: {
  items: RealtimeFindingLike[];
  filters: AgentAuditFindingFilters;
  page: number;
  pageSize?: number;
}): FindingTableState {
  const pageSize = Math.max(toFiniteNumber(input.pageSize) || 10, 1);
  const keyword = input.filters.keyword.trim().toLowerCase();
  const severityFilter = String(input.filters.severity || "all").trim().toLowerCase();

  const filteredRows = input.items
    .map((item) => buildFindingRow(item))
    .filter((row) => {
      const matchedKeyword =
        !keyword ||
        row.typeLabel.toLowerCase().includes(keyword) ||
        String(row.typeTooltip || "").toLowerCase().includes(keyword) ||
        String(row.raw.cwe_id || "").toLowerCase().includes(keyword) ||
        String(row.raw.vulnerability_type || "").toLowerCase().includes(keyword) ||
        row.severityLabel.toLowerCase().includes(keyword) ||
        String(row.confidenceLabel || "").toLowerCase().includes(keyword);
      const matchedSeverity = severityFilter === "all" || row.severity === severityFilter;
      return matchedKeyword && matchedSeverity;
    })
    .sort((left, right) => {
      if (left.severityScore !== right.severityScore) {
        return right.severityScore - left.severityScore;
      }
      if (left.confidenceScore !== right.confidenceScore) {
        return right.confidenceScore - left.confidenceScore;
      }
      const pathCompare = left.filePath.localeCompare(right.filePath);
      if (pathCompare !== 0) return pathCompare;
      const leftLine = left.line ?? Number.MAX_SAFE_INTEGER;
      const rightLine = right.line ?? Number.MAX_SAFE_INTEGER;
      if (leftLine !== rightLine) return leftLine - rightLine;
      return left.stableKey.localeCompare(right.stableKey);
    });

  const totalRows = filteredRows.length;
  const hasVisibleConfidence = filteredRows.some((row) => Boolean(row.confidenceLabel));
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const requestedPage = Math.max(Math.floor(toFiniteNumber(input.page) || 1), 1);
  const page = Math.min(requestedPage, totalPages);
  const pageStart = (page - 1) * pageSize;

  return {
    allRows: input.items,
    filteredRows,
    rows: filteredRows.slice(pageStart, pageStart + pageSize),
    hasVisibleConfidence,
    totalRows,
    totalPages,
    page,
    pageStart,
  };
}

export function formatDurationMs(durationMs: number | null): string {
  if (!Number.isFinite(durationMs) || durationMs === null || durationMs < 0) return "-";
  if (durationMs < 1000) return `${Math.round(durationMs)} ms`;
  const totalSeconds = Math.floor(durationMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function formatTokenValue(tokens: number | null): string {
  if (!Number.isFinite(tokens) || tokens === null) return "-";
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`;
  return `${Math.round(tokens)}`;
}
