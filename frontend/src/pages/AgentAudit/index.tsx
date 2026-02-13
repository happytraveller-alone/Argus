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
  Loader2,
  ArrowDown,
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
import {
  getAgentTask,
  getAgentFindings,
  cancelAgentTask,
  getAgentTree,
  getAgentEvents,
  type AgentFinding,
  AgentEvent,
} from "@/shared/api/agentTasks";
import {
  getOpengrepScanFindings,
  type OpengrepFinding,
} from "@/shared/api/opengrep";
import CreateAgentTaskDialog from "@/components/agent/CreateAgentTaskDialog";

// Local imports
import {
  SplashScreen,
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
import { cleanThinkingContent } from "./utils";
import type {
  BootstrapInputsSummary,
  DetailViewState,
  FindingsViewFilters,
} from "./types";

import type { RealtimeMergedFindingItem } from "./components/RealtimeFindingsPanel";

const EVENT_PAGE_SIZE = 500;
const EVENT_BATCH_SAFETY_LIMIT = 200;
const FINDINGS_REFRESH_INTERVAL = 10000;
const BOOTSTRAP_FINDING_PAGE_SIZE = 200;

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

type UnifiedAgentEvent = {
  type?: string;
  event_type?: string;
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

function toChineseAgentName(raw: string): string {
  const text = String(raw || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower.includes("orchestrator")) return "编排";
  if (lower.includes("recon")) return "侦查";
  if (lower.includes("analysis")) return "分析";
  if (lower.includes("verification")) return "验证";
  return text;
}

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

function buildFindingFingerprint(input: {
  vulnerability_type: unknown;
  file_path: unknown;
  line_start: unknown;
  title: unknown;
}): string {
  const vulnerabilityType = toSafeTrimmedString(input.vulnerability_type) || "unknown";
  const filePath = toSafeTrimmedString(input.file_path);
  const lineStart =
    typeof input.line_start === "number" && Number.isFinite(input.line_start)
      ? String(input.line_start)
      : "";
  const title = toSafeTrimmedString(input.title);
  return [vulnerabilityType, filePath, lineStart, title].join("|");
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

function agentFindingToRealtimeItem(finding: AgentFinding): RealtimeMergedFindingItem | null {
  // Default: do not surface false positives in "potential defects".
  if (finding.status === "false_positive" || finding.authenticity === "false_positive") {
    return null;
  }

  const fingerprint = buildFindingFingerprint({
    vulnerability_type: finding.vulnerability_type,
    file_path: finding.file_path,
    line_start: finding.line_start,
    title: finding.title,
  });

  return {
    id: finding.id,
    fingerprint,
    title: toSafeTrimmedString(finding.title) || "发现缺陷",
    severity: toSafeTrimmedString(finding.severity) || "medium",
    vulnerability_type: toSafeTrimmedString(finding.vulnerability_type) || "unknown",
    file_path: finding.file_path ?? null,
    line_start: finding.line_start ?? null,
    timestamp: finding.created_at ?? null,
    is_verified: Boolean(finding.is_verified),
  };
}

function agentEventToRealtimeItem(event: AgentEvent): RealtimeMergedFindingItem | null {
  const eventType = toSafeTrimmedString(event.event_type).toLowerCase();
  if (
    eventType !== "finding_new" &&
    eventType !== "finding_verified" &&
    eventType !== "finding_update" &&
    eventType !== "finding"
  ) {
    return null;
  }

  const md = event.metadata ?? {};
  const title =
    toSafeTrimmedString((md as any).title) ||
    toSafeTrimmedString(event.message) ||
    "发现缺陷";
  const vulnerabilityType = toSafeTrimmedString((md as any).vulnerability_type) || "unknown";
  const filePath = toSafeTrimmedString((md as any).file_path) || null;
  const lineStart =
    typeof (md as any).line_start === "number" && Number.isFinite((md as any).line_start)
      ? ((md as any).line_start as number)
      : null;
  const severity = toSafeTrimmedString((md as any).severity) || "medium";
  const mdTimestamp =
    typeof (md as any).timestamp === "string" ? ((md as any).timestamp as string) : null;
  const timestamp = event.timestamp || mdTimestamp || null;
  const isVerified =
    eventType === "finding_verified" || (md as any).is_verified === true;

  const fingerprint = buildFindingFingerprint({
    vulnerability_type: vulnerabilityType,
    file_path: filePath || "",
    line_start: lineStart,
    title,
  });

  const id =
    toSafeTrimmedString(event.finding_id) ||
    toSafeTrimmedString((md as any).id) ||
    toSafeTrimmedString(event.id) ||
    `finding-${Date.now()}`;

  return {
    id,
    fingerprint,
    title,
    severity,
    vulnerability_type: vulnerabilityType,
    file_path: filePath,
    line_start: lineStart,
    timestamp,
    is_verified: Boolean(isVerified),
  };
}

function mergeRealtimeFindingsBatch(
  prev: RealtimeMergedFindingItem[],
  incoming: RealtimeMergedFindingItem[],
  options: { source: "db" | "event" },
): RealtimeMergedFindingItem[] {
  if (!incoming.length) return prev;

  const byFingerprint = new Map<string, RealtimeMergedFindingItem>();
  for (const item of prev) {
    if (!item?.fingerprint) continue;
    if (!byFingerprint.has(item.fingerprint)) {
      byFingerprint.set(item.fingerprint, item);
    }
  }

  for (const item of incoming) {
    if (!item?.fingerprint) continue;
    const existing = byFingerprint.get(item.fingerprint);
    if (!existing) {
      byFingerprint.set(item.fingerprint, item);
      continue;
    }

    const preferIncoming = options.source === "db";
    const merged: RealtimeMergedFindingItem = {
      ...existing,
      // Prefer DB fields; event backfill only fills blanks.
      id: preferIncoming ? (item.id || existing.id) : (existing.id || item.id),
      title: preferIncoming
        ? (item.title || existing.title)
        : (existing.title || item.title),
      severity: preferIncoming
        ? (item.severity || existing.severity)
        : (existing.severity || item.severity),
      vulnerability_type: preferIncoming
        ? (item.vulnerability_type || existing.vulnerability_type)
        : (existing.vulnerability_type || item.vulnerability_type),
      file_path: preferIncoming
        ? (item.file_path ?? existing.file_path)
        : (existing.file_path ?? item.file_path),
      line_start: preferIncoming
        ? (item.line_start ?? existing.line_start)
        : (existing.line_start ?? item.line_start),
      timestamp: pickNewerIsoTimestamp(existing.timestamp, item.timestamp),
      is_verified: Boolean(existing.is_verified) || Boolean(item.is_verified),
    };

    byFingerprint.set(item.fingerprint, merged);
  }

  const merged = Array.from(byFingerprint.values());
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
    agentTree,
    logs,
    isLoading,
    isAutoScroll,
    treeNodes,
    filteredLogs,
    isRunning,
    isComplete,
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
  const potentialFindingsManuallyClearedRef = useRef(false);

  const logEndRef = useRef<HTMLDivElement>(null);
  const logsContainerRef = useRef<HTMLDivElement | null>(null);
  const findingsContainerRef = useRef<HTMLDivElement | null>(null);
  const agentContainerRef = useRef<HTMLDivElement | null>(null);
  const logsRef = useRef(logs);
  const toolLogIdByCallIdRef = useRef<Map<string, string>>(new Map());
  const agentTreeRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const lastAgentTreeRefreshTime = useRef<number>(0);
  const previousTaskIdRef = useRef<string | undefined>(undefined);
  const disconnectStreamRef = useRef<(() => void) | null>(null);
  const lastEventSequenceRef = useRef<number>(0);
  const hasConnectedRef = useRef<boolean>(false); // 🔥 追踪是否已连接 SSE
  const hasLoadedHistoricalEventsRef = useRef<boolean>(false); // 🔥 追踪是否已加载历史事件
  const isBackfillingRef = useRef(false);
  const previousTaskStatusRef = useRef<string | undefined>(undefined);
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
  const agentCardStatusText = useMemo(() => {
    if (isRunning) return "运行中";
    if (task?.status === "completed") return "完成";
    if (task?.status === "failed") return "失败";
    if (task?.status === "cancelled") return "已取消";
    return "就绪";
  }, [isRunning, task?.status]);

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

      // 2.1 重置 realtime 面板
      setRealtimeFindings([]);
      potentialFindingsManuallyClearedRef.current = false;
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

  const appendLogFromEvent = useCallback(
    (event: UnifiedAgentEvent) => {
      const eventType = String(
        event.event_type ?? event.type ?? "",
      ).toLowerCase();
      const message = eventToString(event.message).trim();
      const metadata = event.metadata ?? undefined;
      const agentRawName =
        (typeof metadata?.agent_name === "string" && metadata.agent_name) ||
        (typeof metadata?.agent === "string" && metadata.agent) ||
        undefined;
      const agentName =
        typeof agentRawName === "string" && agentRawName.trim()
          ? toChineseAgentName(agentRawName)
          : undefined;
      const baseDetail = {
        event_type: eventType,
        message,
        metadata: metadata ?? {},
        sequence: event.sequence ?? null,
        status: event.status ?? null,
        tool_name: event.tool_name ?? null,
        tool_input: event.tool_input ?? null,
        tool_output: event.tool_output ?? null,
        tool_duration_ms: event.tool_duration_ms ?? null,
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

      if (
        eventType === "thinking_start" ||
        eventType === "thinking_end" ||
        eventType === "thinking_token"
      ) {
        return;
      }

      if (eventType.startsWith("llm_") || eventType === "thinking") {
        const thought =
          typeof metadata?.thought === "string" ? metadata.thought : "";
        const content = thought || message || "";
        if (!content) {
          return;
        }
        dispatch({
          type: "ADD_LOG",
          payload: {
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
        const toolName = event.tool_name || "未知";
        const inputText = eventToString(event.tool_input);
        const toolCallId = (() => {
          const value = metadata?.tool_call_id;
          return typeof value === "string" && value.trim().length > 0
            ? value.trim()
            : null;
        })();

        const existingLogId = toolCallId
          ? toolLogIdByCallIdRef.current.get(toolCallId)
          : null;
        if (existingLogId) {
          updateLog(existingLogId, {
            type: "tool",
            title: `运行中：${toolName}`,
            content: inputText ? `输入：\n${inputText}` : "",
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
        }

        dispatch({
          type: "ADD_LOG",
          payload: {
            id: logId,
            type: "tool",
            title: `运行中：${toolName}`,
            content: inputText ? `输入：\n${inputText}` : "",
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
        const toolName = event.tool_name || "未知";
        const toolStatus = normalizeToolStatus(
          metadata?.tool_status,
          eventType,
        );
        const statusLabel =
          toolStatus === "completed"
            ? "已完成"
            : toolStatus === "failed"
              ? "失败"
              : "已取消";
        const outputText = extractToolOutputText(event.tool_output);
        const toolCallId = (() => {
          const value = metadata?.tool_call_id;
          return typeof value === "string" && value.trim().length > 0
            ? value.trim()
            : null;
        })();

        let targetLogId: string | null = null;
        if (toolCallId) {
          targetLogId =
            toolLogIdByCallIdRef.current.get(toolCallId) ?? `tool-${toolCallId}`;
        } else {
          const fallbackLog = [...logsRef.current]
            .reverse()
            .find(
              (item) =>
                item.type === "tool" &&
                item.tool?.name === toolName &&
                item.tool?.status === "running",
            );
          targetLogId = fallbackLog?.id || null;
        }

        if (targetLogId) {
          const existing = logsRef.current.find((item) => item.id === targetLogId);
          if (existing && existing.tool?.status === toolStatus && toolCallId) {
            return;
          }

          const previousContent = existing?.content ? `${existing.content}\n\n` : "";
          updateLog(targetLogId, {
            type: "tool",
            title: `${statusLabel}：${toolName}`,
            content: outputText
              ? `${previousContent}输出：\n${outputText}`
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
            type: "tool",
            title: `${statusLabel}：${toolName}`,
            content: outputText ? `输出：\n${outputText}` : "",
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
        dispatch({
          type: "ADD_LOG",
          payload: {
            type: "finding",
            title: message || eventToString(metadata?.title) || "发现漏洞",
            severity: eventToString(metadata?.severity) || "medium",
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
        return;
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
        dispatch({
          type: "ADD_LOG",
          payload: {
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
          eventToString(metadata?.error).trim() ||
          "任务执行出错";
        if (taskErrorMessage) {
          setTerminalFailureReason(taskErrorMessage);
        }
        dispatch({
          type: "ADD_LOG",
          payload: {
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
        dispatch({
          type: "ADD_LOG",
          payload: {
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
        const status = event.status ? `（${event.status}）` : "";
        dispatch({
          type: "ADD_LOG",
          payload: {
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
            },
          });
          return;
        }

        dispatch({
          type: "ADD_LOG",
          payload: {
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
            type: "info",
            title: message,
            agentName,
            agentRawName: agentRawName || undefined,
            detail: baseDetail,
          },
        });
      }
    },
    [debouncedLoadAgentTree, dispatch, updateLog],
  );

  const backfillEventsSince = useCallback(
    async (startAfter: number, reason: string) => {
      if (!taskId || isBackfillingRef.current) return;
      isBackfillingRef.current = true;
      try {
        const events = await fetchAllHistoricalEvents(taskId, startAfter);
        if (events.length === 0) {
          return;
        }

        if (!potentialFindingsManuallyClearedRef.current) {
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
    [appendLogFromEvent, fetchAllHistoricalEvents, taskId],
  );

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

      if (!potentialFindingsManuallyClearedRef.current) {
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
  }, [appendLogFromEvent, fetchAllHistoricalEvents, taskId]);

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
    if (potentialFindingsManuallyClearedRef.current) return;
    if (!findings.length) return;
    const items = findings
      .map(agentFindingToRealtimeItem)
      .filter((item): item is RealtimeMergedFindingItem => Boolean(item));
    if (!items.length) return;
    setRealtimeFindings((prev) =>
      mergeRealtimeFindingsBatch(prev, items, { source: "db" }),
    );
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
        const cleanContent = cleanThinkingContent(accumulated);
        if (!cleanContent) return;

        const currentId = getCurrentThinkingId();
        const rawAgent = getCurrentAgentName();
        const displayAgent = rawAgent ? toChineseAgentName(rawAgent) : undefined;
        if (!currentId) {
          // 预生成 ID，这样我们可以跟踪这个日志
          const newLogId = `thinking-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
          dispatch({
            type: "ADD_LOG",
            payload: {
              id: newLogId,
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
        const cleanResponse = cleanThinkingContent(response || "");
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
      onFinding: (finding: Record<string, unknown>, isVerified: boolean) => {
        potentialFindingsManuallyClearedRef.current = false;
        const safeText = (value: unknown) => String(value ?? "").trim();
        const title = safeText(finding.title) || "发现漏洞";
        const vulnerabilityType = safeText(finding.vulnerability_type) || "unknown";
        const filePath = safeText(finding.file_path) || null;
        const lineStart =
          typeof finding.line_start === "number" && Number.isFinite(finding.line_start)
            ? (finding.line_start as number)
            : null;
        const severity = safeText(finding.severity) || "medium";
        const timestamp =
          typeof (finding as any).timestamp === "string"
            ? ((finding as any).timestamp as string)
            : null;

        const fingerprint = [
          vulnerabilityType,
          filePath || "",
          lineStart === null ? "" : String(lineStart),
          title,
        ].join("|");

        const streamId = safeText(finding.id) || `finding-${Date.now()}`;

        const nextItem: RealtimeMergedFindingItem = {
          id: streamId,
          fingerprint,
          title,
          severity,
          vulnerability_type: vulnerabilityType,
          file_path: filePath,
          line_start: lineStart,
          timestamp,
          is_verified: Boolean(isVerified),
        };

        setRealtimeFindings((prev) => {
          const idx = prev.findIndex((x) => x.fingerprint === fingerprint);
          if (idx === -1) {
            return [nextItem, ...prev].slice(0, 500);
          }

          const existing = prev[idx];
          const merged: RealtimeMergedFindingItem = {
            ...existing,
            ...nextItem,
            id: existing.id, // keep stable key
            is_verified: existing.is_verified || Boolean(isVerified),
          };

          const next = [...prev];
          next.splice(idx, 1);
          next.unshift(merged);
          return next.slice(0, 500);
        });
      },
      onComplete: () => {
        void backfillEventsSince(lastEventSequenceRef.current, "on_complete");
        void loadTask();
        void loadFindings({ silent: true });
        void loadAgentTree();
      },
      onError: (err: string) => {
        dispatch({
          type: "ADD_LOG",
          payload: { type: "error", title: `错误：${err}` },
        });
        void backfillEventsSince(lastEventSequenceRef.current, "on_error");
        void loadTask();
        void loadFindings({ silent: true });
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
    dispatch({
      type: "ADD_LOG",
      payload: { type: "info", title: "已连接审计事件流" },
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
      previousStatus === "running" &&
      currentStatus &&
      TERMINAL_STATUSES.has(currentStatus)
    ) {
      void backfillEventsSince(
        lastEventSequenceRef.current,
        "status_transition_to_terminal",
      );
      void loadFindings({ silent: true });
    }
    previousTaskStatusRef.current = currentStatus;
  }, [task?.status, backfillEventsSince, loadFindings]);

  // Auto scroll
  useEffect(() => {
    if (isAutoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, isAutoScroll]);

  // ============ Handlers ============

  const handleClearPotentialFindings = useCallback(() => {
    potentialFindingsManuallyClearedRef.current = true;
    setRealtimeFindings([]);
  }, []);

  const handleCancel = async () => {
    if (!taskId || isCancelling) return;
    setIsCancelling(true);
    dispatch({
      type: "ADD_LOG",
      payload: { type: "info", title: "正在请求中止任务..." },
    });

    try {
      await cancelAgentTask(taskId);
      toast.success("已提交中止请求");
      dispatch({
        type: "ADD_LOG",
        payload: { type: "info", title: "任务中止请求已确认" },
      });
      await loadTask();
      disconnectStream();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "未知错误";
      toast.error(`中止任务失败：${errorMessage}`);
      dispatch({
        type: "ADD_LOG",
        payload: { type: "error", title: `中止失败：${errorMessage}` },
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

  // ============ Render ============

  if (showSplash && !taskId) {
    return (
      <div className="h-[100dvh] max-h-[100dvh] bg-background flex items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 cyber-grid opacity-20" />
        <div className="absolute inset-0 vignette pointer-events-none" />

        <div className="relative z-10 max-w-4xl mx-auto px-6 text-center">
          <button
            type="button"
            onClick={cycleLogoVariant}
            className="mx-auto mb-10 w-48 h-48 rounded-[2.5rem] border border-primary/40 bg-primary/10 flex items-center justify-center shadow-[0_0_48px_rgba(59,130,246,0.4)] cursor-pointer transition-transform duration-200 hover:scale-[1.02]"
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
          <p className="mt-6 text-2xl md:text-3xl text-muted-foreground leading-relaxed">
            面向代码安全与合规审计的智能分析平台。聚焦仓库级项目，
            提供任务编排、自动化审计与结果追踪，帮助团队更快定位风险与改进点。
          </p>
        </div>

        {/*
        <SplashScreen onComplete={() => setShowCreateDialog(true)} />
        <CreateAgentTaskDialog open={showCreateDialog} onOpenChange={setShowCreateDialog} />
        */}
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
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Column - Event Logs */}
        <div className="w-[55%] min-w-0 flex flex-col border-r border-border bg-muted/20">
          <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
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
                  onClick={() => setAutoScroll(!isAutoScroll)}
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

          {failedReason && (
            <div className="mx-3 mt-3 mb-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3">
              <div className="text-sm font-semibold text-rose-600 dark:text-rose-300">
                智能审计失败{failedStep ? `（${failedStep}）` : ""}
              </div>
              <div className="mt-1 text-xs font-mono text-rose-700 dark:text-rose-200 whitespace-pre-wrap break-words">
                {failedReason}
              </div>
            </div>
          )}

          <div className="flex-1 min-h-0 p-3">
            <div
              ref={logsContainerRef}
              className="h-full overflow-y-auto p-2 custom-scrollbar bg-muted/30 rounded-xl border border-border"
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
                <div className="space-y-3 p-2">
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

        {/* Right Column - Findings (top) + Agent (bottom) */}
        <div className="w-[45%] min-w-0 flex flex-col bg-muted/10">
          <div className="flex-1 min-h-0 p-3">
            <RealtimeFindingsPanel
              items={realtimeFindings}
              isRunning={isRunning}
              onClear={handleClearPotentialFindings}
            />
          </div>

          <div className="flex-shrink-0 border-t border-border bg-card/50 p-3">
            <div className="max-h-[42vh] overflow-y-auto custom-scrollbar">
              <div className="rounded-xl border border-border bg-card p-4">
                <StatsPanel task={task} findings={findings} />
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
