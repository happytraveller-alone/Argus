/**
 * Agent Scan Utilities
 * Helper functions for the Agent Scan page
 */

import type { AgentTreeNode, LogItem } from "./types";
import { isAgentAuditTerminalStatus } from "./taskStatus";

const AUDIT_EMOJI_REGEX = /[\p{Extended_Pictographic}\uFE0F\u200D]/gu;
const AUDIT_DECORATION_REGEX = /[◆◇■□●○★☆▶▷◀◁►◄•▪▫◉◎◌⏭⏮⏯⏹⏺⏸⏵⏴⏩⏪]/g;

/**
 * Remove emoji/decorative symbols from scan logs while preserving readable text.
 */
export function sanitizeAuditText(value: string): string {
  if (!value) return "";
  return String(value)
    .replace(AUDIT_EMOJI_REGEX, "")
    .replace(AUDIT_DECORATION_REGEX, "")
    .replace(/\u00A0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

/**
 * Normalize finding path for UI display:
 * - Prefer project-relative style
 * - Strip absolute path prefix when fallback is needed
 */
export function normalizeAuditRelativePath(
  value: string | null | undefined,
): string | null {
  const raw = sanitizeAuditText(String(value ?? ""))
    .replace(/\\/g, "/")
    .replace(/^file:\/\//i, "")
    .trim();
  if (!raw) return null;

  const windowsAbsolute = /^[A-Za-z]:\//.test(raw);
  let pathPart = raw;
  let suffix = "";
  if (!windowsAbsolute) {
    const lineMatch = raw.match(/^(.*?):(\d+(?:-\d+)?)$/);
    if (lineMatch) {
      pathPart = String(lineMatch[1] || "").trim();
      suffix = `:${lineMatch[2]}`;
    }
  }

  if (!pathPart) return null;
  while (pathPart.startsWith("./")) {
    pathPart = pathPart.slice(2);
  }

  if (pathPart.startsWith("/")) {
    const segments = pathPart.split("/").filter(Boolean);
    if (!segments.length) return null;
    const anchors = [
      "src",
      "app",
      "backend",
      "frontend",
      "lib",
      "include",
      "tests",
      "test",
      "config",
    ];
    const anchorIndex = segments.findIndex((seg) => anchors.includes(seg));
    if (anchorIndex >= 0) {
      return `${segments.slice(anchorIndex).join("/")}${suffix}`;
    }
    return `${segments[segments.length - 1]}${suffix}`;
  }

  if (windowsAbsolute) {
    const segments = pathPart.split("/").filter(Boolean);
    const filename = segments[segments.length - 1] || pathPart;
    return `${filename}${suffix}`;
  }

  return `${pathPart}${suffix}`;
}

/**
 * Build tree structure from flat node list
 */
export function buildAgentTree(flatNodes: AgentTreeNode[]): AgentTreeNode[] {
  if (!flatNodes || flatNodes.length === 0) return [];

  // Create node map
  const nodeMap = new Map<string, AgentTreeNode>();
  flatNodes.forEach((node) => {
    nodeMap.set(node.agent_id, { ...node, children: [] });
  });

  // Build tree structure
  const rootNodes: AgentTreeNode[] = [];

  flatNodes.forEach((node) => {
    const currentNode = nodeMap.get(node.agent_id)!;

    if (node.parent_agent_id && nodeMap.has(node.parent_agent_id)) {
      const parentNode = nodeMap.get(node.parent_agent_id)!;
      parentNode.children.push(currentNode);
    } else {
      rootNodes.push(currentNode);
    }
  });

  return rootNodes;
}

/**
 * Find agent by ID in tree
 */
export function findAgentInTree(
  nodes: AgentTreeNode[],
  id: string,
): AgentTreeNode | null {
  for (const node of nodes) {
    if (node.agent_id === id) return node;
    const found = findAgentInTree(node.children, id);
    if (found) return found;
  }
  return null;
}

/**
 * Find agent name by ID in tree
 */
export function findAgentName(
  nodes: AgentTreeNode[],
  id: string,
): string | null {
  const agent = findAgentInTree(nodes, id);
  return agent?.agent_name || null;
}

/**
 * Generate unique log ID
 */
let logIdCounter = 0;
export function generateLogId(): string {
  return `log-${++logIdCounter}`;
}

/**
 * Reset log ID counter (for testing)
 */
export function resetLogIdCounter(): void {
  logIdCounter = 0;
}

/**
 * Get current time string for logs
 */
export function getTimeString(): string {
  return new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDurationHms(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((safe % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (safe % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

export function formatRelativeFromStart(
  startedAtIso: string,
  eventIso: string,
): string {
  const startedMs = new Date(startedAtIso).getTime();
  const eventMs = new Date(eventIso).getTime();
  if (!Number.isFinite(startedMs) || !Number.isFinite(eventMs)) {
    return "00:00:00";
  }
  return formatDurationHms((eventMs - startedMs) / 1000);
}

export function resolveLogDisplayTime(
  startedAtIso: string | null | undefined,
  eventIso: string | null | undefined,
  fallbackNow = getTimeString(),
): string {
  const started = String(startedAtIso || "").trim();
  const eventTs = String(eventIso || "").trim();
  if (!started || !eventTs) {
    return fallbackNow;
  }
  return formatRelativeFromStart(started, eventTs);
}

/**
 * Create a log item
 */
export function createLogItem(
  item: Omit<LogItem, "id" | "time"> & { time?: string; eventTimestamp?: string | null },
): LogItem {
  return {
    ...item,
    id: generateLogId(),
    time: typeof item.time === "string" && item.time.trim() ? item.time : getTimeString(),
  };
}

function toFiniteSequence(value: unknown): number | null {
  const sequence = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(sequence)) {
    return null;
  }
  return Math.floor(sequence);
}

function extractExistingToolCallId(log: LogItem): string | null {
  const directCallId =
    typeof log.tool?.callId === "string" ? log.tool.callId.trim() : "";
  if (directCallId) {
    return directCallId;
  }

  const metadata =
    log.detail && typeof log.detail === "object"
      ? (log.detail.metadata as Record<string, unknown> | undefined)
      : undefined;
  const metadataCallId =
    typeof metadata?.tool_call_id === "string" ? metadata.tool_call_id.trim() : "";
  return metadataCallId || null;
}

export function shouldIgnoreStaleToolEvent(input: {
  existingLog: LogItem | null | undefined;
  incomingEventType: string;
  incomingSequence?: number | null;
  incomingToolCallId?: string | null;
}): boolean {
  const { existingLog, incomingEventType, incomingSequence, incomingToolCallId } = input;
  if (!existingLog || existingLog.type !== "tool") {
    return false;
  }

  const existingCallId = extractExistingToolCallId(existingLog);
  const normalizedIncomingCallId =
    typeof incomingToolCallId === "string" ? incomingToolCallId.trim() : "";
  if (existingCallId && normalizedIncomingCallId && existingCallId !== normalizedIncomingCallId) {
    return false;
  }

  const existingSequence = toFiniteSequence(
    existingLog.detail && typeof existingLog.detail === "object"
      ? existingLog.detail.sequence
      : null,
  );
  const nextSequence = toFiniteSequence(incomingSequence);
  if (
    existingSequence !== null &&
    nextSequence !== null &&
    nextSequence < existingSequence
  ) {
    return true;
  }

  const normalizedEventType = String(incomingEventType || "").trim().toLowerCase();
  const normalizedStatus = String(existingLog.tool?.status || "").trim().toLowerCase();
  const isTerminalToolStatus =
    normalizedStatus === "completed" ||
    normalizedStatus === "failed" ||
    normalizedStatus === "cancelled";

  return Boolean(
    isTerminalToolStatus &&
    (normalizedEventType === "tool_call" || normalizedEventType === "tool_call_start") &&
    existingCallId &&
    normalizedIncomingCallId &&
    existingCallId === normalizedIncomingCallId &&
    (nextSequence === null || existingSequence === null || nextSequence <= existingSequence),
  );
}

export function computeContainerAnchorScrollTop(input: {
  containerScrollTop: number;
  containerClientHeight: number;
  containerTop: number;
  anchorTop: number;
  anchorHeight: number;
}): number {
  const {
    containerScrollTop,
    containerClientHeight,
    containerTop,
    anchorTop,
    anchorHeight,
  } = input;

  if (
    !Number.isFinite(containerClientHeight) ||
    containerClientHeight <= 0 ||
    !Number.isFinite(containerScrollTop) ||
    !Number.isFinite(containerTop) ||
    !Number.isFinite(anchorTop)
  ) {
    return Number.isFinite(containerScrollTop) ? containerScrollTop : 0;
  }

  const safeAnchorHeight =
    Number.isFinite(anchorHeight) && anchorHeight > 0 ? anchorHeight : 0;
  const relativeAnchorTop = anchorTop - containerTop + containerScrollTop;
  const visibleTop = containerScrollTop;
  const visibleBottom = containerScrollTop + containerClientHeight;
  const anchorBottom = relativeAnchorTop + safeAnchorHeight;

  if (relativeAnchorTop >= visibleTop && anchorBottom <= visibleBottom) {
    return containerScrollTop;
  }

  const centeredTarget =
    relativeAnchorTop - containerClientHeight / 2 + safeAnchorHeight / 2;
  return Math.max(0, Math.round(centeredTarget));
}

/**
 * Clean thinking content (extract only the Thought part, remove Action/Action Input)
 */
export function cleanThinkingContent(content: string): string {
  if (!content) return "";

  let cleaned = content;

  // 1. 尝试提取 Thought: 后面的内容
  const thoughtMatch = cleaned.match(
    /Thought:\s*([\s\S]*?)(?=\n\s*Action\s*:|$)/i,
  );
  if (thoughtMatch && thoughtMatch[1]) {
    cleaned = thoughtMatch[1].trim();
  } else {
    // 2. 如果没有 Thought: 前缀，尝试移除 Action 部分
    // 匹配 Action: 及其后面的所有内容（包括开头的 Action）
    cleaned = cleaned.replace(/^Action\s*:[\s\S]*$/i, "");
    cleaned = cleaned.replace(/\n\s*Action\s*:[\s\S]*$/i, "");
  }

  // 3. 移除可能残留的 Action Input 部分
  cleaned = cleaned.replace(/Action\s*Input\s*:[\s\S]*$/i, "");

  // 4. 清理空白和特殊字符
  cleaned = cleaned.trim();

  // 5. 如果清理后只剩下 "Action" 或类似的碎片，返回空
  if (/^Action\s*$/i.test(cleaned) || cleaned.length < 5) {
    return "";
  }

  return cleaned;
}

/**
 * Truncate output string
 */
export function truncateOutput(
  output: string,
  maxLength: number = 1000,
): string {
  void maxLength;
  return output;
}

/**
 * Calculate severity counts from findings
 */
export function calculateSeverityCounts(
  findings: { severity: string }[],
): Record<string, number> {
  return {
    critical: findings.filter((f) => f.severity === "critical").length,
    high: findings.filter((f) => f.severity === "high").length,
    medium: findings.filter((f) => f.severity === "medium").length,
    low: findings.filter((f) => f.severity === "low").length,
  };
}

/**
 * Check if task is in running state
 */
export function isTaskRunning(status: string | undefined): boolean {
  return status === "running" || status === "pending";
}

/**
 * Check if task is complete
 */
export function isTaskComplete(status: string | undefined): boolean {
  return isAgentAuditTerminalStatus(status);
}

/**
 * Format token count
 */
export function formatTokens(tokens: number): string {
  return (tokens / 1000).toFixed(1) + "k";
}

/**
 * Filter logs by agent
 */
export function filterLogsByAgent(
  logs: LogItem[],
  selectedAgentId: string | null,
  treeNodes: AgentTreeNode[],
  showAllLogs: boolean,
): LogItem[] {
  if (showAllLogs || !selectedAgentId) {
    return logs;
  }

  const selectedAgentName = findAgentName(treeNodes, selectedAgentId);
  if (!selectedAgentName) return logs;

  return logs.filter(
    (log) =>
      log.agentRawName?.toLowerCase() === selectedAgentName.toLowerCase() ||
      log.agentRawName
        ?.toLowerCase()
        .includes(selectedAgentName.toLowerCase().split("_")[0]),
  );
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}
