/**
 * Agent Audit Page - Modular Implementation
 * Main entry point for the Agent Audit feature
 * Cassette Futurism / Terminal Retro aesthetic
 */

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Terminal,
  Bot,
  Layers,
  Zap,
  Loader2,
  ArrowDown,
  ArrowRight,
  Download,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { useAgentStream } from "@/hooks/useAgentStream";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";
import type { StreamErrorContext } from "@/shared/api/agentStream";
import {
  getAgentTask,
  getAgentFindings,
  cancelAgentTask,
  getAgentTree,
  getAgentEvents,
  AgentEvent,
} from "@/shared/api/agentTasks";
import {
  getOpengrepScanFindings,
  type OpengrepFinding,
} from "@/shared/api/opengrep";
import CreateAgentTaskDialog from "@/components/agent/CreateAgentTaskDialog";
import CreateProjectAuditDialog from "@/components/audit/CreateProjectAuditDialog";

// Local imports
import {
  Header,
  LogEntry,
  StatsPanel,
  AuditDetailDialog,
  AgentErrorBoundary,
  RealtimeFindingsPanel,
} from "./components";
import ReportExportDialog from "./components/ReportExportDialog";
import { useAgentAuditState } from "./hooks";
import { POLLING_INTERVALS, TASK_PHASE_LABELS } from "./constants";
import {
  cleanThinkingContent,
  getTimeString,
  resolveLogDisplayTime,
  sanitizeAuditText,
} from "./utils";
import {
  fromAgentEvent as agentEventToRealtimeItem,
  fromAgentFinding as agentFindingToRealtimeItem,
} from "./realtimeFindingMapper";
import {
  localizeAuditText,
  normalizeSeverityKey,
  toZhAgentName,
} from "./localization";
import type {
  BootstrapInputsSummary,
  DetailViewState,
  FindingsViewFilters,
  LateToolCallPolicy,
  LogItem,
  TerminalFailureClass,
  TerminalRecoveryState,
} from "./types";

import type { RealtimeMergedFindingItem } from "./components/RealtimeFindingsPanel";

const EVENT_PAGE_SIZE = 500;
const EVENT_BATCH_SAFETY_LIMIT = 200;
const FINDINGS_REFRESH_INTERVAL = 10000;
const BOOTSTRAP_FINDING_PAGE_SIZE = 200;
const AUTO_SCROLL_BY_PROJECT_STORAGE_KEY = "agentAudit.autoScrollByProject.v1";
const EVENT_DEDUP_WINDOW_SIZE = 5000;
const TERMINAL_RECOVERY_MAX_ATTEMPTS = 2;
const TERMINAL_RECOVERY_RETRY_INTERVAL_MS = 1500;
const TERMINAL_RECOVERY_DEBOUNCE_MS = 30_000;
const STREAM_SELF_HEAL_RETRY_MS = 4000;
const LOG_DEFAULT_VISIBLE_COUNT = 3;
const LOG_VIEWPORT_HEIGHT_PX = 200;
const LOG_AUTO_SCROLL_NEAR_BOTTOM_THRESHOLD_PX = 24;

const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "aborted",
  "interrupted",
]);

const PROGRESS_PATTERNS: { pattern: RegExp; key: string }[] = [
  { pattern: /索引进度[:：]?\s*\d+\/\d+/, key: "index_progress" },
  { pattern: /克隆进度[:：]?\s*\d+%/, key: "clone_progress" },
  { pattern: /下载进度[:：]?\s*\d+%/, key: "download_progress" },
  { pattern: /上传进度[:：]?\s*\d+%/, key: "upload_progress" },
  { pattern: /扫描进度[:：]?\s*\d+/, key: "scan_progress" },
  { pattern: /分析进度[:：]?\s*\d+/, key: "analyze_progress" },
];

const LOG_TYPE_LABELS: Record<string, string> = {
  thinking: "思考",
  tool: "工具",
  phase: "阶段",
  finding: "漏洞",
  dispatch: "调度",
  info: "信息",
  error: "错误",
  user: "用户",
  progress: "进度",
};

type HomeScanCard = {
  key: "static" | "agent" | "hybrid";
  title: string;
  intro: string;
  strengths: string;
  limitations: string;
  quickStartHint: string;
  icon: typeof Zap;
  accentClassName: string;
};

type AutoScrollByProjectState = Record<string, boolean>;

function loadAutoScrollByProjectState(): AutoScrollByProjectState {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(AUTO_SCROLL_BY_PROJECT_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const normalized: AutoScrollByProjectState = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === "boolean" && key.trim()) {
        normalized[key] = value;
      }
    }
    return normalized;
  } catch {
    return {};
  }
}

function getPersistedAutoScroll(projectId: string): boolean {
  const state = loadAutoScrollByProjectState();
  if (Object.prototype.hasOwnProperty.call(state, projectId)) {
    return state[projectId];
  }
  return true;
}

function persistAutoScroll(projectId: string, enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    const state = loadAutoScrollByProjectState();
    state[projectId] = enabled;
    window.localStorage.setItem(
      AUTO_SCROLL_BY_PROJECT_STORAGE_KEY,
      JSON.stringify(state),
    );
  } catch {
    // ignore storage errors to avoid blocking runtime behavior
  }
}

type UnifiedAgentEvent = {
  type?: string;
  event_type?: string;
  timestamp?: string | null;
  message?: string | null;
  metadata?: Record<string, unknown> | null;
  sequence?: number;
  status?: string;
  tool_name?: string | null;
  tool_input?: unknown;
  tool_output?: unknown;
  tool_duration_ms?: number | null;
  error?: string | null;
};

function matchProgressKey(message: string): string | null {
  const matched = PROGRESS_PATTERNS.find((item) => item.pattern.test(message));
  return matched?.key ?? null;
}

function eventToString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function extractToolOutputText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null) {
    const data = value as Record<string, unknown>;
    const resultValue = data.result;
    if (typeof resultValue === "string") {
      return resultValue;
    }
  }
  return eventToString(value);
}

function toNonEmptyId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function extractToolCallId(
  metadata: Record<string, unknown> | undefined,
  event?: UnifiedAgentEvent,
): string | null {
  const eventRecord = event as Record<string, unknown> | undefined;
  const toolRecord =
    eventRecord && typeof eventRecord.tool === "object" && eventRecord.tool !== null
      ? (eventRecord.tool as Record<string, unknown>)
      : undefined;
  return (
    toNonEmptyId(metadata?.tool_call_id) ||
    toNonEmptyId(eventRecord?.tool_call_id) ||
    toNonEmptyId(toolRecord?.call_id) ||
    toNonEmptyId(toolRecord?.id)
  );
}

function buildToolBucketKey(agentRawName: string | undefined, agentName: string | undefined, toolName: string): string {
  const owner = String(agentRawName || agentName || "unknown").trim().toLowerCase() || "unknown";
  const tool = String(toolName || "unknown").trim().toLowerCase() || "unknown";
  return `${owner}|${tool}`;
}

function extractEventTimestamp(
  event: UnifiedAgentEvent,
  metadata?: Record<string, unknown>,
): string | null {
  const eventRecord = event as Record<string, unknown>;
  const timestampCandidates: unknown[] = [
    eventRecord.timestamp,
    metadata?.timestamp,
  ];
  for (const candidate of timestampCandidates) {
    if (typeof candidate !== "string") continue;
    const trimmed = candidate.trim();
    if (!trimmed) continue;
    const ts = new Date(trimmed).getTime();
    if (Number.isFinite(ts)) {
      return trimmed;
    }
  }
  return null;
}

function getMcpRouteLabel(metadata?: Record<string, unknown>): string {
  const adapter = toSafeTrimmedString(metadata?.mcp_adapter);
  const mcpTool = toSafeTrimmedString(metadata?.mcp_tool);
  if (!adapter || !mcpTool) return "";
  const domain = toSafeTrimmedString(metadata?.mcp_runtime_domain);
  return domain ? `${adapter}/${mcpTool}@${domain}` : `${adapter}/${mcpTool}`;
}

function buildToolTitle(statusLabel: string, toolName: string, metadata?: Record<string, unknown>): string {
  const routeLabel = getMcpRouteLabel(metadata);
  return routeLabel
    ? `${statusLabel}：${toolName}（MCP: ${routeLabel}）`
    : `${statusLabel}：${toolName}`;
}

function buildToolRouteContentPrefix(metadata?: Record<string, unknown>): string {
  const routeLabel = getMcpRouteLabel(metadata);
  return routeLabel ? `MCP 路由：${routeLabel}` : "";
}

function buildEventDedupKey(
  eventType: string,
  sequence: number | undefined,
  toolCallId: string | null,
  message: string,
): string {
  if (typeof sequence === "number" && Number.isFinite(sequence)) {
    return `seq:${sequence}`;
  }
  const source = `${eventType}|${toolCallId || "none"}|${message}`;
  let hash = 0;
  for (let i = 0; i < source.length; i += 1) {
    hash = (hash * 31 + source.charCodeAt(i)) >>> 0;
  }
  return `fallback:${eventType}:${toolCallId || "none"}:${hash.toString(16)}`;
}

function sanitizeAuditValue(value: unknown): unknown {
  if (typeof value === "string") {
    return sanitizeAuditText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeAuditValue(item));
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      output[key] = sanitizeAuditValue(item);
    }
    return output;
  }
  return value;
}

function extractStepName(message: string): string | null {
  const matched = message.trim().match(/^\[([A-Z0-9_]+)\]/);
  return matched?.[1] ?? null;
}

function normalizeToolStatus(
  statusValue: unknown,
  fallbackEventType: string,
): "completed" | "failed" | "cancelled" {
  const normalized = String(statusValue || "").trim().toLowerCase();
  if (normalized === "failed" || normalized === "error") {
    return "failed";
  }
  if (normalized === "cancelled" || normalized === "canceled" || normalized === "aborted") {
    return "cancelled";
  }
  if (fallbackEventType === "tool_call_error") {
    return "failed";
  }
  return "completed";
}

function toCnVerificationStatus(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "verified") return "已验证";
  if (normalized === "running") return "验证中";
  if (normalized === "pending") return "待验证";
  if (normalized === "false_positive") return "假阳性";
  return normalized || "未知状态";
}

function classifyTerminalFailure(
  reasonText: string,
  metadata?: Record<string, unknown>,
  userCancelled = false,
): { failureClass: TerminalFailureClass; retryable: boolean; cancelOrigin: "user" | "system" | "none" } {
  const retryClass = String(metadata?.retry_error_class || "").trim().toLowerCase();
  const retryableFromMetadata =
    typeof metadata?.retryable === "boolean" ? Boolean(metadata.retryable) : null;
  const cancelOriginRaw = String(metadata?.cancel_origin || "").trim().toLowerCase();
  const cancelOrigin: "user" | "system" | "none" =
    cancelOriginRaw === "user"
      ? "user"
      : cancelOriginRaw === "system"
        ? "system"
        : userCancelled
          ? "user"
          : "none";
  const reason = String(reasonText || "").trim().toLowerCase();

  if (cancelOrigin === "user" || retryClass === "cancelled_user") {
    return { failureClass: "cancelled_user", retryable: false, cancelOrigin: "user" };
  }
  if (retryClass === "cancelled_system") {
    return { failureClass: "cancelled_system", retryable: true, cancelOrigin: "system" };
  }
  if (retryClass === "timeout_error" || /timeout|超时/.test(reason)) {
    return {
      failureClass: "timeout",
      retryable: retryableFromMetadata ?? true,
      cancelOrigin,
    };
  }
  if (retryClass === "mcp_runtime_error" || /mcp|adapter|command_not_found/.test(reason)) {
    return {
      failureClass: "mcp",
      retryable: retryableFromMetadata ?? true,
      cancelOrigin,
    };
  }
  if (retryClass === "network_transient_error" || /network|connection|dns|503|502|429/.test(reason)) {
    return {
      failureClass: "network",
      retryable: retryableFromMetadata ?? true,
      cancelOrigin,
    };
  }
  if (retryClass === "repairable_validation_error" || /参数校验失败|缺少|missing required|required field/.test(reason)) {
    return {
      failureClass: "validation_repairable",
      retryable: retryableFromMetadata ?? true,
      cancelOrigin,
    };
  }
  if (retryClass === "schema_hard_error") {
    return { failureClass: "non_retryable", retryable: false, cancelOrigin };
  }
  if (typeof retryableFromMetadata === "boolean") {
    return {
      failureClass: retryableFromMetadata ? "unknown" : "non_retryable",
      retryable: retryableFromMetadata,
      cancelOrigin,
    };
  }
  return { failureClass: "unknown", retryable: false, cancelOrigin };
}

function toSafeFilename(value: string): string {
  const text = String(value || "").trim();
  if (!text) return "task";
  return text.replace(/[^\w.-]+/g, "_").slice(0, 60) || "task";
}

function downloadTextFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function toSafeNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toSafeTrimmedString(value: unknown): string {
  return String(value ?? "").trim();
}

function resolveRealtimeFindingMergeKey(
  item: RealtimeMergedFindingItem | null | undefined,
): string {
  if (!item) return "";
  const mergeKey = toSafeTrimmedString(item.merge_key);
  if (mergeKey) return mergeKey;
  return toSafeTrimmedString(item.fingerprint);
}

function pickNewerIsoTimestamp(
  a: string | null | undefined,
  b: string | null | undefined,
): string | null {
  const left = typeof a === "string" ? a : "";
  const right = typeof b === "string" ? b : "";
  if (!left && !right) return null;
  if (!left) return right || null;
  if (!right) return left || null;
  return right.localeCompare(left) > 0 ? right : left;
}

function mergeRealtimeFindingsBatch(
  prev: RealtimeMergedFindingItem[],
  incoming: RealtimeMergedFindingItem[],
  options: { source: "db" | "event" },
): RealtimeMergedFindingItem[] {
  if (!incoming.length) return prev;

  const byMergeKey = new Map<string, RealtimeMergedFindingItem>();
  for (const item of prev) {
    const key = resolveRealtimeFindingMergeKey(item);
    if (!key) continue;
    if (!byMergeKey.has(key)) {
      byMergeKey.set(key, item);
    }
  }

  for (const item of incoming) {
    const mergeKey = resolveRealtimeFindingMergeKey(item);
    if (!mergeKey) continue;
    const existing = byMergeKey.get(mergeKey);
    if (!existing) {
      byMergeKey.set(mergeKey, item);
      continue;
    }

    const preferIncoming = options.source === "db";
    const verificationProgress =
      existing.verification_progress === "verified" ||
      item.verification_progress === "verified"
        ? "verified"
        : "pending";
    const displaySeverity =
      existing.display_severity === "invalid" || item.display_severity === "invalid"
        ? "invalid"
        : preferIncoming
          ? (item.display_severity || existing.display_severity)
          : (existing.display_severity || item.display_severity);
    const merged: RealtimeMergedFindingItem = {
      ...existing,
      merge_key: preferIncoming
        ? (item.merge_key || existing.merge_key || mergeKey)
        : (existing.merge_key || item.merge_key || mergeKey),
      // Prefer DB fields; event backfill only fills blanks.
      id: preferIncoming ? (item.id || existing.id) : (existing.id || item.id),
      fingerprint: preferIncoming
        ? (item.fingerprint || existing.fingerprint)
        : (existing.fingerprint || item.fingerprint),
      title: preferIncoming
        ? (item.title || existing.title)
        : (existing.title || item.title),
      severity: preferIncoming
        ? (item.severity || existing.severity)
        : (existing.severity || item.severity),
      display_severity: displaySeverity,
      verification_progress: verificationProgress,
      vulnerability_type: preferIncoming
        ? (item.vulnerability_type || existing.vulnerability_type)
        : (existing.vulnerability_type || item.vulnerability_type),
      display_title: preferIncoming
        ? (item.display_title ?? existing.display_title)
        : (existing.display_title ?? item.display_title),
      description: preferIncoming
        ? (item.description ?? existing.description)
        : (existing.description ?? item.description),
      description_markdown: preferIncoming
        ? (item.description_markdown ?? existing.description_markdown)
        : (existing.description_markdown ?? item.description_markdown),
      file_path: preferIncoming
        ? (item.file_path ?? existing.file_path)
        : (existing.file_path ?? item.file_path),
      line_start: preferIncoming
        ? (item.line_start ?? existing.line_start)
        : (existing.line_start ?? item.line_start),
      line_end: preferIncoming
        ? (item.line_end ?? existing.line_end)
        : (existing.line_end ?? item.line_end),
      cwe_id: preferIncoming
        ? (item.cwe_id ?? existing.cwe_id)
        : (existing.cwe_id ?? item.cwe_id),
      code_snippet: preferIncoming
        ? (item.code_snippet ?? existing.code_snippet)
        : (existing.code_snippet ?? item.code_snippet),
      code_context: preferIncoming
        ? (item.code_context ?? existing.code_context)
        : (existing.code_context ?? item.code_context),
      function_trigger_flow: preferIncoming
        ? (item.function_trigger_flow ?? existing.function_trigger_flow)
        : (existing.function_trigger_flow ?? item.function_trigger_flow),
      verification_evidence: preferIncoming
        ? (item.verification_evidence ?? existing.verification_evidence)
        : (existing.verification_evidence ?? item.verification_evidence),
      reachability_file: preferIncoming
        ? (item.reachability_file ?? existing.reachability_file)
        : (existing.reachability_file ?? item.reachability_file),
      reachability_function: preferIncoming
        ? (item.reachability_function ?? existing.reachability_function)
        : (existing.reachability_function ?? item.reachability_function),
      reachability_function_start_line: preferIncoming
        ? (item.reachability_function_start_line ?? existing.reachability_function_start_line)
        : (existing.reachability_function_start_line ?? item.reachability_function_start_line),
      reachability_function_end_line: preferIncoming
        ? (item.reachability_function_end_line ?? existing.reachability_function_end_line)
        : (existing.reachability_function_end_line ?? item.reachability_function_end_line),
      context_start_line: preferIncoming
        ? (item.context_start_line ?? existing.context_start_line)
        : (existing.context_start_line ?? item.context_start_line),
      context_end_line: preferIncoming
        ? (item.context_end_line ?? existing.context_end_line)
        : (existing.context_end_line ?? item.context_end_line),
      timestamp: pickNewerIsoTimestamp(existing.timestamp, item.timestamp),
      is_verified: verificationProgress === "verified",
    };

    byMergeKey.set(mergeKey, merged);
  }

  const merged = Array.from(byMergeKey.values());
  merged.sort((a, b) =>
    String(b.timestamp || "").localeCompare(String(a.timestamp || "")),
  );
  return merged.slice(0, 500);
}

function AgentAuditPageContent() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    task,
    findings,
    logs,
    isLoading,
    isAutoScroll,
    treeNodes,
    filteredLogs,
    isRunning,
    setTask,
    setFindings,
    setAgentTree,
    updateLog,
    removeLog,
    selectAgent,
    setLoading,
    setAutoScroll,
    setCurrentAgentName,
    getCurrentAgentName,
    setCurrentThinkingId,
    getCurrentThinkingId,
    dispatch,
    reset,
  } = useAgentAuditState();

  // Local state
  const [showSplash, setShowSplash] = useState(!taskId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showHomeStaticDialog, setShowHomeStaticDialog] = useState(false);
  const [showHomeAgentDialog, setShowHomeAgentDialog] = useState(false);
  const [showHomeMixedDialog, setShowHomeMixedDialog] = useState(false);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [activeMainTab, setActiveMainTab] = useState<"logs" | "findings">(
    "logs",
  );
  const [, setIsFindingsLoading] = useState(false);
  const [, setFindingsError] = useState<string | null>(null);
  const [findingsFilters, setFindingsFilters] = useState<FindingsViewFilters>({
    keyword: "",
    severity: "all",
    verification: "all",
    showFiltered: false,
  });
  // NOTE: bootstrap (opengrep) input UI is currently not shown in the new realtime layout,
  // but we keep the plumbing in place for future toggles.
  const [bootstrapInputsSummary, setBootstrapInputsSummary] =
    useState<BootstrapInputsSummary | null>(null);
  const [bootstrapInputFindings, setBootstrapInputFindings] = useState<
    OpengrepFinding[]
  >([]);
  const [bootstrapInputsLoading, setBootstrapInputsLoading] = useState(false);
  const [bootstrapInputsError, setBootstrapInputsError] = useState<string | null>(
    null,
  );
  const [detailViewState, setDetailViewState] = useState<DetailViewState | null>(null);
  const [detailDialog, setDetailDialog] = useState<{
    type: "log" | "finding" | "agent";
    id: string;
  } | null>(null);
  const [terminalFailureReason, setTerminalFailureReason] = useState<string | null>(null);
  const [highlightedLogId, setHighlightedLogId] = useState<string | null>(null);
  const [, setHighlightedFindingId] = useState<string | null>(null);
  const [, setHighlightedAgentId] = useState<string | null>(null);

  // Realtime panels state
  const [realtimeFindings, setRealtimeFindings] = useState<RealtimeMergedFindingItem[]>([]);
  const verifiedFindingsManuallyClearedRef = useRef(false);

  const logEndRef = useRef<HTMLDivElement>(null);
  const logsContainerRef = useRef<HTMLDivElement | null>(null);
  const hasInitializedLogViewportRef = useRef(false);
  const findingsContainerRef = useRef<HTMLDivElement | null>(null);
  const agentContainerRef = useRef<HTMLDivElement | null>(null);
  const logsRef = useRef(logs);
  const toolLogIdByCallIdRef = useRef<Map<string, string>>(new Map());
  const pendingToolBucketsRef = useRef<Map<string, string[]>>(new Map());
  const agentTreeRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const lastAgentTreeRefreshTime = useRef<number>(0);
  const previousTaskIdRef = useRef<string | undefined>(undefined);
  const disconnectStreamRef = useRef<(() => void) | null>(null);
  const lastEventSequenceRef = useRef<number>(0);
  const seenEventKeysRef = useRef<Set<string>>(new Set());
  const seenEventOrderRef = useRef<string[]>([]);
  const hasConnectedRef = useRef<boolean>(false); // 🔥 追踪是否已连接 SSE
  const hasLoadedHistoricalEventsRef = useRef<boolean>(false); // 🔥 追踪是否已加载历史事件
  const isBackfillingRef = useRef(false);
  const previousTaskStatusRef = useRef<string | undefined>(undefined);
  const taskStatusRef = useRef<string | undefined>(undefined);
  const terminalBoundarySequenceRef = useRef<number | null>(null);
  const taskStartedAtRef = useRef<string | null>(null);
  const userCancelSeenRef = useRef(false);
  const lastStreamSelfHealAttemptRef = useRef(0);
  const terminalRecoveryStateRef = useRef<TerminalRecoveryState>({
    active: false,
    attempts: 0,
    reasonKey: "",
    triggeredAt: 0,
  });
  const runTerminalRecoveryRef = useRef<
    ((triggerReason: string, metadata?: Record<string, unknown>) => void) | null
  >(null);
  // 🔥 使用 state 来标记历史事件加载状态和触发 streamOptions 重新计算
  const [afterSequence, setAfterSequence] = useState<number>(0);
  const [historicalEventsLoaded, setHistoricalEventsLoaded] =
    useState<boolean>(false);
  const { logoSrc, cycleLogoVariant } = useLogoVariant();
  const effectiveFindingsCount = useMemo(
    () =>
      findings.filter(
        (item) =>
          item.status !== "false_positive" &&
          item.authenticity !== "false_positive",
      ).length,
    [findings],
  );
  const selectedLogItem = useMemo(
    () =>
      detailDialog?.type === "log"
        ? logs.find((item) => item.id === detailDialog.id) || null
        : null,
    [detailDialog, logs],
  );
  const selectedFinding = useMemo(
    () =>
      detailDialog?.type === "finding"
        ? findings.find((item) => item.id === detailDialog.id) || null
        : null,
    [detailDialog, findings],
  );
  const selectedAgentNode = useMemo(
    () =>
      detailDialog?.type === "agent"
        ? treeNodes.find((item) => item.agent_id === detailDialog.id) || null
        : null,
    [detailDialog, treeNodes],
  );
  const failedReason = useMemo(() => {
    if (task?.status !== "failed") return null;
    const reason = terminalFailureReason || task.error_message || "";
    const normalized = reason.trim();
    return normalized || "任务执行失败";
  }, [task?.status, task?.error_message, terminalFailureReason]);
  const failedStep = useMemo(
    () => (failedReason ? extractStepName(failedReason) : null),
    [failedReason],
  );
  const openHomeModeDialog = useCallback((mode: HomeScanCard["key"]) => {
    setShowHomeStaticDialog(mode === "static");
    setShowHomeAgentDialog(mode === "agent");
    setShowHomeMixedDialog(mode === "hybrid");
  }, []);
  const homeScanCards: HomeScanCard[] = useMemo(
    () => [
      {
        key: "static",
        title: "静态扫描",
        intro: "简介：严重规则快速定位缺陷",
        strengths: "优势：速度快、结果稳定",
        limitations: "劣势：复杂语义覆盖有限",
        quickStartHint: "点击卡片，快速开始静态审计",
        icon: Zap,
        accentClassName:
          "from-sky-500/25 via-cyan-500/10 to-transparent border-sky-400/40",
      },
      {
        key: "agent",
        title: "智能扫描",
        intro: "简介：智能体上下文推理审计",
        strengths: "优势：可发现规则外风险",
        limitations: "劣势：耗时更长、资源更高",
        quickStartHint: "点击卡片，快速开始智能扫描（可先配置测试 LLM）",
        icon: Bot,
        accentClassName:
          "from-violet-500/25 via-indigo-500/10 to-transparent border-violet-400/40",
      },
      {
        key: "hybrid",
        title: "混合扫描",
        intro: "简介：静态 + 智能完整双阶段链路",
        strengths: "优势：覆盖更全面",
        limitations: "劣势：执行耗时更长",
        quickStartHint: "点击卡片，快速开始混合扫描（可先配置测试 LLM）",
        icon: Layers,
        accentClassName:
          "from-emerald-500/25 via-cyan-500/10 to-transparent border-emerald-400/40",
      },
    ],
    [],
  );
  const currentProjectId = useMemo(() => {
    const value = typeof task?.project_id === "string" ? task.project_id.trim() : "";
    return value || null;
  }, [task?.project_id]);
  const currentPhaseLabel = useMemo(() => {
    const phaseKey = String(task?.current_phase || "")
      .trim()
      .toLowerCase();
    if (phaseKey && TASK_PHASE_LABELS[phaseKey]) {
      return TASK_PHASE_LABELS[phaseKey];
    }
    if (task?.status === "completed") return "完成";
    if (task?.status === "failed") return "失败";
    if (task?.status === "cancelled") return "已取消";
    return null;
  }, [task?.current_phase, task?.status]);
  const phaseHint = useMemo(() => {
    const currentStep = String(task?.current_step || "").trim();
    if (currentStep) return currentStep;
    if (!isRunning) return null;
    if (currentPhaseLabel) return `当前阶段：${currentPhaseLabel}`;
    return null;
  }, [task?.current_step, isRunning, currentPhaseLabel]);
  const setDetailQuery = useCallback(
    (nextDetail: { type: "log" | "finding" | "agent"; id: string } | null) => {
      const params = new URLSearchParams(location.search);
      if (nextDetail) {
        params.set("detailType", nextDetail.type);
        params.set("detailId", nextDetail.id);
      } else {
        params.delete("detailType");
        params.delete("detailId");
      }
      const search = params.toString();
      navigate(
        {
          pathname: location.pathname,
          search: search ? `?${search}` : "",
        },
        { replace: true },
      );
    },
    [location.pathname, location.search, navigate],
  );

  const clearHighlights = useCallback(() => {
    setHighlightedLogId(null);
    setHighlightedFindingId(null);
    setHighlightedAgentId(null);
  }, []);

  const restoreAndScrollToAnchor = useCallback(
    (state: DetailViewState | null) => {
      if (!state) return;
      // Legacy: preserve stored tab state, but current UI is split into realtime+right-panel.
      setActiveMainTab(state.activeTab);
      setFindingsFilters(state.filters);
      selectAgent(null);

      requestAnimationFrame(() => {
        if (logsContainerRef.current) {
          logsContainerRef.current.scrollTop = state.logsScrollTop;
        }
        if (findingsContainerRef.current) {
          findingsContainerRef.current.scrollTop = state.findingsScrollTop;
        }
        if (agentContainerRef.current) {
          agentContainerRef.current.scrollTop = state.agentScrollTop;
        }

        clearHighlights();
        if (state.detailType === "log") {
          setHighlightedLogId(state.detailId);
        } else if (state.detailType === "finding") {
          setHighlightedFindingId(state.detailId);
        } else if (state.detailType === "agent") {
          setHighlightedAgentId(state.detailId);
        }

        const anchor = document.getElementById(state.anchorId);
        anchor?.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => clearHighlights(), 1800);
      });
    },
    [clearHighlights, selectAgent],
  );

  const openDetailDialog = useCallback(
    (detail: { type: "log" | "finding" | "agent"; id: string; anchorId: string }) => {
      setDetailViewState({
        detailType: detail.type,
        detailId: detail.id,
        anchorId: detail.anchorId,
        activeTab: activeMainTab,
        logsScrollTop: logsContainerRef.current?.scrollTop ?? 0,
        findingsScrollTop: findingsContainerRef.current?.scrollTop ?? 0,
        agentScrollTop: agentContainerRef.current?.scrollTop ?? 0,
        filters: findingsFilters,
      });
      setDetailDialog({
        type: detail.type,
        id: detail.id,
      });
      setDetailQuery({ type: detail.type, id: detail.id });
    },
    [activeMainTab, findingsFilters, setDetailQuery],
  );

  const handleDetailBack = useCallback(() => {
    if (!detailDialog) return;
    setDetailDialog(null);
    setDetailQuery(null);
    restoreAndScrollToAnchor(detailViewState);
    setDetailViewState(null);
  }, [detailDialog, detailViewState, restoreAndScrollToAnchor, setDetailQuery]);

  const handleBack = useCallback(() => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate("/dashboard");
  }, [navigate]);

  useEffect(() => {
    logsRef.current = logs;
  }, [logs]);

  useEffect(() => {
    taskStatusRef.current = task?.status;
  }, [task?.status]);

  const markTerminalBoundary = useCallback(
    (status: string, sequence?: number) => {
      const normalizedStatus = String(status || "").trim().toLowerCase();
      if (!TERMINAL_STATUSES.has(normalizedStatus)) return;
      taskStatusRef.current = normalizedStatus;
      if (typeof sequence === "number") {
        const current = terminalBoundarySequenceRef.current;
        terminalBoundarySequenceRef.current =
          typeof current === "number" ? Math.max(current, sequence) : sequence;
      }
    },
    [],
  );

  useEffect(() => {
    const startedAt = typeof task?.started_at === "string" ? task.started_at.trim() : "";
    taskStartedAtRef.current = startedAt || null;
  }, [task?.started_at]);

  useEffect(() => {
    const startedAt = taskStartedAtRef.current;
    if (!startedAt || !logsRef.current.length) return;

    let changed = false;
    const nextLogs = logsRef.current.map((item) => {
      const eventTimestamp =
        typeof item.eventTimestamp === "string" ? item.eventTimestamp.trim() : "";
      if (!eventTimestamp) return item;
      const nextTime = resolveLogDisplayTime(startedAt, eventTimestamp, item.time);
      if (nextTime === item.time) return item;
      changed = true;
      return {
        ...item,
        time: nextTime,
      };
    });

    if (changed) {
      logsRef.current = nextLogs;
      dispatch({ type: "SET_LOGS", payload: nextLogs });
    }
  }, [dispatch, task?.started_at]);

  useEffect(() => {
    if (!currentProjectId) return;
    setAutoScroll(getPersistedAutoScroll(currentProjectId));
  }, [currentProjectId, setAutoScroll]);

  // 🔥 当 taskId 变化时立即重置状态（新建任务时清理旧日志）
  useEffect(() => {
    // 如果 taskId 发生变化，立即重置
    if (taskId !== previousTaskIdRef.current) {
      // 1. 先断开旧的 SSE 流连接
      if (disconnectStreamRef.current) {
        disconnectStreamRef.current();
        disconnectStreamRef.current = null;
      }
      // 2. 重置所有状态
      reset();
      setShowSplash(!taskId);
      hasInitializedLogViewportRef.current = false;

      // 2.1 重置 realtime 面板
      setRealtimeFindings([]);
      verifiedFindingsManuallyClearedRef.current = false;
      // 3. 重置事件序列号和加载状态
      lastEventSequenceRef.current = 0;
      hasConnectedRef.current = false; // 🔥 重置 SSE 连接标志
      hasLoadedHistoricalEventsRef.current = false; // 🔥 重置历史事件加载标志
      isBackfillingRef.current = false;
      previousTaskStatusRef.current = undefined;
      setHistoricalEventsLoaded(false); // 🔥 重置历史事件加载状态
      setAfterSequence(0); // 🔥 重置 afterSequence state
      setActiveMainTab("logs");
      setFindingsError(null);
      setIsFindingsLoading(false);
      setFindingsFilters({
        keyword: "",
        severity: "all",
        verification: "all",
        showFiltered: false,
      });
      setBootstrapInputsSummary(null);
      setBootstrapInputFindings([]);
      setBootstrapInputsLoading(false);
      setBootstrapInputsError(null);
      setDetailViewState(null);
      setDetailDialog(null);
      setHighlightedLogId(null);
      setHighlightedFindingId(null);
      setHighlightedAgentId(null);
      setTerminalFailureReason(null);
      toolLogIdByCallIdRef.current.clear();
      pendingToolBucketsRef.current.clear();
      seenEventKeysRef.current.clear();
      seenEventOrderRef.current = [];
      userCancelSeenRef.current = false;
      lastStreamSelfHealAttemptRef.current = 0;
      terminalRecoveryStateRef.current = {
        active: false,
        attempts: 0,
        reasonKey: "",
        triggeredAt: 0,
      };
      terminalBoundarySequenceRef.current = null;
    }
    previousTaskIdRef.current = taskId;
  }, [taskId, reset]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const detailType = params.get("detailType");
    const detailId = params.get("detailId");
    if (!detailType || !detailId) return;
    if (detailDialog?.type === detailType && detailDialog?.id === detailId) return;
    if (detailType === "log") {
      if (logs.some((item) => item.id === detailId)) {
        setDetailDialog({ type: "log", id: detailId });
      }
      return;
    }
    if (detailType === "finding") {
      if (findings.some((item) => item.id === detailId)) {
        setDetailDialog({ type: "finding", id: detailId });
      }
      return;
    }
    if (detailType === "agent") {
      if (treeNodes.some((item) => item.agent_id === detailId)) {
        setDetailDialog({ type: "agent", id: detailId });
      }
    }
  }, [detailDialog?.id, detailDialog?.type, findings, location.search, logs, treeNodes]);

  // ============ Data Loading ============

  const loadTask = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await getAgentTask(taskId);
      setTask(data);
      if (data.status === "failed" && typeof data.error_message === "string") {
        const message = data.error_message.trim();
        if (message) {
          setTerminalFailureReason(message);
        }
      }
    } catch {
      toast.error("加载任务失败");
    }
  }, [taskId, setTask]);

  const loadFindings = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!taskId) return;
      const silent = options?.silent ?? false;
      if (!silent) {
        setIsFindingsLoading(true);
      }
      setFindingsError(null);
      try {
        const data = await getAgentFindings(taskId, {
          include_false_positive: true,
        });
        setFindings(data);
      } catch (err) {
        console.error(err);
        const message = err instanceof Error ? err.message : "加载审计结果失败";
        setFindingsError(message);
      } finally {
        if (!silent) {
          setIsFindingsLoading(false);
        }
      }
    },
    [taskId, setFindings],
  );

  const loadBootstrapInputFindings = useCallback(async (scanTaskId: string) => {
    setBootstrapInputsLoading(true);
    setBootstrapInputsError(null);
    try {
      const allFindings: OpengrepFinding[] = [];
      let skip = 0;
      for (let batch = 0; batch < EVENT_BATCH_SAFETY_LIMIT; batch += 1) {
        const page = await getOpengrepScanFindings({
          taskId: scanTaskId,
          skip,
          limit: BOOTSTRAP_FINDING_PAGE_SIZE,
        });
        if (!page.length) break;
        allFindings.push(...page);
        skip += page.length;
        if (page.length < BOOTSTRAP_FINDING_PAGE_SIZE) break;
      }

      const filtered = allFindings.filter((item) => {
        const severity = String(item.severity || "").trim().toUpperCase();
        const confidence = String(item.confidence || "").trim().toUpperCase();
        return (
          severity === "ERROR" && (confidence === "HIGH" || confidence === "MEDIUM")
        );
      });

      setBootstrapInputFindings(filtered);
      setBootstrapInputsSummary((prev) =>
        prev && prev.taskId === scanTaskId
          ? {
            ...prev,
            candidateCount: Math.max(prev.candidateCount, filtered.length),
            totalFindings: Math.max(prev.totalFindings, allFindings.length),
          }
          : prev,
      );
    } catch (error) {
      console.error("Failed to load bootstrap input findings:", error);
      setBootstrapInputsError("加载静态输入失败");
      setBootstrapInputFindings([]);
    } finally {
      setBootstrapInputsLoading(false);
    }
  }, []);

  const loadAgentTree = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await getAgentTree(taskId);
      setAgentTree(data);
    } catch (err) {
      console.error(err);
    }
  }, [taskId, setAgentTree]);

  const debouncedLoadAgentTree = useCallback(() => {
    const now = Date.now();
    const minInterval = POLLING_INTERVALS.AGENT_TREE_DEBOUNCE;

    if (agentTreeRefreshTimer.current) {
      clearTimeout(agentTreeRefreshTimer.current);
    }

    const timeSinceLastRefresh = now - lastAgentTreeRefreshTime.current;
    if (timeSinceLastRefresh < minInterval) {
      agentTreeRefreshTimer.current = setTimeout(() => {
        lastAgentTreeRefreshTime.current = Date.now();
        loadAgentTree();
      }, minInterval - timeSinceLastRefresh);
    } else {
      agentTreeRefreshTimer.current = setTimeout(() => {
        lastAgentTreeRefreshTime.current = Date.now();
        loadAgentTree();
      }, POLLING_INTERVALS.AGENT_TREE_MIN_DELAY);
    }
  }, [loadAgentTree]);

  const fetchAllHistoricalEvents = useCallback(
    async (targetTaskId: string, startAfter = 0): Promise<AgentEvent[]> => {
      let afterSequenceCursor = startAfter;
      const allEvents: AgentEvent[] = [];

      for (let batch = 0; batch < EVENT_BATCH_SAFETY_LIMIT; batch += 1) {
        const page = await getAgentEvents(targetTaskId, {
          after_sequence: afterSequenceCursor,
          limit: EVENT_PAGE_SIZE,
        });
        if (!page.length) {
          break;
        }
        page.sort((a, b) => a.sequence - b.sequence);
        allEvents.push(...page);
        afterSequenceCursor = page[page.length - 1].sequence;

        if (page.length < EVENT_PAGE_SIZE) {
          break;
        }
      }

      return allEvents;
    },
    [],
  );

  const reconcileTerminalLogs = useCallback(
    (finalStatus: string, terminalSequence?: number) => {
      const normalized = String(finalStatus || "").trim().toLowerCase();
      if (!TERMINAL_STATUSES.has(normalized)) {
        return;
      }

      const nextToolStatus: "completed" | "failed" | "cancelled" =
        normalized === "completed"
          ? "completed"
          : normalized === "failed"
            ? "failed"
            : "cancelled";
      const nextToolLabel =
        nextToolStatus === "completed"
          ? "已完成"
          : nextToolStatus === "failed"
            ? "失败"
            : "已取消";

      let changed = false;
      const reconciled = logsRef.current.map((item) => {
        let nextItem: LogItem = item;
        if (item.type === "tool" && item.tool?.status === "running") {
          const title =
            item.title.startsWith("运行中：") && item.tool?.name
              ? `${nextToolLabel}：${item.tool.name}`
              : item.title;
          nextItem = {
            ...item,
            title,
            tool: {
              ...item.tool,
              status: nextToolStatus,
            },
            detail: {
              ...(item.detail || {}),
              terminal_reconciled: true,
              terminal_status: normalized,
              terminal_sequence:
                typeof terminalSequence === "number" ? terminalSequence : undefined,
            },
          };
          changed = true;
        } else if (
          item.type === "progress" &&
          item.progressStatus === "running"
        ) {
          nextItem = {
            ...item,
            progressStatus: "completed",
            detail: {
              ...(item.detail || {}),
              terminal_reconciled: true,
              terminal_status: normalized,
              terminal_sequence:
                typeof terminalSequence === "number" ? terminalSequence : undefined,
            },
          };
          changed = true;
        }
        return nextItem;
      });

      if (changed) {
        logsRef.current = reconciled;
        dispatch({ type: "SET_LOGS", payload: reconciled });
      }
    },
    [dispatch],
  );

  const compactToolLogsAfterReplay = useCallback(() => {
    const currentLogs = logsRef.current;
    if (!currentLogs.length) return;

    const terminalByCallId = new Map<string, { id: string; sequence: number }>();
    const terminalByBucket = new Map<string, number>();
    const getSequence = (item: LogItem): number => {
      const seq = toSafeNumber(item.detail?.sequence);
      return seq ?? -1;
    };

    for (const item of currentLogs) {
      if (item.type !== "tool") continue;
      const toolStatus = item.tool?.status;
      const toolName = String(item.tool?.name || "").trim();
      if (!toolName) continue;
      const callId =
        toNonEmptyId(item.tool?.callId) ||
        toNonEmptyId((item.detail?.metadata as Record<string, unknown> | undefined)?.tool_call_id);
      const bucketKey = buildToolBucketKey(item.agentRawName, item.agentName, toolName);
      const sequence = getSequence(item);
      const isTerminal = toolStatus === "completed" || toolStatus === "failed" || toolStatus === "cancelled";
      if (!isTerminal) continue;

      if (callId) {
        const previous = terminalByCallId.get(callId);
        if (!previous || sequence >= previous.sequence) {
          terminalByCallId.set(callId, { id: item.id, sequence });
        }
      }
      const previousBucketSeq = terminalByBucket.get(bucketKey);
      if (previousBucketSeq === undefined || sequence >= previousBucketSeq) {
        terminalByBucket.set(bucketKey, sequence);
      }
    }

    const compacted: LogItem[] = [];
    let changed = false;
    for (const item of currentLogs) {
      if (item.type !== "tool") {
        compacted.push(item);
        continue;
      }
      const toolName = String(item.tool?.name || "").trim();
      const toolStatus = item.tool?.status;
      const sequence = getSequence(item);
      const callId =
        toNonEmptyId(item.tool?.callId) ||
        toNonEmptyId((item.detail?.metadata as Record<string, unknown> | undefined)?.tool_call_id);
      const bucketKey = buildToolBucketKey(item.agentRawName, item.agentName, toolName);

      if (callId) {
        const terminal = terminalByCallId.get(callId);
        if (terminal) {
          if (toolStatus === "running") {
            changed = true;
            continue;
          }
          const isTerminal = toolStatus === "completed" || toolStatus === "failed" || toolStatus === "cancelled";
          if (isTerminal && item.id !== terminal.id) {
            changed = true;
            continue;
          }
        }
      } else if (toolStatus === "running") {
        const bucketTerminalSeq = terminalByBucket.get(bucketKey);
        if (bucketTerminalSeq !== undefined && sequence <= bucketTerminalSeq) {
          changed = true;
          continue;
        }
      }

      compacted.push(item);
    }

    const rebuiltCallIdMap = new Map<string, string>();
    const rebuiltPendingBuckets = new Map<string, string[]>();
    for (const item of compacted) {
      if (item.type !== "tool") continue;
      const toolName = String(item.tool?.name || "").trim();
      const callId =
        toNonEmptyId(item.tool?.callId) ||
        toNonEmptyId((item.detail?.metadata as Record<string, unknown> | undefined)?.tool_call_id);
      if (callId) {
        rebuiltCallIdMap.set(callId, item.id);
      } else if (toolName && item.tool?.status === "running") {
        const bucket = buildToolBucketKey(item.agentRawName, item.agentName, toolName);
        const queue = rebuiltPendingBuckets.get(bucket) ?? [];
        queue.push(item.id);
        rebuiltPendingBuckets.set(bucket, queue);
      }
    }
    toolLogIdByCallIdRef.current = rebuiltCallIdMap;
    pendingToolBucketsRef.current = rebuiltPendingBuckets;

    if (changed) {
      logsRef.current = compacted;
      dispatch({ type: "SET_LOGS", payload: compacted });
    }
  }, [dispatch]);

  const appendLogFromEvent = useCallback(
    (event: UnifiedAgentEvent) => {
      const eventType = String(
        event.event_type ?? event.type ?? "",
      ).toLowerCase();
      const rawMessage = eventToString(event.message).trim();
      const message = sanitizeAuditText(rawMessage);
      const metadata = (event.metadata ?? undefined) as Record<string, unknown> | undefined;
      const eventKey = buildEventDedupKey(
        eventType,
        event.sequence,
        extractToolCallId(metadata, event),
        message,
      );
      if (seenEventKeysRef.current.has(eventKey)) {
        return;
      }
      seenEventKeysRef.current.add(eventKey);
      seenEventOrderRef.current.push(eventKey);
      if (seenEventOrderRef.current.length > EVENT_DEDUP_WINDOW_SIZE) {
        const expired = seenEventOrderRef.current.shift();
        if (expired) {
          seenEventKeysRef.current.delete(expired);
        }
      }

      const sanitizedMetadata = sanitizeAuditValue(metadata ?? {}) as Record<string, unknown>;
      const eventTimestamp = extractEventTimestamp(event, metadata);
      const displayTime = resolveLogDisplayTime(
        taskStartedAtRef.current,
        eventTimestamp,
        getTimeString(),
      );
      const agentRawName =
        (typeof metadata?.agent_name === "string" && metadata.agent_name) ||
        (typeof metadata?.agent === "string" && metadata.agent) ||
        undefined;
      const agentName =
        typeof agentRawName === "string" && agentRawName.trim()
          ? toZhAgentName(agentRawName)
          : undefined;
      const baseDetail = {
        event_type: eventType,
        message,
        metadata: sanitizedMetadata,
        sequence: event.sequence ?? null,
        status: event.status ?? null,
        tool_name:
          typeof event.tool_name === "string"
            ? sanitizeAuditText(event.tool_name)
            : event.tool_name ?? null,
        tool_input: sanitizeAuditValue(event.tool_input ?? null),
        tool_output: sanitizeAuditValue(event.tool_output ?? null),
        tool_duration_ms: event.tool_duration_ms ?? null,
        event_timestamp: eventTimestamp,
      };
      const bootstrapTaskId =
        typeof metadata?.bootstrap_task_id === "string"
          ? metadata.bootstrap_task_id.trim()
          : "";
      if (
        bootstrapTaskId &&
        (metadata?.bootstrap === true ||
          typeof metadata?.bootstrap_source === "string")
      ) {
        const totalFindings = toSafeNumber(metadata?.bootstrap_total_findings);
        const candidateCount = toSafeNumber(metadata?.bootstrap_candidate_count);
        const sourceValue =
          typeof metadata?.bootstrap_source === "string"
            ? metadata.bootstrap_source
            : "scan_forced";
        setBootstrapInputsSummary((prev) => ({
          taskId: bootstrapTaskId,
          source: sourceValue || prev?.source || "scan_forced",
          totalFindings: totalFindings ?? prev?.totalFindings ?? 0,
          candidateCount: candidateCount ?? prev?.candidateCount ?? 0,
        }));
      }

      if (typeof event.sequence === "number") {
        lastEventSequenceRef.current = Math.max(
          lastEventSequenceRef.current,
          event.sequence,
        );
      }

      if (eventType === "heartbeat") {
        return;
      }

      if (eventType === "llm_observation" && metadata?.deduped === true) {
        return;
      }

      if (
        eventType === "thinking_start" ||
        eventType === "thinking_end" ||
        eventType === "thinking_token"
      ) {
        return;
      }

      if (eventType.startsWith("llm_") || eventType === "thinking") {
        const thought =
          typeof metadata?.thought === "string"
            ? sanitizeAuditText(metadata.thought)
            : "";
        const content = thought || message || "";
        if (!content) {
          return;
        }
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "thinking",
            title:
              content.length > 100 ? `${content.slice(0, 100)}...` : content,
            content,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }

      if (eventType === "tool_call" || eventType === "tool_call_start") {
        const toolName = sanitizeAuditText(event.tool_name || "未知") || "未知";
        const runningTitle = buildToolTitle("运行中", toolName, metadata);
        const routePrefix = buildToolRouteContentPrefix(metadata);
        const boundarySequence = terminalBoundarySequenceRef.current;
        const isLateAfterTerminal =
          typeof boundarySequence === "number" &&
          (typeof event.sequence !== "number" || event.sequence > boundarySequence);
        if (isLateAfterTerminal) {
          const statusSnapshot = String(taskStatusRef.current || "").toLowerCase();
          const latePolicy: LateToolCallPolicy =
            statusSnapshot === "completed" ? "ignore" : "recovery";
          dispatch({
            type: "ADD_LOG",
            payload: {
              time: displayTime,
              eventTimestamp,
              type: "info",
              title:
                latePolicy === "ignore"
                  ? `终态后忽略迟到工具调用：${toolName}`
                  : `终态后收到迟到工具调用，触发恢复重试：${toolName}`,
              content: message || "",
              agentName,
              agentRawName: agentRawName || undefined,
              detail: baseDetail,
            },
          });
          if (latePolicy === "recovery") {
            runTerminalRecoveryRef.current?.("late_tool_call", metadata);
          }
          return;
        }
        const inputText = sanitizeAuditText(eventToString(event.tool_input));
        const runningContent = inputText
          ? `${routePrefix ? `${routePrefix}\n\n` : ""}输入：\n${inputText}`
          : routePrefix;
        const toolCallId = extractToolCallId(metadata, event);
        const bucketKey = buildToolBucketKey(agentRawName, agentName, toolName);
        const existingLogId = toolCallId
          ? toolLogIdByCallIdRef.current.get(toolCallId) ||
            logsRef.current.find((item) => item.id === `tool-${toolCallId}`)?.id ||
            logsRef.current.find((item) => {
              if (item.type !== "tool") return false;
              const metadataCallId = toNonEmptyId(
                (item.detail?.metadata as Record<string, unknown> | undefined)?.tool_call_id,
              );
              return metadataCallId === toolCallId;
            })?.id ||
            null
          : null;
        if (existingLogId) {
          updateLog(existingLogId, {
            time: displayTime,
            eventTimestamp,
            type: "tool",
            title: runningTitle,
            content: runningContent,
            tool: {
              name: toolName,
              status: "running",
              callId: toolCallId,
            },
            agentName,
            detail: baseDetail,
          });
          return;
        }

        const logId = toolCallId
          ? `tool-${toolCallId}`
          : `tool-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

        if (toolCallId) {
          toolLogIdByCallIdRef.current.set(toolCallId, logId);
        } else {
          const queue = pendingToolBucketsRef.current.get(bucketKey) ?? [];
          queue.push(logId);
          pendingToolBucketsRef.current.set(bucketKey, queue);
        }

        dispatch({
          type: "ADD_LOG",
          payload: {
            id: logId,
            time: displayTime,
            eventTimestamp,
            type: "tool",
            title: runningTitle,
            content: runningContent,
            tool: { name: toolName, status: "running", callId: toolCallId || undefined },
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }

      if (
        eventType === "tool_result" ||
        eventType === "tool_call_end" ||
        eventType === "tool_call_error"
      ) {
        const toolName = sanitizeAuditText(event.tool_name || "未知") || "未知";
        const toolStatus = normalizeToolStatus(
          metadata?.tool_status,
          eventType,
        );
        const statusSnapshot = String(taskStatusRef.current || "").toLowerCase();
        const boundarySequence = terminalBoundarySequenceRef.current;
        const isLateAfterTerminal =
          typeof boundarySequence === "number" &&
          (typeof event.sequence !== "number" || event.sequence > boundarySequence);
        if (
          isLateAfterTerminal &&
          TERMINAL_STATUSES.has(statusSnapshot) &&
          statusSnapshot !== "completed" &&
          toolStatus === "completed"
        ) {
          dispatch({
            type: "ADD_LOG",
            payload: {
              time: displayTime,
              eventTimestamp,
              type: "info",
              title: `终态后收到迟到工具结果，触发恢复重试：${toolName}`,
              content: message || "",
              agentName,
              agentRawName: agentRawName || undefined,
              detail: baseDetail,
            },
          });
          runTerminalRecoveryRef.current?.("late_tool_result", metadata);
        }
        const statusLabel =
          toolStatus === "completed"
            ? "已完成"
            : toolStatus === "failed"
              ? "失败"
              : "已取消";
        const resolvedToolTitle = buildToolTitle(statusLabel, toolName, metadata);
        const routePrefix = buildToolRouteContentPrefix(metadata);
        const outputText = sanitizeAuditText(extractToolOutputText(event.tool_output));
        const toolCallId = extractToolCallId(metadata, event);
        const writeScopeAllowed =
          typeof metadata?.write_scope_allowed === "boolean"
            ? (metadata.write_scope_allowed as boolean)
            : null;
        const writeScopeReason = toSafeTrimmedString(metadata?.write_scope_reason);
        const writeScopeFile = toSafeTrimmedString(metadata?.write_scope_file);
        const writeScopeTotal = toSafeNumber(metadata?.write_scope_total_files);
        const writeScopeHint =
          writeScopeAllowed === false
            ? `写入已拒绝（${writeScopeReason || "write_scope_not_allowed"}）` +
              (writeScopeFile ? ` 文件: ${writeScopeFile}` : "") +
              (writeScopeTotal !== null ? `，当前可写文件数: ${writeScopeTotal}` : "")
            : "";

        const bucketKey = buildToolBucketKey(agentRawName, agentName, toolName);
        let targetLogId: string | null = null;
        if (toolCallId) {
          targetLogId =
            toolLogIdByCallIdRef.current.get(toolCallId) ||
            logsRef.current.find((item) => item.id === `tool-${toolCallId}`)?.id ||
            logsRef.current.find((item) => {
              if (item.type !== "tool") return false;
              const metadataCallId = toNonEmptyId(
                (item.detail?.metadata as Record<string, unknown> | undefined)?.tool_call_id,
              );
              return metadataCallId === toolCallId;
            })?.id ||
            null;
        }
        if (!targetLogId && !toolCallId) {
          const queue = pendingToolBucketsRef.current.get(bucketKey) ?? [];
          while (queue.length > 0 && !targetLogId) {
            const candidate = queue.shift() ?? null;
            if (candidate && logsRef.current.some((item) => item.id === candidate)) {
              targetLogId = candidate;
            }
          }
          if (queue.length > 0) {
            pendingToolBucketsRef.current.set(bucketKey, queue);
          } else {
            pendingToolBucketsRef.current.delete(bucketKey);
          }
        }
        if (!targetLogId) {
          const fallbackLog = [...logsRef.current].reverse().find((item) => {
            if (item.type !== "tool" || item.tool?.status !== "running") return false;
            if (item.tool?.name !== toolName) return false;
            if (agentName && item.agentName && item.agentName !== agentName) return false;
            return true;
          });
          targetLogId = fallbackLog?.id || null;
        }
        if (targetLogId && !logsRef.current.some((item) => item.id === targetLogId)) {
          targetLogId = null;
        }

        if (targetLogId) {
          const existing = logsRef.current.find((item) => item.id === targetLogId);
          if (existing && existing.tool?.status === toolStatus && toolCallId) {
            return;
          }

          const previousContent = existing?.content ? `${existing.content}\n\n` : "";
          const outputBlock = outputText
            ? `${routePrefix ? `${routePrefix}\n\n` : ""}输出：\n${outputText}${writeScopeHint ? `\n\n${writeScopeHint}` : ""}`
            : `${routePrefix}${writeScopeHint ? `${routePrefix ? "\n\n" : ""}${writeScopeHint}` : ""}`.trim();
          updateLog(targetLogId, {
            time: displayTime,
            eventTimestamp,
            type: "tool",
            title: resolvedToolTitle,
            content: outputBlock
              ? `${previousContent}${outputBlock}`.trim()
              : previousContent.trim(),
            tool: {
              name: toolName,
              duration: event.tool_duration_ms ?? existing?.tool?.duration ?? 0,
              status: toolStatus,
              callId: toolCallId ?? existing?.tool?.callId,
            },
            agentName: agentName || existing?.agentName,
            detail: baseDetail,
          });
          if (toolCallId) {
            toolLogIdByCallIdRef.current.set(toolCallId, targetLogId);
          }
          return;
        }

        const logId = toolCallId
          ? `tool-${toolCallId}`
          : `tool-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        if (toolCallId) {
          toolLogIdByCallIdRef.current.set(toolCallId, logId);
        }
        dispatch({
          type: "ADD_LOG",
          payload: {
            id: logId,
            time: displayTime,
            eventTimestamp,
            type: "tool",
            title: resolvedToolTitle,
            content: outputText
              ? `${routePrefix ? `${routePrefix}\n\n` : ""}输出：\n${outputText}${writeScopeHint ? `\n\n${writeScopeHint}` : ""}`
              : `${routePrefix}${writeScopeHint ? `${routePrefix ? "\n\n" : ""}${writeScopeHint}` : ""}`.trim(),
            tool: {
              name: toolName,
              duration: event.tool_duration_ms ?? 0,
              status: toolStatus,
              callId: toolCallId || undefined,
            },
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }

      if (
        eventType === "finding" ||
        eventType === "finding_new" ||
        eventType === "finding_verified" ||
        eventType === "finding_update"
      ) {
        const normalizedEvent: AgentEvent = {
          id: toSafeTrimmedString(
            (event as Record<string, unknown>).id,
          ),
          sequence: Number(event.sequence || 0),
          task_id: "",
          event_type: eventType,
          phase: null,
          message: message || null,
          metadata: metadata || null,
          tool_name: null,
          tool_input: undefined,
          tool_output: undefined,
          tool_duration_ms: null,
          finding_id:
            toSafeTrimmedString((event as Record<string, unknown>).finding_id) ||
            null,
          tokens_used: null,
          timestamp: toSafeTrimmedString(event.timestamp) || "",
        };
        const mergedFindingItem = agentEventToRealtimeItem(normalizedEvent);
        if (mergedFindingItem) {
          setRealtimeFindings((prev) =>
            mergeRealtimeFindingsBatch(prev, [mergedFindingItem], {
              source: "event",
            }),
          );
        }

        const findingTitle =
          sanitizeAuditText(
            localizeAuditText(
              eventToString(metadata?.display_title) ||
              eventToString(metadata?.title) ||
              message ||
              "发现漏洞",
            ),
          ) || "发现漏洞";
        const falsePositiveSignal = [
          metadata?.status,
          metadata?.authenticity,
          metadata?.verdict,
        ].some((value) => String(value || "").trim().toLowerCase() === "false_positive");
        const findingSeverity = falsePositiveSignal
          ? "invalid"
          : normalizeSeverityKey(metadata?.severity);

        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "finding",
            title: findingTitle,
            severity: findingSeverity,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }

      if (eventType === "todo_update") {
        const todoScope = String(metadata?.todo_scope || "").trim().toLowerCase();
        const todoList = Array.isArray(metadata?.todo_list)
          ? (metadata?.todo_list as Array<Record<string, unknown>>)
          : [];

        if (todoScope === "verification") {
          const verifiedCount = todoList.filter((item) => item?.status === "verified").length;
          const pendingCount = todoList.filter(
            (item) => item?.status === "pending" || item?.status === "running",
          ).length;
          const falsePositiveCount = todoList.filter(
            (item) => item?.status === "false_positive",
          ).length;
          const statusPreview = todoList
            .slice(0, 3)
            .map((item) => toCnVerificationStatus(item?.status))
            .join(" / ");
          const compactProgress = `逐漏洞验证进度：已验证 ${verifiedCount}，待验证 ${pendingCount}，假阳性 ${falsePositiveCount}`;
          dispatch({
            type: "ADD_LOG",
            payload: {
              time: displayTime,
              eventTimestamp,
              type: "progress",
              title: compactProgress,
              content: `${message || ""}${statusPreview ? `\n状态样例：${statusPreview}` : ""}`,
              agentName,
              agentRawName: agentRawName || undefined,
              detail: baseDetail,
            },
          });
          return;
        }

        if (todoScope === "finding_table") {
          const contextPending = toSafeNumber(metadata?.context_pending) ?? 0;
          const contextReady = toSafeNumber(metadata?.context_ready) ?? 0;
          const contextFailed = toSafeNumber(metadata?.context_failed) ?? 0;
          const verifyUnverified = toSafeNumber(metadata?.verify_unverified) ?? 0;
          const verified = toSafeNumber(metadata?.verified) ?? 0;
          const falsePositive = toSafeNumber(metadata?.false_positive) ?? 0;
          const round = toSafeNumber(metadata?.round) ?? 0;
          const compactProgress =
            `缺陷表收敛进度（第 ${round} 轮）：` +
            `上下文待收集 ${contextPending}，已就绪 ${contextReady}，失败 ${contextFailed}；` +
            `待验证 ${verifyUnverified}，已验证 ${verified}，假阳性 ${falsePositive}`;
          dispatch({
            type: "ADD_LOG",
            payload: {
              time: displayTime,
              eventTimestamp,
              type: "progress",
              title: compactProgress,
              content: message || "",
              agentName,
              agentRawName: agentRawName || undefined,
              detail: baseDetail,
            },
          });
          return;
        }
      }

      if (
        eventType === "dispatch" ||
        eventType === "dispatch_complete" ||
        eventType === "node_start" ||
        eventType === "node_complete" ||
        eventType === "node_end" ||
        eventType === "phase_start" ||
        eventType === "phase_complete" ||
        eventType === "phase_end"
      ) {
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "dispatch",
            title: message || `事件：${eventType}`,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        debouncedLoadAgentTree();
        return;
      }

      if (eventType === "task_complete" || eventType === "complete") {
        markTerminalBoundary("completed", event.sequence);
        reconcileTerminalLogs("completed", event.sequence);
        compactToolLogsAfterReplay();
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "info",
            title: message || "任务已完成",
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }
      if (eventType === "task_error") {
        const taskErrorMessage =
          message ||
          sanitizeAuditText(eventToString(metadata?.error)) ||
          "任务执行出错";
        const cancelOrigin = String(metadata?.cancel_origin || "").trim().toLowerCase();
        if (cancelOrigin === "user") {
          userCancelSeenRef.current = true;
        }
        if (taskErrorMessage) {
          setTerminalFailureReason(taskErrorMessage);
        }
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "error",
            title: taskErrorMessage,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }
      if (eventType === "task_cancel") {
        userCancelSeenRef.current = true;
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "info",
            title: message || "任务已取消",
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }
      if (eventType === "task_end") {
        const terminalStatus = String(event.status || "").toLowerCase();
        if (TERMINAL_STATUSES.has(terminalStatus)) {
          markTerminalBoundary(terminalStatus, event.sequence);
          reconcileTerminalLogs(terminalStatus, event.sequence);
          compactToolLogsAfterReplay();
        }
        const status = event.status ? `（${event.status}）` : "";
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "info",
            title: message || `任务流已结束${status}`,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
      }

      if (
        eventType === "progress" ||
        eventType === "info" ||
        eventType === "warning" ||
        eventType === "error"
      ) {
        const fallback = message || eventType;
        const progressKey = matchProgressKey(fallback);
        if (progressKey) {
          dispatch({
            type: "UPDATE_OR_ADD_PROGRESS_LOG",
            payload: {
              progressKey,
              title: fallback,
              agentName,
              time: displayTime,
              eventTimestamp,
            },
          });
          return;
        }

        if (/索引.*完成/.test(fallback) || /index(?:ing)?\s+(?:complete|completed)/i.test(fallback)) {
          dispatch({
            type: "UPDATE_OR_ADD_PROGRESS_LOG",
            payload: {
              progressKey: "index_progress",
              title: fallback,
              agentName,
              progressStatus: "completed",
              time: displayTime,
              eventTimestamp,
            },
          });
          return;
        }

        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: eventType === "error" ? "error" : "info",
            title: fallback,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        if (
          eventType === "error" &&
          Boolean(metadata?.is_terminal) &&
          fallback
        ) {
          setTerminalFailureReason(fallback);
        }
        return;
      }

      if (message) {
        dispatch({
          type: "ADD_LOG",
          payload: {
            time: displayTime,
            eventTimestamp,
            type: "info",
            title: message,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
      }
    },
    [
      compactToolLogsAfterReplay,
      debouncedLoadAgentTree,
      dispatch,
      markTerminalBoundary,
      reconcileTerminalLogs,
      updateLog,
    ],
  );

  const buildNowRelativeLogTime = useCallback(() => {
    const nowIso = new Date().toISOString();
    return {
      time: resolveLogDisplayTime(
        taskStartedAtRef.current,
        nowIso,
        getTimeString(),
      ),
      eventTimestamp: nowIso,
    };
  }, []);

  const backfillEventsSince = useCallback(
    async (startAfter: number, reason: string) => {
      if (!taskId || isBackfillingRef.current) return;
      isBackfillingRef.current = true;
      try {
        const events = await fetchAllHistoricalEvents(taskId, startAfter);
        if (events.length === 0) {
          return;
        }

        if (!verifiedFindingsManuallyClearedRef.current) {
          const findingItems = events
            .map(agentEventToRealtimeItem)
            .filter((item): item is RealtimeMergedFindingItem => Boolean(item));
          if (findingItems.length) {
            setRealtimeFindings((prev) =>
              mergeRealtimeFindingsBatch(prev, findingItems, { source: "event" }),
            );
          }
        }
        events.forEach((event) => appendLogFromEvent(event));
        compactToolLogsAfterReplay();
        const lastSequence = events[events.length - 1]?.sequence ?? startAfter;
        lastEventSequenceRef.current = Math.max(
          lastEventSequenceRef.current,
          lastSequence,
        );
        setAfterSequence(lastEventSequenceRef.current);
        console.log(
          `[AgentAudit] Backfilled ${events.length} events (${reason}), last sequence=${lastEventSequenceRef.current}`,
        );
      } catch (error) {
        console.error("[AgentAudit] Backfill events failed:", error);
      } finally {
        isBackfillingRef.current = false;
      }
    },
    [appendLogFromEvent, compactToolLogsAfterReplay, fetchAllHistoricalEvents, taskId],
  );

  const runTerminalRecovery = useCallback(
    async (triggerReason: string, metadata?: Record<string, unknown>) => {
      if (!taskId) return;
      const terminalStatus = String(taskStatusRef.current || "").toLowerCase();
      if (terminalStatus !== "failed" && terminalStatus !== "cancelled") return;

      const recentTaskErrorLog = [...logsRef.current]
        .reverse()
        .find((item) => item.type === "error" || item.detail?.event_type === "task_error");
      const reasonText =
        terminalFailureReason ||
        String(recentTaskErrorLog?.title || "").trim() ||
        String(task?.error_message || "").trim();
      const classification = classifyTerminalFailure(
        reasonText,
        metadata,
        userCancelSeenRef.current,
      );
      if (classification.cancelOrigin === "user") {
        return;
      }
      if (!classification.retryable) {
        const nowTime = buildNowRelativeLogTime();
        dispatch({
          type: "ADD_LOG",
          payload: {
            ...nowTime,
            type: "info",
            title: `终态恢复跳过：失败分类=${classification.failureClass}，不满足自动重试条件`,
          },
        });
        return;
      }

      const now = Date.now();
      const reasonKey = `${taskId}:${classification.failureClass}:${classification.cancelOrigin}:${triggerReason}`;
      const currentState = terminalRecoveryStateRef.current;
      if (currentState.active) {
        return;
      }
      if (
        currentState.reasonKey === reasonKey &&
        now - currentState.triggeredAt < TERMINAL_RECOVERY_DEBOUNCE_MS
      ) {
        return;
      }

      terminalRecoveryStateRef.current = {
        active: true,
        attempts: 0,
        reasonKey,
        triggeredAt: now,
      };

      let recovered = false;
      let finalStatus = terminalStatus;
      try {
        for (let attempt = 1; attempt <= TERMINAL_RECOVERY_MAX_ATTEMPTS; attempt += 1) {
          terminalRecoveryStateRef.current = {
            ...terminalRecoveryStateRef.current,
            attempts: attempt,
          };
          const nowTime = buildNowRelativeLogTime();
          dispatch({
            type: "ADD_LOG",
            payload: {
              ...nowTime,
              type: "info",
              title: `终态恢复重试 ${attempt}/${TERMINAL_RECOVERY_MAX_ATTEMPTS}：原因=${reasonText || triggerReason}，分类=${classification.failureClass}`,
            },
          });

          await backfillEventsSince(
            lastEventSequenceRef.current,
            `terminal_recovery_retry_${attempt}`,
          );
          await loadTask();
          await loadFindings({ silent: true });

          try {
            const snapshot = await getAgentTask(taskId);
            setTask(snapshot);
            finalStatus = String(snapshot?.status || finalStatus).toLowerCase();
            if (finalStatus !== "failed" && finalStatus !== "cancelled") {
              recovered = true;
              break;
            }
          } catch {
            // keep retrying on snapshot fetch errors within budget
          }
          if (attempt < TERMINAL_RECOVERY_MAX_ATTEMPTS) {
            await new Promise((resolve) =>
              setTimeout(resolve, TERMINAL_RECOVERY_RETRY_INTERVAL_MS),
            );
          }
        }
      } finally {
        const nowTime = buildNowRelativeLogTime();
        dispatch({
          type: "ADD_LOG",
          payload: {
            ...nowTime,
            type: "info",
            title: `终态恢复结束：状态=${finalStatus}，是否恢复=${recovered ? "是" : "否"}`,
          },
        });
        terminalRecoveryStateRef.current = {
          ...terminalRecoveryStateRef.current,
          active: false,
          triggeredAt: Date.now(),
        };
      }
    },
    [
      backfillEventsSince,
      buildNowRelativeLogTime,
      dispatch,
      loadFindings,
      loadTask,
      setTask,
      task?.error_message,
      taskId,
      terminalFailureReason,
    ],
  );

  useEffect(() => {
    runTerminalRecoveryRef.current = (triggerReason: string, metadata?: Record<string, unknown>) => {
      void runTerminalRecovery(triggerReason, metadata);
    };
    return () => {
      runTerminalRecoveryRef.current = null;
    };
  }, [runTerminalRecovery]);

  // 🔥 NEW: 加载历史事件并转换为日志项
  const loadHistoricalEvents = useCallback(async () => {
    if (!taskId) return 0;

    if (hasLoadedHistoricalEventsRef.current) {
      console.log("[AgentAudit] Historical events already loaded, skipping");
      return 0;
    }
    hasLoadedHistoricalEventsRef.current = true;

    try {
      console.log(
        `[AgentAudit] Fetching full historical events for task ${taskId}...`,
      );
      const events = await fetchAllHistoricalEvents(taskId, 0);
      if (!events.length) {
        return 0;
      }

      if (!verifiedFindingsManuallyClearedRef.current) {
        const findingItems = events
          .map(agentEventToRealtimeItem)
          .filter((item): item is RealtimeMergedFindingItem => Boolean(item));
        if (findingItems.length) {
          setRealtimeFindings((prev) =>
            mergeRealtimeFindingsBatch(prev, findingItems, { source: "event" }),
          );
        }
      }
      events.forEach((event) => appendLogFromEvent(event));
      compactToolLogsAfterReplay();
      lastEventSequenceRef.current = Math.max(
        lastEventSequenceRef.current,
        events[events.length - 1].sequence,
      );
      setAfterSequence(lastEventSequenceRef.current);
      console.log(
        `[AgentAudit] Historical events loaded: ${events.length}, last sequence=${lastEventSequenceRef.current}`,
      );
      return events.length;
    } catch (err) {
      console.error("[AgentAudit] Failed to load historical events:", err);
      return 0;
    }
  }, [appendLogFromEvent, compactToolLogsAfterReplay, fetchAllHistoricalEvents, taskId]);

  useEffect(() => {
    const bootstrapTaskId = bootstrapInputsSummary?.taskId;
    if (!bootstrapTaskId) return;
    void loadBootstrapInputFindings(bootstrapTaskId);
  }, [
    bootstrapInputsSummary?.taskId,
    bootstrapInputsSummary?.candidateCount,
    bootstrapInputsSummary?.totalFindings,
    loadBootstrapInputFindings,
  ]);

  // Backfill "potential findings" from DB findings so they persist across reloads.
  useEffect(() => {
    if (!findings.length) return;
    if (!verifiedFindingsManuallyClearedRef.current) {
      const items = findings
        .map(agentFindingToRealtimeItem)
        .filter((item): item is RealtimeMergedFindingItem => Boolean(item));
      if (items.length) {
        setRealtimeFindings((prev) =>
          mergeRealtimeFindingsBatch(prev, items, { source: "db" }),
        );
      }
    }
  }, [findings]);

  // ============ Stream Event Handling ============

  const streamOptions = useMemo(
    () => ({
      includeThinking: true,
      includeToolCalls: true,
      afterSequence,
      onEvent: (event: UnifiedAgentEvent) => {
        if (event.metadata?.agent_name) {
          setCurrentAgentName(String(event.metadata.agent_name));
        }
        appendLogFromEvent(event);
        if (String(event.type ?? "").toLowerCase() === "task_end") {
          void backfillEventsSince(
            lastEventSequenceRef.current,
            "task_end_event",
          );
        }
      },
      onThinkingStart: () => {
        const currentId = getCurrentThinkingId();
        if (currentId) {
          updateLog(currentId, { isStreaming: false });
        }
        setCurrentThinkingId(null);
      },
      onThinkingToken: (_token: string, accumulated: string) => {
        if (!accumulated?.trim()) return;
        const cleanContent = sanitizeAuditText(cleanThinkingContent(accumulated));
        if (!cleanContent) return;

        const currentId = getCurrentThinkingId();
        const rawAgent = getCurrentAgentName();
        const displayAgent = rawAgent ? toZhAgentName(rawAgent) : undefined;
        if (!currentId) {
          // 预生成 ID，这样我们可以跟踪这个日志
          const newLogId = `thinking-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
          const nowTime = buildNowRelativeLogTime();
          dispatch({
            type: "ADD_LOG",
            payload: {
              id: newLogId,
              ...nowTime,
              type: "thinking",
              title: "思考中...",
              content: cleanContent,
              isStreaming: true,
              agentName: displayAgent,
              agentRawName: rawAgent || undefined,
            },
          });
          setCurrentThinkingId(newLogId);
        } else {
          updateLog(currentId, { content: cleanContent });
        }
      },
      onThinkingEnd: (response: string) => {
        const cleanResponse = sanitizeAuditText(cleanThinkingContent(response || ""));
        const currentId = getCurrentThinkingId();

        if (!cleanResponse) {
          if (currentId) {
            removeLog(currentId);
          }
          setCurrentThinkingId(null);
          return;
        }

        if (currentId) {
          updateLog(currentId, {
            title:
              cleanResponse.slice(0, 100) +
              (cleanResponse.length > 100 ? "..." : ""),
            content: cleanResponse,
            isStreaming: false,
          });
          setCurrentThinkingId(null);
        }
      },
      onFinding: () => {
        // Realtime findings are synchronized from onEvent to avoid duplicate merges.
      },
      onComplete: () => {
        void backfillEventsSince(lastEventSequenceRef.current, "on_complete");
        void loadTask();
        void loadFindings({ silent: true });
        void loadAgentTree();
      },
      onError: (err: string, context: StreamErrorContext) => {
        const source = context?.source ?? "event";
        const isTerminal = Boolean(context?.terminal);
        if (source === "event" && !isTerminal) {
          console.warn("[AgentAudit] non_terminal_error", {
            message: err,
            context,
          });
          return;
        }

        if (source === "event" && isTerminal) {
          console.error("[AgentAudit] terminal_error", {
            message: err,
            context,
          });
          if (err) {
            setTerminalFailureReason(err);
          }
        } else if (source === "transport" || source === "stream_end") {
          const nowTime = buildNowRelativeLogTime();
          dispatch({
            type: "ADD_LOG",
            payload: {
              ...nowTime,
              type: "error",
              title:
                source === "transport"
                  ? `事件流连接失败：${err}`
                  : `事件流连接中断：${err}`,
            },
          });
        }

        if (isTerminal || source === "transport" || source === "stream_end") {
          void backfillEventsSince(lastEventSequenceRef.current, "on_error");
          void loadTask();
          void loadFindings({ silent: true });
        }
      },
    }),
    [
      afterSequence,
      appendLogFromEvent,
      backfillEventsSince,
      dispatch,
      loadTask,
      loadFindings,
      loadAgentTree,
      updateLog,
      removeLog,
      getCurrentAgentName,
      getCurrentThinkingId,
      setCurrentAgentName,
      setCurrentThinkingId,
      buildNowRelativeLogTime,
    ],
  );

  const {
    connect: connectStream,
    disconnect: disconnectStream,
    isConnected,
  } = useAgentStream(taskId || null, streamOptions);

  // 保存 disconnect 函数到 ref，以便在 taskId 变化时使用
  useEffect(() => {
    disconnectStreamRef.current = disconnectStream;
  }, [disconnectStream]);

  // ============ Effects ============

  // Initial load - 🔥 加载任务数据和历史事件
  useEffect(() => {
    if (!taskId) {
      setShowSplash(true);
      return;
    }
    setShowSplash(false);
    setLoading(true);
    setHistoricalEventsLoaded(false);

    const loadAllData = async () => {
      try {
        // 先加载任务基本信息
        await Promise.all([
          loadTask(),
          loadFindings({ silent: true }),
          loadAgentTree(),
        ]);

        // 🔥 加载历史事件 - 无论任务是否运行都需要加载
        const eventsLoaded = await loadHistoricalEvents();
        console.log(
          `[AgentAudit] Loaded ${eventsLoaded} historical events for task ${taskId}`,
        );

        // 标记历史事件已加载完成 (setAfterSequence 已在 loadHistoricalEvents 中调用)
        setHistoricalEventsLoaded(true);
      } catch (error) {
        console.error("[AgentAudit] Failed to load data:", error);
        setHistoricalEventsLoaded(true); // 即使出错也标记为完成，避免无限等待
      } finally {
        setLoading(false);
      }
    };

    loadAllData();
  }, [
    taskId,
    loadTask,
    loadFindings,
    loadAgentTree,
    loadHistoricalEvents,
    setLoading,
  ]);

  // Stream connection - 🔥 在历史事件加载完成后连接
  useEffect(() => {
    // 等待历史事件加载完成，且任务正在运行
    if (!taskId || !task?.status || task.status !== "running") return;

    // 🔥 使用 state 变量确保在历史事件加载完成后才连接
    if (!historicalEventsLoaded) return;

    // 🔥 避免重复连接 - 只连接一次
    if (hasConnectedRef.current) return;

    hasConnectedRef.current = true;
    console.log(
      `[AgentAudit] Connecting to stream (afterSequence will be passed via streamOptions)`,
    );
    connectStream();
    const nowTime = buildNowRelativeLogTime();
    dispatch({
      type: "ADD_LOG",
      payload: { ...nowTime, type: "info", title: "已连接审计事件流" },
    });

    return () => {
      console.log("[AgentAudit] Cleanup: disconnecting stream");
      disconnectStream();
    };
    // 🔥 CRITICAL FIX: 移除 afterSequence 依赖！
    // afterSequence 通过 streamOptions 传递，不需要在这里触发重连
    // 如果包含它，当 loadHistoricalEvents 更新 afterSequence 时会触发断开重连
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    taskId,
    task?.status,
    historicalEventsLoaded,
    connectStream,
    disconnectStream,
    dispatch,
    buildNowRelativeLogTime,
  ]);

  useEffect(() => {
    if (!taskId || task?.status !== "running") return;
    if (!historicalEventsLoaded) return;
    if (!hasConnectedRef.current) return;
    if (isConnected) return;

    const elapsed = Date.now() - lastStreamSelfHealAttemptRef.current;
    const delay = elapsed >= STREAM_SELF_HEAL_RETRY_MS
      ? 0
      : STREAM_SELF_HEAL_RETRY_MS - elapsed;
    const timer = setTimeout(() => {
      if (taskStatusRef.current !== "running") return;
      lastStreamSelfHealAttemptRef.current = Date.now();
      console.warn("[AgentAudit] stream_self_heal_reconnect", {
        taskId,
        lastSequence: lastEventSequenceRef.current,
      });
      connectStream();
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [
    taskId,
    task?.status,
    historicalEventsLoaded,
    isConnected,
    connectStream,
  ]);

  // Polling
  useEffect(() => {
    if (!taskId || !isRunning) return;
    const interval = setInterval(loadAgentTree, POLLING_INTERVALS.AGENT_TREE);
    return () => clearInterval(interval);
  }, [taskId, isRunning, loadAgentTree]);

  useEffect(() => {
    if (!taskId || !isRunning) return;
    const interval = setInterval(loadTask, POLLING_INTERVALS.TASK_STATS);
    return () => clearInterval(interval);
  }, [taskId, isRunning, loadTask]);

  useEffect(() => {
    if (!taskId || !isRunning) return;
    const interval = setInterval(() => {
      void loadFindings({ silent: true });
    }, FINDINGS_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [taskId, isRunning, loadFindings]);

  useEffect(() => {
    const previousStatus = previousTaskStatusRef.current;
    const currentStatus = task?.status;
    if (
      (previousStatus === "running" || previousStatus === "pending") &&
      currentStatus &&
      TERMINAL_STATUSES.has(currentStatus)
    ) {
      markTerminalBoundary(currentStatus, lastEventSequenceRef.current);
      reconcileTerminalLogs(currentStatus, lastEventSequenceRef.current);
      compactToolLogsAfterReplay();
      void backfillEventsSince(
        lastEventSequenceRef.current,
        "status_transition_to_terminal",
      );
      void loadFindings({ silent: true });
    }
    previousTaskStatusRef.current = currentStatus;
  }, [
    markTerminalBoundary,
    task?.status,
    backfillEventsSince,
    compactToolLogsAfterReplay,
    loadFindings,
    reconcileTerminalLogs,
  ]);

  useEffect(() => {
    if (!historicalEventsLoaded) return;
    const currentStatus = String(task?.status || "").toLowerCase();
    if (!TERMINAL_STATUSES.has(currentStatus)) return;
    reconcileTerminalLogs(currentStatus, lastEventSequenceRef.current);
    compactToolLogsAfterReplay();
  }, [
    compactToolLogsAfterReplay,
    historicalEventsLoaded,
    reconcileTerminalLogs,
    task?.status,
  ]);

  const scrollLogsToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const container = logsContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
  }, []);

  const handleLogsScroll = useCallback(() => {
    const container = logsContainerRef.current;
    if (!container || !isAutoScroll) return;
    const distanceToBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceToBottom <= LOG_AUTO_SCROLL_NEAR_BOTTOM_THRESHOLD_PX) return;
    setAutoScroll(false);
    if (currentProjectId) {
      persistAutoScroll(currentProjectId, false);
    }
  }, [currentProjectId, isAutoScroll, setAutoScroll]);

  // Default viewport: show latest logs (about 3 visible rows) when opening a task.
  useEffect(() => {
    if (!taskId || hasInitializedLogViewportRef.current) return;
    if (filteredLogs.length === 0) return;
    requestAnimationFrame(() => {
      scrollLogsToBottom("auto");
      hasInitializedLogViewportRef.current = true;
    });
  }, [filteredLogs.length, scrollLogsToBottom, taskId]);

  // Auto scroll while stream keeps appending logs.
  useEffect(() => {
    if (!isAutoScroll) return;
    scrollLogsToBottom("smooth");
  }, [filteredLogs.length, isAutoScroll, scrollLogsToBottom]);

  // ============ Handlers ============

  const handleClearPotentialFindings = useCallback(() => {
    verifiedFindingsManuallyClearedRef.current = true;
    setRealtimeFindings([]);
  }, []);

  const handleCancel = async () => {
    if (!taskId || isCancelling) return;
    userCancelSeenRef.current = true;
    setIsCancelling(true);
    const nowTime = buildNowRelativeLogTime();
    dispatch({
      type: "ADD_LOG",
      payload: { ...nowTime, type: "info", title: "正在请求中止任务..." },
    });

    try {
      await cancelAgentTask(taskId);
      toast.success("已提交中止请求");
      const confirmedNow = buildNowRelativeLogTime();
      dispatch({
        type: "ADD_LOG",
        payload: { ...confirmedNow, type: "info", title: "任务中止请求已确认" },
      });
      await loadTask();
      disconnectStream();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "未知错误";
      toast.error(`中止任务失败：${errorMessage}`);
      const failedNow = buildNowRelativeLogTime();
      dispatch({
        type: "ADD_LOG",
        payload: { ...failedNow, type: "error", title: `中止失败：${errorMessage}` },
      });
    } finally {
      setIsCancelling(false);
    }
  };

  const handleExportReport = () => {
    if (!task) return;
    setShowExportDialog(true);
  };

  const handleExportLogs = useCallback(
    (format: "json" | "markdown") => {
      if (!task) {
        toast.error("任务信息未加载，无法导出");
        return;
      }
      const date = new Date();
      const ymd = date.toISOString().slice(0, 10);
      const taskName = toSafeFilename(task.name || task.id.slice(0, 8));
      const base = `agent_audit_logs_${taskName}_${ymd}`;

      if (format === "json") {
        const payload = {
          meta: {
            task_id: task.id,
            task_name: task.name,
            project_id: task.project_id,
            exported_at: date.toISOString(),
            status: task.status,
            current_phase: task.current_phase,
            current_step: task.current_step,
          },
          logs,
        };
        downloadTextFile(
          JSON.stringify(payload, null, 2),
          `${base}.json`,
          "application/json",
        );
        toast.success("活动日志已导出为 JSON");
        return;
      }

      const lines: string[] = [];
      lines.push(`# 智能审计活动日志`);
      lines.push(`- task_id: ${task.id}`);
      lines.push(`- task_name: ${task.name || "-"}`);
      lines.push(`- project_id: ${task.project_id}`);
      lines.push(`- status: ${task.status}`);
      lines.push(`- phase: ${task.current_phase || "-"}`);
      lines.push(`- step: ${task.current_step || "-"}`);
      lines.push(`- exported_at: ${date.toISOString()}`);
      lines.push("");

      for (const item of logs) {
        const typeLabel = LOG_TYPE_LABELS[item.type] || item.type;
        const agentLabel = item.agentName ? `【${item.agentName}】` : "";
        lines.push(`## [${item.time}] [${typeLabel}] ${agentLabel} ${item.title}`);
        if (item.tool?.name) {
          lines.push(
            `- tool: ${item.tool.name} (${item.tool.status || "-"})` +
            (item.tool.duration ? `, ${item.tool.duration}ms` : ""),
          );
        }
        if (item.content) {
          lines.push("");
          lines.push("```text");
          lines.push(item.content);
          lines.push("```");
        }
        if (item.detail) {
          lines.push("");
          lines.push("```json");
          lines.push(JSON.stringify(item.detail, null, 2));
          lines.push("```");
        }
        lines.push("");
      }

      downloadTextFile(lines.join("\n"), `${base}.md`, "text/markdown");
      toast.success("活动日志已导出为 Markdown");
    },
    [logs, task],
  );

  const handleToggleAutoScroll = useCallback(() => {
    const nextEnabled = !isAutoScroll;
    setAutoScroll(nextEnabled);
    if (currentProjectId) {
      persistAutoScroll(currentProjectId, nextEnabled);
    }
    if (nextEnabled) {
      requestAnimationFrame(() => {
        scrollLogsToBottom("smooth");
      });
    }
  }, [currentProjectId, isAutoScroll, scrollLogsToBottom, setAutoScroll]);

  // ============ Render ============

  if (showSplash && !taskId) {
    return (
      <div className="min-h-[100dvh] bg-background flex items-start justify-center relative overflow-y-auto overflow-x-hidden pt-6 md:pt-10">
        <div className="absolute inset-0 cyber-grid opacity-20" />
        <div className="absolute inset-0 vignette pointer-events-none" />

        <div className="relative z-10 w-full max-w-[1800px] mx-auto px-6 text-center">
          <button
            type="button"
            onClick={cycleLogoVariant}
            className="mx-auto mb-6 w-48 h-48 rounded-[2.5rem] border border-primary/40 bg-primary/10 flex items-center justify-center shadow-[0_0_48px_rgba(59,130,246,0.4)] cursor-pointer transition-transform duration-200 hover:scale-[1.02]"
            title="点击切换 Logo"
          >
            <img
              src={logoSrc}
              alt="VulHunter"
              className="w-32 h-32 object-contain"
            />
          </button>

          <h1 className="text-6xl md:text-7xl font-mono font-bold tracking-wider text-foreground">
            VulHunter
          </h1>
          <p className="mt-4 text-xl md:text-2xl text-muted-foreground leading-relaxed">
            VulHunter 让你以静态、智能或混合方式快速发起代码安全审计。
          </p>

          <div className="mt-8 mx-auto w-full md:w-[80%] grid grid-cols-1 md:grid-cols-[repeat(3,30%)] md:justify-between gap-5 text-left">
            {homeScanCards.map((card) => {
              const Icon = card.icon;
              return (
                <button
                  key={card.key}
                  type="button"
                  onClick={() => openHomeModeDialog(card.key)}
                  aria-label={`${card.title}，点击快速开启审计`}
                  className="group relative flex h-full min-h-[280px] flex-col overflow-hidden rounded-2xl border border-border/70 bg-card/70 p-6 md:p-7 transition-all duration-300 hover:-translate-y-1 hover:border-primary/50 hover:shadow-[0_22px_48px_-28px_rgba(56,189,248,0.65)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
                >
                  <div
                    className={`pointer-events-none absolute inset-0 bg-gradient-to-br opacity-0 transition-opacity duration-300 group-hover:opacity-100 group-focus-visible:opacity-100 ${card.accentClassName}`}
                  />
                  <div className="relative z-10 flex h-full flex-col items-start text-left">
                    <div className="flex-1 space-y-3">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-primary/35 bg-primary/10 text-primary">
                          <Icon className="w-5 h-5" />
                        </span>
                        <h3 className="text-lg md:text-xl font-semibold text-foreground">
                          {card.title}
                        </h3>
                      </div>
                      <p className="w-full text-sm md:text-base text-muted-foreground leading-relaxed text-left break-words">
                        {card.intro}
                      </p>
                      <p className="w-full text-sm md:text-base text-foreground/90 leading-relaxed text-left break-words">
                        {card.strengths}
                      </p>
                      <p className="w-full text-sm md:text-base text-muted-foreground leading-relaxed text-left break-words">
                        {card.limitations}
                      </p>
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-2 border-t border-primary/20 pt-3 text-sm font-medium text-muted-foreground transition-colors duration-200 group-hover:text-primary group-focus-visible:text-primary">
                      <span className="text-left break-words">
                        {card.quickStartHint}
                      </span>
                      <ArrowRight className="h-4 w-4 flex-shrink-0 transition-transform duration-200 group-hover:translate-x-0.5 group-focus-visible:translate-x-0.5" />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <CreateProjectAuditDialog
          open={showHomeStaticDialog}
          onOpenChange={setShowHomeStaticDialog}
          initialMode="static"
          lockMode
          allowUploadProject
          navigateOnSuccess
          primaryCreateLabel="开始静态扫描"
        />
        <CreateProjectAuditDialog
          open={showHomeAgentDialog}
          onOpenChange={setShowHomeAgentDialog}
          initialMode="agent"
          lockMode
          allowUploadProject
          navigateOnSuccess
          primaryCreateLabel="开始智能扫描"
        />
        <CreateProjectAuditDialog
          open={showHomeMixedDialog}
          onOpenChange={setShowHomeMixedDialog}
          initialMode="hybrid"
          lockMode
          allowUploadProject
          navigateOnSuccess
          primaryCreateLabel="开始混合扫描"
        />
      </div>
    );
  }

  if (isLoading && !task) {
    return (
      <div className="h-[100dvh] max-h-[100dvh] bg-background flex items-center justify-center relative overflow-hidden">
        {/* Grid background */}
        <div className="absolute inset-0 cyber-grid opacity-30" />
        {/* Vignette */}
        <div className="absolute inset-0 vignette pointer-events-none" />
        <div className="flex items-center gap-3 text-muted-foreground relative z-10">
          <Loader2 className="w-5 h-5 animate-spin text-primary" />
          <span className="font-mono text-sm tracking-wide">
            正在加载审计任务...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[100dvh] max-h-[100dvh] bg-background flex flex-col overflow-hidden relative">
      {/* Header */}
      <Header
        task={task}
        isRunning={isRunning}
        isCancelling={isCancelling}
        phaseLabel={currentPhaseLabel}
        phaseHint={phaseHint}
        onBack={handleBack}
        onCancel={handleCancel}
        onExport={handleExportReport}
        onNewAudit={() => setShowCreateDialog(true)}
      />

      {/* Main content */}
      <div className="flex-1 overflow-hidden relative p-3 bg-muted/10">
        <div className="h-full flex flex-col gap-3">
          {failedReason && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3">
              <div className="text-sm font-semibold text-rose-600 dark:text-rose-300">
                智能审计失败{failedStep ? `（${failedStep}）` : ""}
              </div>
              <div className="mt-1 text-xs font-mono text-rose-700 dark:text-rose-200 whitespace-pre-wrap break-words">
                {failedReason}
              </div>
            </div>
          )}

          {/* Full-width stats row */}
          <div className="flex-shrink-0">
            <div
              ref={agentContainerRef}
              className="overflow-y-auto custom-scrollbar"
            >
              <StatsPanel task={task} findings={findings} />
            </div>
          </div>

          {/* Full-width findings panel (expanded) */}
          <div className="min-h-0 flex-1 overflow-hidden">
            <div ref={findingsContainerRef} className="h-full">
              <RealtimeFindingsPanel
                items={realtimeFindings}
                isRunning={isRunning}
                onClear={handleClearPotentialFindings}
              />
            </div>
          </div>

          {/* Bottom: Full-width event logs */}
          <div className="flex-shrink-0 rounded-xl border border-border bg-card/70 overflow-hidden">
            <div className="px-4 py-3 border-b border-border bg-card">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Terminal className="w-4 h-4 text-primary" />
                  <span className="text-sm font-semibold">事件日志</span>
                  <Badge variant="outline" className="text-[11px]">
                    {filteredLogs.length}
                  </Badge>
                  {isConnected ? (
                    <Badge
                      variant="outline"
                      className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                    >
                      已连接
                    </Badge>
                  ) : null}
                  <span className="text-[11px] text-muted-foreground">
                    默认最新 {LOG_DEFAULT_VISIBLE_COUNT} 条，可上拉查看历史
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md font-mono uppercase tracking-wider border border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>导出日志</span>
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => handleExportLogs("json")}>
                        导出为 JSON
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => handleExportLogs("markdown")}>
                        导出为 Markdown
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => toast.info("导出范围：全部活动日志")}>
                        当前为全部导出
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <button
                    onClick={handleToggleAutoScroll}
                    className={`
                      flex items-center gap-2 text-xs px-3 py-1.5 rounded-md font-mono uppercase tracking-wider
                      ${isAutoScroll
                        ? "bg-primary/15 text-primary border border-primary/50"
                        : "text-muted-foreground hover:text-foreground border border-border hover:bg-muted"
                      }
                    `}
                  >
                    <ArrowDown className="w-3.5 h-3.5" />
                    <span>自动滚动</span>
                  </button>
                </div>
              </div>
            </div>

            <div className="p-3">
              <div
                ref={logsContainerRef}
                onScroll={handleLogsScroll}
                className="overflow-y-auto p-2 custom-scrollbar bg-muted/30 rounded-lg border border-border"
                style={{ height: LOG_VIEWPORT_HEIGHT_PX, maxHeight: "30vh" }}
              >
                {filteredLogs.length === 0 ? (
                  <div className="h-full flex items-center justify-center">
                    <div className="text-center text-muted-foreground">
                      {isRunning ? (
                        <div className="flex flex-col items-center gap-3">
                          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                          <span className="text-sm font-mono tracking-wide">
                            等待活动日志...
                          </span>
                        </div>
                      ) : (
                        <span className="text-sm font-mono tracking-wide">
                          暂无活动日志
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 p-1.5">
                    {filteredLogs.map((item) => (
                      <LogEntry
                        key={item.id}
                        item={item}
                        anchorId={`log-item-${item.id}`}
                        highlighted={highlightedLogId === item.id}
                        onOpenDetail={() =>
                          openDetailDialog({
                            type: "log",
                            id: item.id,
                            anchorId: `log-item-${item.id}`,
                          })
                        }
                      />
                    ))}
                  </div>
                )}
                <div ref={logEndRef} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Create dialog */}
      <CreateAgentTaskDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
      />

      {/* Export dialog */}
      <ReportExportDialog
        open={showExportDialog}
        onOpenChange={setShowExportDialog}
        task={task}
        findings={findings}
      />

      <AuditDetailDialog
        open={detailDialog !== null}
        detailType={detailDialog?.type ?? null}
        logItem={selectedLogItem}
        finding={selectedFinding}
        agentNode={selectedAgentNode}
        onBack={handleDetailBack}
        onOpenChange={(open) => {
          if (!open) {
            handleDetailBack();
          }
        }}
      />
    </div>
  );
}

// Wrapped export with Error Boundary
export default function AgentAuditPage() {
  const { taskId } = useParams<{ taskId: string }>();

  return (
    <AgentErrorBoundary
      taskId={taskId}
      onRetry={() => window.location.reload()}
    >
      <AgentAuditPageContent />
    </AgentErrorBoundary>
  );
}
