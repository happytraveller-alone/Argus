import type { FindingNarrativeInput } from "@/pages/AgentAudit/components/findingNarrative";
import type { FindingCodeWindowDisplayLine } from "@/pages/AgentAudit/components/FindingCodeWindow";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type {
  OpengrepFinding,
  OpengrepFindingContext,
} from "@/shared/api/opengrep";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import type { ProjectSourceType } from "@/shared/types";

const CODE_CONTEXT_PADDING = 3;
const ELLIPSIS_PLACEHOLDER = "// ....";
const MISSING_VALUE = "未提供";
const MISSING_SEVERITY = "未分级";
const MISSING_DESCRIPTION = "当前来源未提供扫描说明，请结合命中代码与追踪信息复核。";
const MISSING_MARKDOWN_SECTION = "未提供此部分。";
const MISSING_AGENT_CODE_EVIDENCE = "暂无可展示的命中代码。";
const MARKDOWN_SECTION_HEADING_RE = /^###\s+(.+?)\s*$/gm;

type FindingDetailTone = "danger" | "warning" | "info" | "success" | "muted";

export type FindingDetailFullFileRequest = {
  projectId: string;
  filePath: string;
};

export type FindingDetailCodeView = {
  id: string;
  title: string;
  filePath: string | null;
  displayFilePath?: string;
  locationLabel?: string;
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
  highlightStartLine: number | null;
  highlightEndLine: number | null;
  focusLine: number | null;
  displayLines?: FindingCodeWindowDisplayLine[];
  relatedLines?: FindingCodeWindowDisplayLine[];
  fullFileAvailable?: boolean;
  fullFileRequest?: FindingDetailFullFileRequest | null;
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
  title?: string | null;
};

export type FindingDetailNarrativeSection = {
  id: string;
  title: string;
  emphasis?: "primary" | "secondary" | "success" | "neutral";
  finding?: FindingNarrativeInput | null;
  body?: string | null;
};

export type FindingDetailPageModel = {
  pageTitle: string;
  codePanelTitle: string;
  emptyCodeMessage: string;
  narrativeSections: FindingDetailNarrativeSection[];
  trackingItems: FindingDetailTrackingItem[];
  overviewItems: FindingDetailTrackingItem[];
  codeSections: FindingDetailCodeView[];
  codeBrowserTarget: {
    filePath: string | null;
    line: number | null;
  } | null;
};

export function isFindingDetailFullFilePathSupported(
  filePath: string | null | undefined,
): boolean {
  let normalized = String(filePath || "").trim().replace(/\\/g, "/");
  if (!normalized) return false;

  while (normalized.startsWith("./")) {
    normalized = normalized.slice(2);
  }

  if (!normalized) return false;
  if (normalized.startsWith("/")) return false;
  if (/^[a-z]:\//i.test(normalized)) return false;

  const lowered = normalized.toLowerCase();
  if (lowered.startsWith("tmp/Argus_")) return false;
  return true;
}

function normalizeFindingDetailFullFilePath(
  filePath: string | null | undefined,
): string | null {
  if (!isFindingDetailFullFilePathSupported(filePath)) return null;

  let normalized = String(filePath || "").trim().replace(/\\/g, "/");
  while (normalized.startsWith("./")) {
    normalized = normalized.slice(2);
  }
  return normalized || null;
}

function normalizeToken(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function normalizeUpper(value: unknown): string {
  return String(value || "").trim().toUpperCase();
}

function splitCodeLines(code: string): string[] {
  return String(code || "").replace(/\r\n/g, "\n").split("\n");
}

function buildLineLabel(lineStart: number | null, lineEnd: number | null): string {
  if (isFiniteLineNumber(lineStart) && isFiniteLineNumber(lineEnd) && lineEnd > lineStart) {
    return `第 ${lineStart}-${lineEnd} 行`;
  }
  if (isFiniteLineNumber(lineStart)) {
    return `第 ${lineStart} 行`;
  }
  return "行号未提供";
}

function buildDisplayFilePath(filePath: string | null | undefined, projectName?: string | null): string {
  const trimmed = String(filePath || "").trim();
  if (!trimmed) return "未定位文件";

  const normalized = trimmed.replace(/\\/g, "/").replace(/^\/+/, "");
  const segments = normalized.split("/").filter(Boolean);
  if (segments.length === 0) return trimmed;

  const sourceRootSegments = new Set(["src", "include", "lib", "app", "apps", "test", "tests"]);
  const sourceRootIndex = segments.findIndex((segment) =>
    sourceRootSegments.has(segment.toLowerCase()),
  );

  const projectNameLower = String(projectName || "").trim().toLowerCase();
  if (projectNameLower) {
    const projectIndex = segments.findIndex((segment) => segment.toLowerCase() === projectNameLower);
    const isProjectRootPrefix =
      projectIndex >= 0 &&
      projectIndex < segments.length - 1 &&
      (sourceRootIndex < 0 ? projectIndex <= 1 : projectIndex < sourceRootIndex);
    if (isProjectRootPrefix) {
      return segments.slice(projectIndex + 1).join("/");
    }
  }
  if (sourceRootIndex >= 0) {
    return segments.slice(sourceRootIndex).join("/");
  }

  return normalized;
}

function isFiniteLineNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function buildCodeBrowserTarget(params: {
  filePath?: string | null;
  line?: number | null;
}): FindingDetailPageModel["codeBrowserTarget"] {
  const rawFilePath = normalizeFindingDetailFullFilePath(params.filePath);
  const line = isFiniteLineNumber(params.line) && params.line > 0 ? params.line : null;
  if (!rawFilePath && line === null) return null;
  return {
    filePath: rawFilePath || null,
    line,
  };
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

function resolvePreferredFilePath(
  rawFilePath: string | null | undefined,
  resolvedFilePath?: string | null,
): string | null {
  const preferred = String(resolvedFilePath || "").trim();
  if (preferred) return preferred;
  const fallback = String(rawFilePath || "").trim();
  return fallback || null;
}

function resolvePreferredLineStart(
  fallbackLineStart: number | null | undefined,
  resolvedLineStart?: number | null,
): number | null {
  if (isFiniteLineNumber(resolvedLineStart)) {
    return resolvedLineStart;
  }
  return isFiniteLineNumber(fallbackLineStart) ? fallbackLineStart : null;
}

function buildTrackingItems(params: {
  sourceLabel: string;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  location?: string | null;
  includeSource?: boolean;
}): FindingDetailTrackingItem[] {
  const items: FindingDetailTrackingItem[] = [];

  if (params.includeSource !== false) {
    items.push({ label: "来源", value: params.sourceLabel });
  }

  // const taskName = String(params.taskName || "").trim();
  // if (taskName) {
  //   items.push({ label: "任务名称", value: taskName });
  // }

  items.push(
    { label: "任务 ID", value: params.taskId || "-", mono: true },
    { label: "漏洞 ID", value: params.findingId || "-", mono: true },
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
  const raw = String(value || "").trim();
  if (!raw) return MISSING_VALUE;

  const normalized = normalizeToken(raw).replace(/[\s-]+/g, "_");
  if (normalized === "verified" || normalized === "confirmed") return "确报";
  if (
    normalized === "open" ||
    normalized === "pending" ||
    normalized === "needs_review" ||
    normalized === "likely" ||
    normalized === "uncertain" ||
    normalized === "new" ||
    normalized === "analyzing"
  ) {
    return "待确认";
  }
  if (normalized === "false_positive") return "误报";
  if (normalized === "closed") return "已关闭";
  if (normalized === "resolved") return "已处理";
  return raw;
}

function buildOverviewItems(params: {
  headlineLabel: string;
  headlineValue: string;
  headlineTitle?: string | null;
  summaryStats: FindingDetailSummaryStat[];
}): FindingDetailTrackingItem[] {
  const items: FindingDetailTrackingItem[] = [];

  const headlineValue = String(params.headlineValue || "").trim();
  if (headlineValue) {
    items.push({
      label: String(params.headlineLabel || "").trim() || "概览",
      value: headlineValue,
      title: String(params.headlineTitle || "").trim() || null,
    });
  }

  items.push(
    ...params.summaryStats.map((stat) => ({
      label: stat.label,
      value: stat.value,
    })),
  );

  return items;
}

function buildMergedOverviewItems(params: {
  name: string;
  overviewItems: FindingDetailTrackingItem[];
  trackingItems: FindingDetailTrackingItem[];
}): FindingDetailTrackingItem[] {
  const name = String(params.name || "").trim() || MISSING_VALUE;
  return [
    { label: "名称", value: name },
    ...params.overviewItems,
    ...params.trackingItems,
  ];
}

function buildNarrativeSection(params: {
  id: string;
  title: string;
  emphasis?: FindingDetailNarrativeSection["emphasis"];
  content?: string | null;
  emptyBody?: string;
}): FindingDetailNarrativeSection {
  const content = String(params.content || "").trim();
  if (content) {
    return {
      id: params.id,
      title: params.title,
      emphasis: params.emphasis || "neutral",
      finding: {
        description: content,
        description_markdown: content,
      },
    };
  }

  return {
    id: params.id,
    title: params.title,
    emphasis: params.emphasis || "neutral",
    body: params.emptyBody || MISSING_DESCRIPTION,
  };
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

function extractMarkdownSections(sourceText: string): Map<string, string> {
  const source = String(sourceText || "").replace(/\r\n/g, "\n");
  const matches = [...source.matchAll(MARKDOWN_SECTION_HEADING_RE)];
  const sections = new Map<string, string>();

  matches.forEach((match, index) => {
    const title = String(match[1] || "").trim();
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? (matches[index + 1]?.index ?? source.length) : source.length;
    const content = source.slice(start, end).trim();
    if (title) {
      sections.set(title, content);
    }
  });

  return sections;
}

function buildAgentMarkdownNarrativeSections(
  finding: AgentFinding,
): FindingDetailNarrativeSection[] {
  const sections = extractMarkdownSections(String(finding.description_markdown || ""));
  const impact = String(finding.impact || sections.get("业务影响") || "").trim();
  const remediation = String(
    finding.remediation || finding.suggestion || sections.get("修复建议") || "",
  ).trim();
  const verification = String(
    finding.verification || sections.get("验证结论") || "",
  ).trim();

  const narrativeSections = [
    buildNarrativeSection({
      id: `agent:${finding.id}:root-cause`,
      title: "根因说明",
      emphasis: "primary",
      content: sections.get("根因解释"),
      emptyBody: MISSING_MARKDOWN_SECTION,
    }),
  ];

  if (impact) {
    narrativeSections.push(
      buildNarrativeSection({
        id: `agent:${finding.id}:impact`,
        title: "影响分析",
        emphasis: "secondary",
        content: impact,
        emptyBody: MISSING_MARKDOWN_SECTION,
      }),
    );
  }
  if (remediation) {
    narrativeSections.push(
      buildNarrativeSection({
        id: `agent:${finding.id}:remediation`,
        title: "修复建议",
        emphasis: "success",
        content: remediation,
        emptyBody: MISSING_MARKDOWN_SECTION,
      }),
    );
  }
  if (verification) {
    narrativeSections.push(
      buildNarrativeSection({
        id: `agent:${finding.id}:verification`,
        title: "验证结论",
        emphasis: "neutral",
        content: verification,
        emptyBody: MISSING_MARKDOWN_SECTION,
      }),
    );
  }

  return narrativeSections;
}

function buildIntelligentAuditSourceItems(finding: AgentFinding): FindingDetailTrackingItem[] {
  const items: FindingDetailTrackingItem[] = [{ label: "来源", value: "智能审计" }];
  const nodeName = String(finding.source_node_name || finding.source_node_id || "").trim();
  if (nodeName) {
    items.push({ label: "来源节点", value: nodeName, mono: Boolean(finding.source_node_id) });
  }
  const role = String(finding.source_role || "").trim();
  if (role) {
    items.push({ label: "来源角色", value: role });
  }
  if (Array.isArray(finding.artifact_refs) && finding.artifact_refs.length > 0) {
    items.push({
      label: "Artifact",
      value: finding.artifact_refs
        .map((artifact) => String(artifact?.path || "").trim())
        .filter(Boolean)
        .slice(0, 3)
        .join("；") || MISSING_VALUE,
      mono: true,
    });
  }
  return items;
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

export function buildFullFileDisplayLines(params: {
  content: string;
  lineStart?: number | null;
  focusLine?: number | null;
  highlightStartLine?: number | null;
  highlightEndLine?: number | null;
}): FindingCodeWindowDisplayLine[] {
  const lines = splitCodeLines(params.content);
  const lineStart = isFiniteLineNumber(params.lineStart) ? params.lineStart : 1;
  const highlightStart = isFiniteLineNumber(params.highlightStartLine)
    ? params.highlightStartLine
    : null;
  const highlightEnd = isFiniteLineNumber(params.highlightEndLine)
    ? params.highlightEndLine
    : highlightStart;
  const focusLine = isFiniteLineNumber(params.focusLine) ? params.focusLine : null;

  return lines.map((content, index) => {
    const lineNumber = lineStart + index;
    const isHighlighted =
      highlightStart !== null &&
      highlightEnd !== null &&
      lineNumber >= highlightStart &&
      lineNumber <= highlightEnd;
    return {
      lineNumber,
      content,
      kind: "code",
      isHighlighted,
      isFocus: focusLine !== null && lineNumber === focusLine,
    };
  });
}

function finalizeCodeSectionView(
  view: FindingDetailCodeView,
  params: {
    projectId?: string | null;
    projectSourceType?: ProjectSourceType | null;
    projectName?: string | null;
  },
): FindingDetailCodeView {
  const displayFilePath = buildDisplayFilePath(view.filePath, params.projectName);
  const locationLabel = buildLineLabel(
    isFiniteLineNumber(view.highlightStartLine) ? view.highlightStartLine : view.lineStart,
    isFiniteLineNumber(view.highlightEndLine) ? view.highlightEndLine : view.lineEnd,
  );
  const relatedLines =
    Array.isArray(view.displayLines) && view.displayLines.length > 0
      ? view.displayLines
      : buildFullFileDisplayLines({
        content: view.code,
        lineStart: view.lineStart,
        focusLine: view.focusLine,
        highlightStartLine: view.highlightStartLine,
        highlightEndLine: view.highlightEndLine,
      });
  const projectId = String(params.projectId || "").trim();
  const filePath = normalizeFindingDetailFullFilePath(view.filePath);
  const fullFileAvailable =
    params.projectSourceType === "zip" && projectId.length > 0 && filePath !== null;

  return {
    ...view,
    displayFilePath,
    locationLabel,
    relatedLines,
    fullFileAvailable,
    fullFileRequest: fullFileAvailable
      ? {
        projectId,
        filePath,
      }
      : null,
  };
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
  const descriptionMarkdown = String(finding.description_markdown || "").trim();
  if (descriptionMarkdown) return descriptionMarkdown;
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
  const resolvedFilePath = resolvePreferredFilePath(
    finding.file_path,
    finding.resolved_file_path,
  );
  const resolvedStartLine = resolvePreferredLineStart(
    finding.start_line ?? null,
    finding.resolved_line_start,
  );
  if (context && Array.isArray(context.lines) && context.lines.length > 0) {
    const sortedLines = [...context.lines].sort((a, b) => a.line_number - b.line_number);
    const hitLines = sortedLines.filter((line) => line.is_hit).map((line) => line.line_number);
    const lineStart = sortedLines[0]?.line_number ?? context.start_line;
    const lineEnd = sortedLines[sortedLines.length - 1]?.line_number ?? context.end_line;
    return [
      {
        id: `static:${finding.id}`,
        title: "命中代码",
        filePath: context.file_path || resolvedFilePath || null,
        code: sortedLines.map((line) => line.content || "").join("\n"),
        lineStart,
        lineEnd,
        highlightStartLine:
          hitLines[0] ?? context.start_line ?? resolvedStartLine ?? null,
        highlightEndLine:
          hitLines[hitLines.length - 1] ??
          context.end_line ??
          parseStaticEndLine(finding) ??
          resolvedStartLine ??
          null,
        focusLine: hitLines[0] ?? resolvedStartLine ?? context.start_line ?? lineStart ?? null,
      },
    ];
  }

  const fallbackCode = String(finding.code_snippet || "").trim();
  if (!fallbackCode) return [];
  return [
    {
      id: `static:${finding.id}`,
      title: "命中代码",
      filePath: resolvedFilePath || null,
      code: fallbackCode,
      lineStart: resolvedStartLine ?? null,
      lineEnd: parseStaticEndLine(finding),
      highlightStartLine: resolvedStartLine ?? null,
      highlightEndLine: parseStaticEndLine(finding),
      focusLine: resolvedStartLine ?? null,
    },
  ];
}

export function buildAgentFindingCodeViews(finding: AgentFinding): FindingDetailCodeView[] {
  const resolvedFilePath = resolvePreferredFilePath(
    finding.file_path,
    finding.resolved_file_path,
  );
  const resolvedStartLine = resolvePreferredLineStart(
    finding.line_start ?? null,
    finding.resolved_line_start,
  );
  const contextCode = String(finding.code_context || "").trim();
  const snippetCode = String(finding.code_snippet || "").trim();
  const code = contextCode || snippetCode;
  if (!code) return [];

  const lineStart = isFiniteLineNumber(finding.context_start_line)
    ? finding.context_start_line
    : resolvedStartLine;
  const lineEnd = isFiniteLineNumber(finding.context_end_line)
    ? finding.context_end_line
    : finding.line_end;

  return [
    {
      id: `agent:${finding.id}`,
      title: contextCode ? "命中代码" : "命中片段",
      filePath: resolvedFilePath,
      code,
      lineStart: lineStart ?? null,
      lineEnd: lineEnd ?? lineStart ?? null,
      highlightStartLine: resolvedStartLine ?? lineStart ?? null,
      highlightEndLine: finding.line_end ?? lineEnd ?? lineStart ?? null,
      focusLine: resolvedStartLine ?? lineStart ?? null,
    },
  ];
}

function buildBaseModel(params: {
  pageTitle: string;
  codePanelTitle: string;
  emptyCodeMessage: string;
  narrativeSections: FindingDetailNarrativeSection[];
  trackingItems: FindingDetailTrackingItem[];
  overviewItems: FindingDetailTrackingItem[];
  codeSections: FindingDetailCodeView[];
  codeBrowserTarget: FindingDetailPageModel["codeBrowserTarget"];
  projectId?: string | null;
  projectSourceType?: ProjectSourceType | null;
  projectName?: string | null;
}): FindingDetailPageModel {
  return {
    pageTitle: params.pageTitle,
    codePanelTitle: params.codePanelTitle,
    emptyCodeMessage: params.emptyCodeMessage,
    narrativeSections: params.narrativeSections,
    trackingItems: params.trackingItems,
    overviewItems: params.overviewItems,
    codeSections: params.codeSections.map((section) =>
      finalizeCodeSectionView(section, {
        projectId: params.projectId,
        projectSourceType: params.projectSourceType,
        projectName: params.projectName,
      }),
    ),
    codeBrowserTarget: params.codeBrowserTarget,
  };
}

export function buildAgentFindingDetailModel(params: {
  finding: AgentFinding;
  taskId: string;
  findingId: string;
  projectId?: string | null;
  projectSourceType?: ProjectSourceType | null;
  projectName?: string | null;
}): FindingDetailPageModel {
  const { finding } = params;
  const isFalsePositive = isAgentFalsePositiveFinding(finding);
  const severity = resolveSeverityDisplay(finding.severity);
  const confidence = resolveNumericConfidenceDisplay(resolveAgentConfidenceValue(finding));
  const location = formatLocation({
    filePath: resolvePreferredFilePath(finding.file_path, finding.resolved_file_path),
    lineStart: resolvePreferredLineStart(finding.line_start, finding.resolved_line_start),
    lineEnd: finding.line_end,
  });
  const typeDisplay = resolveCweDisplay({
    cwe: finding.cwe_id,
    fallbackLabel: String(finding.vulnerability_type || "").trim() || MISSING_VALUE,
  });
  const trackingItems = [
    ...buildTrackingItems({
      sourceLabel: "智能审计",
      taskId: params.taskId,
      findingId: params.findingId,
      location,
      includeSource: false,
    }),
    ...buildIntelligentAuditSourceItems(finding),
  ];
  const overviewTrackingItems = trackingItems.filter((item) => item.label !== "来源");
  const codeSections = buildFindingDetailCodeSections(buildAgentFindingCodeViews(finding));

  if (isFalsePositive) {
    const statusLabel = buildStatusLabel(finding.status || "false_positive");
    const summaryStats: FindingDetailSummaryStat[] = [
      { label: "漏洞类型", value: typeDisplay.label, tone: "info" },
      { label: "漏洞危害", value: severity.label, tone: severity.tone },
      { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
    ];

    return buildBaseModel({
      pageTitle: "误报判定依据",
      codePanelTitle: "关联代码 / 命中位置",
      emptyCodeMessage: "该误报未保留可展示代码，仅提供判定结论。",
      narrativeSections: [
        buildNarrativeSection({
          id: `agent:${finding.id}:false-positive`,
          title: "判定依据",
          content: getAgentFalsePositiveEvidence(finding),
          emphasis: "neutral",
          emptyBody: "未生成详细判定说明",
        }),
      ],
      trackingItems,
      overviewItems: buildMergedOverviewItems({
        name:
          String(finding.display_title || "").trim() ||
          String(finding.title || "").trim() ||
          "该问题已在验证阶段判定为误报",
        overviewItems: [
          { label: "状态", value: statusLabel },
          ...buildOverviewItems({
            headlineLabel: "验证结论",
            headlineValue: "该问题已在验证阶段判定为误报",
            summaryStats,
          }),
        ],
        trackingItems: overviewTrackingItems,
      }),
      codeSections,
      codeBrowserTarget: buildCodeBrowserTarget({
        filePath: finding.resolved_file_path ?? finding.file_path,
        line: finding.resolved_line_start ?? finding.line_start,
      }),
      projectId: params.projectId,
      projectSourceType: params.projectSourceType,
      projectName: params.projectName,
    });
  }

  const summaryStats: FindingDetailSummaryStat[] = [
    { label: "漏洞危害", value: severity.label, tone: severity.tone },
    { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
  ];

  return buildBaseModel({
    pageTitle: "统一漏洞详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: MISSING_AGENT_CODE_EVIDENCE,
    narrativeSections: buildAgentMarkdownNarrativeSections(finding),
    trackingItems,
    overviewItems: buildMergedOverviewItems({
      name:
        String(finding.display_title || "").trim() ||
        String(finding.title || "").trim() ||
        typeDisplay.label,
      overviewItems: buildOverviewItems({
        headlineLabel: "漏洞类型",
        headlineValue: typeDisplay.label,
        headlineTitle: typeDisplay.tooltip,
        summaryStats,
      }),
      trackingItems: overviewTrackingItems,
    }),
    codeSections,
    codeBrowserTarget: buildCodeBrowserTarget({
      filePath: finding.resolved_file_path ?? finding.file_path,
      line: finding.resolved_line_start ?? finding.line_start,
    }),
    projectId: params.projectId,
    projectSourceType: params.projectSourceType,
    projectName: params.projectName,
  });
}

export function buildOpengrepFindingDetailModel(params: {
  finding: OpengrepFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  context?: OpengrepFindingContext | null;
  projectId?: string | null;
  projectSourceType?: ProjectSourceType | null;
  projectName?: string | null;
}): FindingDetailPageModel {
  return buildStaticFindingDetailModel({
    ...params,
    sourceLabel: "静态审计 · Opengrep",
  });
}

export function buildCodeqlFindingDetailModel(params: {
  finding: OpengrepFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  context?: OpengrepFindingContext | null;
  projectId?: string | null;
  projectSourceType?: ProjectSourceType | null;
  projectName?: string | null;
}): FindingDetailPageModel {
  return buildStaticFindingDetailModel({
    ...params,
    sourceLabel: "静态审计 · CodeQL",
  });
}

function buildStaticFindingDetailModel(params: {
  finding: OpengrepFinding;
  taskId: string;
  findingId: string;
  taskName?: string | null;
  context?: OpengrepFindingContext | null;
  projectId?: string | null;
  projectSourceType?: ProjectSourceType | null;
  projectName?: string | null;
  sourceLabel: string;
}): FindingDetailPageModel {
  const { finding } = params;
  const severity = resolveSeverityDisplay(finding.severity);
  const confidence = resolveTextConfidenceDisplay(finding.confidence);
  const location = formatLocation({
    filePath: resolvePreferredFilePath(finding.file_path, finding.resolved_file_path),
    lineStart: resolvePreferredLineStart(finding.start_line ?? null, finding.resolved_line_start),
    lineEnd: parseStaticEndLine(finding),
  });
  const typeDisplay = resolveCweDisplay({
    cwe: finding.cwe,
    fallbackLabel: String(finding.rule_name || "").trim() || "unknown-rule",
  });
  const summaryStats: FindingDetailSummaryStat[] = [
    { label: "漏洞危害", value: severity.label, tone: severity.tone },
    { label: "漏洞置信度", value: confidence.label, tone: confidence.tone },
  ];
  const trackingItems = buildTrackingItems({
    sourceLabel: params.sourceLabel,
    taskId: params.taskId,
    findingId: params.findingId,
    taskName: params.taskName,
    location,
  });
  const ruleName = String(finding.rule_name || "").trim();
  if (ruleName) {
    trackingItems.push({ label: "规则标识", value: ruleName, mono: true });
  }

  return buildBaseModel({
    pageTitle: "统一漏洞详情",
    codePanelTitle: "关联代码",
    emptyCodeMessage: "暂无可展示的命中代码。",
    narrativeSections: [
      buildNarrativeSection({
        id: `opengrep:${finding.id}:summary`,
        title: "扫描说明",
        content: String(finding.description || "").trim() || MISSING_DESCRIPTION,
      }),
    ],
    trackingItems,
    overviewItems: buildMergedOverviewItems({
      name: typeDisplay.label,
      overviewItems: buildOverviewItems({
        headlineLabel: "漏洞类型",
        headlineValue: typeDisplay.label,
        headlineTitle: typeDisplay.tooltip,
        summaryStats,
      }),
      trackingItems,
    }),
    codeSections: buildFindingDetailCodeSections(
      buildOpengrepFindingCodeViews(finding, params.context ?? null),
    ),
    codeBrowserTarget: buildCodeBrowserTarget({
      filePath: finding.resolved_file_path ?? finding.file_path,
      line: finding.resolved_line_start ?? finding.start_line,
    }),
    projectId: params.projectId,
    projectSourceType: params.projectSourceType,
    projectName: params.projectName,
  });
}
