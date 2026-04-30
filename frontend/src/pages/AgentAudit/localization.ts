export type AuditSeverityKey =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "invalid";

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

const STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "中止",
  canceled: "已取消",
  pending: "待处理",
  waiting: "等待中",
  created: "已创建",
};

export function toZhAgentName(raw: string): string {
  const text = String(raw || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower.includes("orchestrator")) return "编排智能体";
  if (lower.includes("reconnaissance") || lower.includes("recon")) {
    return "侦查智能体";
  }
  if (lower.includes("analysis")) return "分析智能体";
  if (lower.includes("verification")) return "验证智能体";
  return text;
}

export function normalizeSeverityKey(raw: unknown): AuditSeverityKey {
  const normalized = String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/^[\[\(\{<\s]+|[\]\)\}>\s]+$/g, "")
    .replace(/[-\s]+/g, "_");

  if (
    normalized === "critical" ||
    normalized === "严重"
  ) {
    return "critical";
  }
  if (
    normalized === "high" ||
    normalized === "高危" ||
    normalized === "高"
  ) {
    return "high";
  }
  if (
    normalized === "medium" ||
    normalized === "中危" ||
    normalized === "中"
  ) {
    return "medium";
  }
  if (
    normalized === "low" ||
    normalized === "低危" ||
    normalized === "低" ||
    normalized === "info" ||
    normalized === "informational" ||
    normalized === "信息"
  ) {
    return "low";
  }
  if (
    normalized === "invalid" ||
    normalized === "无效" ||
    normalized === "false_positive" ||
    normalized === "falsepositive"
  ) {
    return "invalid";
  }
  return "medium";
}

export function toZhSeverityLabel(raw: unknown): string {
  const normalized = normalizeSeverityKey(raw);
  if (normalized === "critical") return "严重";
  if (normalized === "high") return "高危";
  if (normalized === "medium") return "中危";
  if (normalized === "low") return "低危";
  return "无效";
}

export function localizeAuditText(text: string): string {
  if (!text) return "";
  return String(text)
    .replace(/\borchestrator\b/gi, "编排智能体")
    .replace(/\breconnaissance\b/gi, "侦查智能体")
    .replace(/\brecon\b/gi, "侦查智能体")
    .replace(/\banalysis\b/gi, "分析智能体")
    .replace(/\bverification\b/gi, "验证智能体")
    .replace(
      /\b(critical|high|medium|low|invalid|informational|info)\b/gi,
      (matched) => toZhSeverityLabel(matched),
    );
}

export function toZhLogType(raw: string): string {
  const key = String(raw || "").trim().toLowerCase();
  if (!key) return "";
  return LOG_TYPE_LABELS[key] || raw;
}

export function toZhStatus(raw: string): string {
  const key = String(raw || "").trim().toLowerCase();
  if (!key) return "";
  return STATUS_LABELS[key] || raw;
}

type EventLogPhaseLabel =
  | "初始化"
  | "编排"
  | "侦查"
  | "分析"
  | "完成";

const PHASE_LABEL_SET = new Set<EventLogPhaseLabel>([
  "初始化",
  "编排",
  "侦查",
  "分析",
  "完成",
]);

function toPhaseKey(raw: unknown): string {
  return String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

function toAllowedPhaseLabel(raw: unknown): EventLogPhaseLabel | null {
  const label = String(raw ?? "").trim();
  if (!label) return null;
  return PHASE_LABEL_SET.has(label as EventLogPhaseLabel)
    ? (label as EventLogPhaseLabel)
    : null;
}

export function normalizeEventLogPhaseLabel(input: {
  rawPhase?: unknown;
  eventType?: unknown;
  taskStatus?: unknown;
  message?: unknown;
  fallbackPhaseLabel?: string | null;
}): EventLogPhaseLabel | null {
  const taskStatus = toPhaseKey(input.taskStatus);
  const eventType = toPhaseKey(input.eventType);
  const rawPhase = toPhaseKey(input.rawPhase);
  const message = String(input.message ?? "").trim();

  if (
    taskStatus === "completed" &&
    (eventType === "task_complete" || eventType === "complete")
  ) {
    return "完成";
  }

  if (
    rawPhase === "preparation" ||
    rawPhase === "planning" ||
    rawPhase === "indexing" ||
    rawPhase === "init" ||
    rawPhase === "initialization"
  ) {
    return "初始化";
  }

  if (rawPhase === "orchestration" || rawPhase === "orchestrator") {
    return "编排";
  }

  if (
    rawPhase === "recon" ||
    rawPhase === "reconnaissance" ||
    rawPhase === "business_logic_recon"
  ) {
    return "侦查";
  }

  if (
    rawPhase === "analysis" ||
    rawPhase === "business_logic_analysis" ||
    rawPhase === "verification" ||
    rawPhase === "report" ||
    rawPhase === "reporting"
  ) {
    return "分析";
  }

  if (
    (eventType === "info" || eventType === "progress") &&
    /任务开始执行|开始执行|执行准备|准备阶段|索引/.test(message)
  ) {
    return "初始化";
  }

  return toAllowedPhaseLabel(input.fallbackPhaseLabel);
}
