import type { FindingNarrativeInput } from "@/pages/AgentAudit/components/findingNarrative";
import type { FindingCodeWindowDisplayLine } from "@/pages/AgentAudit/components/FindingCodeWindow";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type { BanditFinding } from "@/shared/api/bandit";
import type { GitleaksFinding } from "@/shared/api/gitleaks";
import type {
  OpengrepFinding,
  OpengrepFindingContext,
} from "@/shared/api/opengrep";

const CODE_CONTEXT_PADDING = 3;
const ELLIPSIS_PLACEHOLDER = "// ....";
const MISSING_VALUE = "未提供";
const MISSING_SEVERITY = "未分级";
const MISSING_DESCRIPTION = "当前来源未提供扫描说明，请结合命中代码与追踪信息复核。";

type FindingDetailTone = "danger" | "warning" | "info" | "success" | "muted";

export type FindingDetailCodeView = {
  id: string;
  title: string;
  filePath: string | null;
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
  highlightStartLine: number | null;
  highlightEndLine: number | null;
  focusLine: number | null;
  displayLines?: FindingCodeWindowDisplayLine[];
};

export type FindingDetailSummaryStat = {
  label: string;
  value: string;
  tone: FindingDetailTone;
};

export type FindingDetailTrackingItem = {
  label: string;
  value: string;
  mono?: boolean;
};

export type FindingDetailRootCause = {
  title: string;
  finding?: FindingNarrativeInput | null;
  body?: string | null;
};

export type FindingDetailPageModel = {
  pageTitle: string;
  codePanelTitle: string;
  emptyCodeMessage: string;
  sourceLabel: string;
  statusLabel: string;
  heroEyebrow: string;
  heroTitle: string;
  heroSubtitle: string | null;
  helperLocation: string | null;
  summaryStats: FindingDetailSummaryStat[];
  rootCause: FindingDetailRootCause;
  trackingItems: FindingDetailTrackingItem[];
  codeSections: FindingDetailCodeView[];
};

function normalizeToken(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function normalizeUpper(value: unknown): string {
  return String(value || "").trim().toUpperCase();
}

function splitCodeLines(code: string): string[] {
  return String(code || "").replace(/\r\n/g, "\n").split("\n");
}

function isFiniteLineNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatLocation(params: {
  filePath?: string | null;
  lineStart?: number | null;
  lineEnd?: number | null;
}): string | null {
  const filePath = String(params.filePath || "").trim();
  if (!filePath) return null;
  const lineStart = isFiniteLineNumber(params.lineStart) ? params.lineStart : null;
  const lineEnd = isFiniteLineNumber(params.lineEnd) ? params.lineEnd : null;
  if (lineStart !== null && lineEnd !== null && lineEnd > lineStart) {
    return `${filePath}:${lineStart}-${lineEnd}`;
  }
  if (lineStart !== null) {
    return `${filePath}:${lineStart}`;
  }
  return filePath;
}

function buildTrackingItems(params: {
  sourceLabel: string;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  location?: string | null;
}): FindingDetailTrackingItem[] {
  const items: FindingDetailTrackingItem[] = [
    { label: "来源", value: params.sourceLabel },
  ];

  const taskName = String(params.taskName || "").trim();
  if (taskName) {
    items.push({ label: "任务名称", value: taskName });
  }

  items.push(
    { label: "任务 ID", value: params.taskId || "-", mono: true },
    { label: "缺陷 ID", value: params.findingId || "-", mono: true },
  );

  const location = String(params.location || "").trim();
  if (location) {
    items.push({ label: "文件位置", value: location, mono: true });
  }

  return items;
}

function resolveSeverityDisplay(value: unknown): { label: string; tone: FindingDetailTone } {
  const normalized = normalizeUpper(value);
  if (normalized === "CRITICAL" || normalized === "ERROR") {
    return { label: "严重", tone: "danger" };
  }
  if (normalized === "HIGH" || normalized === "WARNING") {
    return { label: "高危", tone: "warning" };
  }
  if (normalized === "MEDIUM" || normalized === "INFO") {
    return { label: "中危", tone: "info" };
  }
  if (normalized === "LOW") return { label: "低危", tone: "success" };
  return { label: MISSING_SEVERITY, tone: "muted" };
}

function resolveTextConfidenceDisplay(value: unknown): {
  label: string;
  tone: FindingDetailTone;
} {
  const normalized = normalizeUpper(value);
  if (normalized === "HIGH") return { label: "高", tone: "success" };
  if (normalized === "MEDIUM") return { label: "中", tone: "warning" };
  if (normalized === "LOW") return { label: "低", tone: "info" };
  return { label: MISSING_VALUE, tone: "muted" };
}

function resolveNumericConfidenceDisplay(value: number | null | undefined): {
  label: string;
  tone: FindingDetailTone;
} {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return { label: MISSING_VALUE, tone: "muted" };
  }
  if (value >= 0.8) return { label: "高", tone: "success" };
  if (value >= 0.5) return { label: "中", tone: "warning" };
  if (value > 0) return { label: "低", tone: "info" };
  return { label: MISSING_VALUE, tone: "muted" };
}

function buildStatusLabel(value: unknown): string {
  const normalized = normalizeUpper(value);
  return normalized || MISSING_VALUE;
}

function resolveAgentConfidenceValue(finding: AgentFinding): number | null {
  if (typeof finding.ai_confidence === "number" && Number.isFinite(finding.ai_confidence)) {
    return finding.ai_confidence;
  }
  if (typeof finding.confidence === "number" && Number.isFinite(finding.confidence)) {
    return finding.confidence;
  }
  return null;
}

function parseStaticEndLine(finding: OpengrepFinding): number | null {
  const rule = finding.rule as {
    end?: { line?: number | string | null } | null;
  } | null;
  const raw = Number(rule?.end?.line);
  if (Number.isFinite(raw) && raw > 0) return raw;
  return isFiniteLineNumber(finding.start_line) ? finding.start_line : null;
}

function getActualLineEnd(view: FindingDetailCodeView, lineCount: number): number | null {
  if (!isFiniteLineNumber(view.lineStart)) return null;
  if (isFiniteLineNumber(view.lineEnd)) {
    const expected = view.lineEnd - view.lineStart + 1;
    if (expected === lineCount) {
      return view.lineEnd;
    }
  }
  return view.lineStart + lineCount - 1;
}

export function isAgentFalsePositiveFinding(finding: AgentFinding | null): boolean {
  if (!finding) return false;
  return (
    normalizeToken(finding.authenticity) === "false_positive" ||
    normalizeToken(finding.status) === "false_positive"
  );
}

export function getAgentFalsePositiveEvidence(finding: AgentFinding | null): string {
  if (!finding) return "未生成详细判定说明";
  const evidence = String(finding.verification_evidence || "").trim();
  if (evidence) return evidence;
  const description = String(finding.description || "").trim();
  if (description) return description;
  return "未生成详细判定说明";
}

export function buildFindingDetailCodeSections(
  codeViews: FindingDetailCodeView[],
): FindingDetailCodeView[] {
  return codeViews.map((view) => {
    const lines = splitCodeLines(view.code);
    const lineStart = isFiniteLineNumber(view.lineStart) ? view.lineStart : null;
    const actualEnd = getActualLineEnd(view, lines.length);
    const highlightStart = isFiniteLineNumber(view.highlightStartLine)
      ? view.highlightStartLine
      : null;
    const highlightEnd = isFiniteLineNumber(view.highlightEndLine)
      ? view.highlightEndLine
      : null;
    const focusLine = isFiniteLineNumber(view.focusLine) ? view.focusLine : highlightStart;
    const highlightSpan =
      highlightStart !== null && highlightEnd !== null ? highlightEnd - highlightStart + 1 : null;

    if (
      lineStart === null ||
      actualEnd === null ||
      highlightStart === null ||
      highlightEnd === null ||
      highlightStart < lineStart ||
      highlightEnd > actualEnd ||
      highlightSpan === null ||
      highlightSpan <= 1
    ) {
      return { ...view };
    }

    const keepStart = Math.max(lineStart, highlightStart - CODE_CONTEXT_PADDING);
    const keepEnd = Math.min(actualEnd, highlightEnd + CODE_CONTEXT_PADDING);

    if (keepStart === lineStart && keepEnd === actualEnd) {
      return { ...view };
    }

    const displayLines: FindingCodeWindowDisplayLine[] = [];

    if (keepStart > lineStart) {
      displayLines.push({
        lineNumber: null,
        content: ELLIPSIS_PLACEHOLDER,
        kind: "placeholder",
      });
    }

    for (let currentLine = keepStart; currentLine <= keepEnd; currentLine += 1) {
      displayLines.push({
        lineNumber: currentLine,
        content: lines[currentLine - lineStart] ?? "",
        kind: "code",
        isHighlighted: currentLine >= highlightStart && currentLine <= highlightEnd,
        isFocus: focusLine !== null && currentLine === focusLine,
      });
    }

    if (keepEnd < actualEnd) {
      displayLines.push({
        lineNumber: null,
        content: ELLIPSIS_PLACEHOLDER,
        kind: "placeholder",
      });
    }

    return {
      ...view,
      displayLines,
    };
  });
}

export function buildOpengrepFindingCodeViews(
  finding: OpengrepFinding,
  context: OpengrepFindingContext | null,
): FindingDetailCodeView[] {
  if (context && Array.isArray(context.lines) && context.lines.length > 0) {
    const sortedLines = [...context.lines].sort((a, b) => a.line_number - b.line_number);
    const hitLines = sortedLines.filter((line) => line.is_hit).map((line) => line.line_number);
    const lineStart = sortedLines[0]?.line_number ?? context.start_line;
    const lineEnd = sortedLines[sortedLines.length - 1]?.line_number ?? context.end_line;
    return [
      {
        id: `static:${finding.id}`,
        title: "命中代码",
        filePath: context.file_path || finding.file_path || null,
        code: sortedLines.map((line) => line.content || "").join("\n"),
        lineStart,
        lineEnd,
        highlightStartLine:
          hitLines[0] ?? context.start_line ?? finding.start_line ?? null,
        highlightEndLine:
          hitLines[hitLines.length - 1] ??
          context.end_line ??
          parseStaticEndLine(finding) ??
          finding.start_line ??
          null,
        focusLine: hitLines[0] ?? finding.start_line ?? context.start_line ?? lineStart ?? null,
      },
    ];
  }

  const fallbackCode = String(finding.code_snippet || "").trim();
  if (!fallbackCode) return [];
  return [
    {
      id: `static:${finding.id}`,
      title: "命中代码",
      filePath: finding.file_path || null,
      code: fallbackCode,
      lineStart: finding.start_line ?? null,
      lineEnd: parseStaticEndLine(finding),
      highlightStartLine: finding.start_line ?? null,
      highlightEndLine: parseStaticEndLine(finding),
      focusLine: finding.start_line ?? null,
    },
  ];
}

export function buildGitleaksFindingCodeViews(
  finding: GitleaksFinding,
): FindingDetailCodeView[] {
  const content = String(finding.match || finding.secret || "").trim();
  if (!content) return [];
  return [
    {
      id: `gitleaks:${finding.id}`,
      title: "命中内容",
      filePath: finding.file_path || null,
      code: content,
      lineStart: finding.start_line ?? null,
      lineEnd: finding.end_line ?? finding.start_line ?? null,
      highlightStartLine: finding.start_line ?? null,
      highlightEndLine: finding.end_line ?? finding.start_line ?? null,
      focusLine: finding.start_line ?? null,
    },
  ];
}

export function buildBanditFindingCodeViews(finding: BanditFinding): FindingDetailCodeView[] {
  const content = String(finding.code || "").trim();
  if (!content) return [];
  return [
    {
      id: `bandit:${finding.id}`,
      title: "风险代码",
      filePath: finding.file_path || null,
      code: content,
      lineStart: finding.line_number ?? null,
      lineEnd: finding.line_number ?? null,
      highlightStartLine: finding.line_number ?? null,
      highlightEndLine: finding.line_number ?? null,
      focusLine: finding.line_number ?? null,
    },
  ];
}

export function buildAgentFindingCodeViews(finding: AgentFinding): FindingDetailCodeView[] {
  const contextCode = String(finding.code_context || "").trim();
  const snippetCode = String(finding.code_snippet || "").trim();
  const code = contextCode || snippetCode;
  if (!code) return [];

  const lineStart = isFiniteLineNumber(finding.context_start_line)
    ? finding.context_start_line
    : finding.line_start;
  const lineEnd = isFiniteLineNumber(finding.context_end_line)
    ? finding.context_end_line
    : finding.line_end;

  return [
    {
      id: `agent:${finding.id}`,
      title: contextCode ? "命中代码" : "命中片段",
      filePath: finding.file_path,
      code,
      lineStart: lineStart ?? null,
      lineEnd: lineEnd ?? lineStart ?? null,
      highlightStartLine: finding.line_start ?? lineStart ?? null,
      highlightEndLine: finding.line_end ?? lineEnd ?? lineStart ?? null,
      focusLine: finding.line_start ?? lineStart ?? null,
    },
  ];
}

function buildAgentNarrativeFinding(finding: AgentFinding): FindingNarrativeInput {
  return {
    description: finding.description,
    description_markdown: finding.description_markdown,
    code_snippet: finding.code_snippet,
    code_context: finding.code_context,
    file_path: finding.file_path,
    line_start: finding.line_start,
    line_end: finding.line_end,
    function_trigger_flow: finding.function_trigger_flow,
    verification_evidence: finding.verification_evidence,
    reachability_file: finding.reachability_file,
    reachability_function: finding.reachability_function,
    reachability_function_start_line: finding.reachability_function_start_line,
    reachability_function_end_line: finding.reachability_function_end_line,
  };
}

function buildBaseModel(params: {
  pageTitle: string;
  codePanelTitle: string;
  emptyCodeMessage: string;
  sourceLabel: string;
  statusLabel: string;
  heroEyebrow: string;
  heroTitle: string;
  heroSubtitle?: string | null;
  helperLocation?: string | null;
  summaryStats: FindingDetailSummaryStat[];
  rootCause: FindingDetailRootCause;
  trackingItems: FindingDetailTrackingItem[];
  codeSections: FindingDetailCodeView[];
}): FindingDetailPageModel {
  return {
    pageTitle: params.pageTitle,
    codePanelTitle: params.codePanelTitle,
    emptyCodeMessage: params.emptyCodeMessage,
    sourceLabel: params.sourceLabel,
    statusLabel: params.statusLabel,
    heroEyebrow: params.heroEyebrow,
    heroTitle: params.heroTitle,
    heroSubtitle: params.heroSubtitle ?? null,
    helperLocation: params.helperLocation ?? null,
    summaryStats: params.summaryStats,
    rootCause: params.rootCause,
    trackingItems: params.trackingItems,
    codeSections: params.codeSections,
  };
}

export function buildAgentFindingDetailModel(params: {
  finding: AgentFinding;
  taskId: string;
  findingId: string;
}): FindingDetailPageModel {
  const { finding } = params;
  const isFalsePositive = isAgentFalsePositiveFinding(finding);
  const severity = resolveSeverityDisplay(finding.severity);
  const confidence = resolveNumericConfidenceDisplay(resolveAgentConfidenceValue(finding));
  const location = formatLocation({
    filePath: finding.file_path,
    lineStart: finding.line_start,
    lineEnd: finding.line_end,
  });
  const typeLabel = String(finding.vulnerability_type || "").trim() || MISSING_VALUE;
  const trackingItems = buildTrackingItems({
    sourceLabel: "智能扫描",
    taskId: params.taskId,
    findingId: params.findingId,
    location,
  });
  const codeSections = buildFindingDetailCodeSections(buildAgentFindingCodeViews(finding));

  if (isFalsePositive) {
    return buildBaseModel({
      pageTitle: "误报判定依据",
      codePanelTitle: "关联代码 / 命中位置",
      emptyCodeMessage: "该误报未保留可展示代码，仅提供判定结论。",
      sourceLabel: "智能扫描",
      statusLabel: buildStatusLabel(finding.status || "false_positive"),
      heroEyebrow: "验证结论",
      heroTitle: "该问题已在验证阶段判定为误报",
      heroSubtitle:
        [typeLabel, String(finding.display_title || finding.title || "").trim()]
          .filter(Boolean)
          .join(" · ") || null,
      helperLocation: location,
      summaryStats: [
        { label: "漏洞类型", value: typeLabel, tone: "info" },
        { label: "漏洞危害", value: severity.label, tone: severity.tone },
        { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
      ],
      rootCause: {
        title: "判定依据",
        body: getAgentFalsePositiveEvidence(finding),
      },
      trackingItems,
      codeSections,
    });
  }

  return buildBaseModel({
    pageTitle: "统一缺陷详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: "暂无可展示的命中代码。",
    sourceLabel: "智能扫描",
    statusLabel: buildStatusLabel(finding.status),
    heroEyebrow: "漏洞类型",
    heroTitle: typeLabel,
    heroSubtitle: String(finding.display_title || finding.title || "").trim() || null,
    helperLocation: location,
    summaryStats: [
      { label: "漏洞危害", value: severity.label, tone: severity.tone },
      { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
    ],
    rootCause: {
      title: "根因说明",
      finding: buildAgentNarrativeFinding(finding),
    },
    trackingItems,
    codeSections,
  });
}

export function buildOpengrepFindingDetailModel(params: {
  finding: OpengrepFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  context?: OpengrepFindingContext | null;
}): FindingDetailPageModel {
  const { finding } = params;
  const severity = resolveSeverityDisplay(finding.severity);
  const confidence = resolveTextConfidenceDisplay(finding.confidence);
  const location = formatLocation({
    filePath: finding.file_path,
    lineStart: finding.start_line,
    lineEnd: parseStaticEndLine(finding),
  });
  const typeLabel = String(finding.rule_name || "").trim() || "unknown-rule";

  return buildBaseModel({
    pageTitle: "统一缺陷详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: "暂无可展示的命中代码。",
    sourceLabel: "静态扫描 · Opengrep",
    statusLabel: buildStatusLabel(finding.status),
    heroEyebrow: "漏洞类型",
    heroTitle: typeLabel,
    heroSubtitle: null,
    helperLocation: location,
    summaryStats: [
      { label: "漏洞危害", value: severity.label, tone: severity.tone },
      { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
    ],
    rootCause: {
      title: "扫描说明",
      body: String(finding.description || "").trim() || MISSING_DESCRIPTION,
    },
    trackingItems: buildTrackingItems({
      sourceLabel: "静态扫描 · Opengrep",
      taskId: params.taskId,
      findingId: params.findingId,
      taskName: params.taskName,
      location,
    }),
    codeSections: buildFindingDetailCodeSections(
      buildOpengrepFindingCodeViews(finding, params.context ?? null),
    ),
  });
}

export function buildGitleaksFindingDetailModel(params: {
  finding: GitleaksFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
}): FindingDetailPageModel {
  const { finding } = params;
  const location = formatLocation({
    filePath: finding.file_path,
    lineStart: finding.start_line,
    lineEnd: finding.end_line,
  });

  return buildBaseModel({
    pageTitle: "统一缺陷详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: "暂无可展示的命中代码。",
    sourceLabel: "静态扫描 · Gitleaks",
    statusLabel: buildStatusLabel(finding.status),
    heroEyebrow: "漏洞类型",
    heroTitle: String(finding.rule_id || "").trim() || "gitleaks-rule",
    heroSubtitle: null,
    helperLocation: location,
    summaryStats: [
      { label: "漏洞危害", value: MISSING_SEVERITY, tone: "muted" },
      { label: "漏洞置信度", value: MISSING_VALUE, tone: "muted" },
    ],
    rootCause: {
      title: "扫描说明",
      body: String(finding.description || "").trim() || MISSING_DESCRIPTION,
    },
    trackingItems: buildTrackingItems({
      sourceLabel: "静态扫描 · Gitleaks",
      taskId: params.taskId,
      findingId: params.findingId,
      taskName: params.taskName,
      location,
    }),
    codeSections: buildFindingDetailCodeSections(buildGitleaksFindingCodeViews(finding)),
  });
}

export function buildBanditFindingDetailModel(params: {
  finding: BanditFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
}): FindingDetailPageModel {
  const { finding } = params;
  const severity = resolveSeverityDisplay(finding.issue_severity);
  const confidence = resolveTextConfidenceDisplay(finding.issue_confidence);
  const location = formatLocation({
    filePath: finding.file_path,
    lineStart: finding.line_number,
    lineEnd: finding.line_number,
  });
  const heroTitle = [
    String(finding.test_id || "").trim(),
    String(finding.test_name || "").trim(),
  ]
    .filter(Boolean)
    .join(" · ");

  return buildBaseModel({
    pageTitle: "统一缺陷详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: "暂无可展示的命中代码。",
    sourceLabel: "静态扫描 · Bandit",
    statusLabel: buildStatusLabel(finding.status),
    heroEyebrow: "漏洞类型",
    heroTitle: heroTitle || "bandit-rule",
    heroSubtitle: null,
    helperLocation: location,
    summaryStats: [
      { label: "漏洞危害", value: severity.label, tone: severity.tone },
      { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
    ],
    rootCause: {
      title: "扫描说明",
      body:
        String(finding.issue_text || "").trim() ||
        String(finding.more_info || "").trim() ||
        MISSING_DESCRIPTION,
    },
    trackingItems: buildTrackingItems({
      sourceLabel: "静态扫描 · Bandit",
      taskId: params.taskId,
      findingId: params.findingId,
      taskName: params.taskName,
      location,
    }),
    codeSections: buildFindingDetailCodeSections(buildBanditFindingCodeViews(finding)),
  });
}
