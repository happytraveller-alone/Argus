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
  total_iterations?: number | null;
  tool_calls_count?: number | null;
  tokens_used?: number | null;
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
  filePath: string;
  line: number | null;
  location: string;
  raw: RealtimeFindingLike;
  stableKey: string;
}

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

function toPositiveNumberOrNull(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function hasDisplayableConfidence(item: RealtimeFindingLike): boolean {
  return typeof item.confidence === "number" && Number.isFinite(item.confidence);
}

export function isFalsePositiveFinding(item: RealtimeFindingLike): boolean {
  const status = String(item.status || "").trim().toLowerCase();
  const authenticity = String(item.authenticity || "").trim().toLowerCase();
  const detailMode = String(item.detailMode || "").trim().toLowerCase();
  const displaySeverity = String(item.display_severity || "").trim().toLowerCase();

  return (
    status === "false_positive" ||
    authenticity === "false_positive" ||
    detailMode === "false_positive_reason" ||
    displaySeverity === "invalid"
  );
}

export function isVerifiedFinding(item: RealtimeFindingLike): boolean {
  if (item.is_verified) return true;
  return String(item.verification_progress || "").trim().toLowerCase() === "verified";
}

export function isVisibleVerifiedVulnerability(item: RealtimeFindingLike): boolean {
  return (
    isVerifiedFinding(item) &&
    !isFalsePositiveFinding(item) &&
    hasDisplayableConfidence(item)
  );
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
  const verifiedTotal = displayFindings.length
    ? displayFindings.filter((item) => isVisibleVerifiedVulnerability(item)).length
    : Math.max(toFiniteNumber(task?.verified_count), 0);

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
    totalFindings: verifiedTotal,
    effectiveFindings: verifiedTotal,
    falsePositiveFindings: 0,
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
