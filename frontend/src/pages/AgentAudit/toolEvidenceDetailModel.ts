import type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";
import type {
  ParsedToolEvidence,
  ToolEvidenceCodeWindowEntry,
  ToolEvidenceExecutionResultEntry,
  ToolEvidenceFileListEntry,
  ToolEvidenceFlowAnalysisEntry,
  ToolEvidenceFunctionSummaryEntry,
  ToolEvidenceLine,
  ToolEvidenceLocatorResultEntry,
  ToolEvidenceOutlineSummaryEntry,
  ToolEvidencePayload,
  ToolEvidenceReportSummaryEntry,
  ToolEvidenceSearchHitEntry,
  ToolEvidenceVerificationSummaryEntry,
} from "./toolEvidence";
import { asParsedToolEvidence, toolEvidenceLinesToCode } from "./toolEvidence";

type ToolEvidenceHeaderBadgeTone = "default" | "success" | "warning" | "danger";

interface ToolEvidenceHeaderBadge {
  label: string;
  mono?: boolean;
  tone?: ToolEvidenceHeaderBadgeTone;
}

export interface ToolEvidenceOverviewChip {
  label: string;
  value: string;
  mono?: boolean;
}

interface ToolEvidencePrimaryCodeWindowPanel {
  kind: "code-window";
  title: string;
  code: string;
  displayLines: FindingCodeWindowDisplayLine[];
  filePath?: string | null;
  lineStart?: number | null;
  lineEnd?: number | null;
  focusLine?: number | null;
  highlightStartLine?: number | null;
  highlightEndLine?: number | null;
  meta?: string[];
}

interface ToolEvidencePrimaryMonospacePanel {
  kind: "monospace";
  title: string;
  content: string;
  note?: string;
}

interface ToolEvidencePrimaryFactPanel {
  kind: "fact-list";
  title: string;
  items: Array<{
    label: string;
    value: string;
    mono?: boolean;
  }>;
}

interface ToolEvidencePrimaryListPanel {
  kind: "list";
  title: string;
  items: string[];
  note?: string;
}

export type ToolEvidencePrimaryPanel =
  | ToolEvidencePrimaryCodeWindowPanel
  | ToolEvidencePrimaryMonospacePanel
  | ToolEvidencePrimaryFactPanel
  | ToolEvidencePrimaryListPanel;

export interface ToolEvidenceDetailViewModel {
  headerBadges: ToolEvidenceHeaderBadge[];
  notices: string[];
  overview: {
    chips: ToolEvidenceOverviewChip[];
  };
  primaryEvidence: {
    panels: ToolEvidencePrimaryPanel[];
  };
  rawData: {
    title: string;
    triggerLabel: string;
    content: string;
  };
}

interface BuildToolEvidenceDetailViewModelArgs {
  toolName?: string | null;
  evidence: ParsedToolEvidence | ToolEvidencePayload;
  rawOutput: unknown;
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function nonEmpty(items: Array<string | null | undefined>): string[] {
  return items.map((item) => String(item || "").trim()).filter(Boolean);
}

function buildHeaderBadges(parsed: ParsedToolEvidence): ToolEvidenceHeaderBadge[] {
  const payload = parsed.payload;
  if (!payload) return [];
  const stateTone: ToolEvidenceHeaderBadgeTone = parsed.state === "raw-only" ? "warning" : "success";

  return [
    {
      label: payload.displayCommand,
      mono: true,
    },
    {
      label: parsed.state,
      mono: true,
      tone: stateTone,
    },
  ];
}

function toDisplayLines(lines: ToolEvidenceLine[]): FindingCodeWindowDisplayLine[] {
  return lines.map((line) => ({
    lineNumber: line.lineNumber,
    content: line.text,
    kind: "code",
    isFocus: line.kind === "focus" || undefined,
    isHighlighted: line.kind === "focus" || line.kind === "match" || undefined,
  }));
}

function toLineRange(lines: ToolEvidenceLine[]): { startLine: number | null; endLine: number | null } {
  const first = lines[0]?.lineNumber ?? null;
  const last = lines[lines.length - 1]?.lineNumber ?? first;
  return {
    startLine: first,
    endLine: last,
  };
}

function formatLocation(filePath: string, line: number | null, endLine?: number | null): string {
  if (typeof line === "number" && typeof endLine === "number" && endLine >= line) {
    return `${filePath}:${line}-${endLine}`;
  }
  if (typeof line === "number") {
    return `${filePath}:${line}`;
  }
  return filePath;
}

function formatCount(value: number, unit: string): string {
  return `${value} ${unit}`;
}

function firstCommandStep(payload: ToolEvidencePayload, toolName?: string | null): string {
  return payload.commandChain[0] || String(toolName || "").trim() || payload.displayCommand;
}

function buildCodeWindowPanels(
  entries: ToolEvidenceCodeWindowEntry[],
  fallbackTitle: string,
): ToolEvidencePrimaryPanel[] {
  return entries.map((entry, index) => ({
    kind: "code-window",
    title: entry.title || `${fallbackTitle} ${index + 1}`,
    code: toolEvidenceLinesToCode(entry.lines),
    displayLines: toDisplayLines(entry.lines),
    filePath: entry.filePath,
    lineStart: entry.startLine,
    lineEnd: entry.endLine,
    focusLine: entry.focusLine,
    highlightStartLine: entry.focusLine,
    highlightEndLine: entry.focusLine,
    meta: nonEmpty([
      entry.language,
      entry.symbolName ? `${entry.symbolKind || "symbol"} ${entry.symbolName}` : "",
    ]),
  }));
}

function buildExecutionPanel(entry: ToolEvidenceExecutionResultEntry): ToolEvidencePrimaryPanel {
  if (entry.code) {
    const range = toLineRange(entry.code.lines);
    return {
      kind: "code-window",
      title: entry.title || "执行代码",
      code: toolEvidenceLinesToCode(entry.code.lines),
      displayLines: toDisplayLines(entry.code.lines),
      filePath: entry.title || "execution",
      lineStart: range.startLine,
      lineEnd: range.endLine,
      focusLine: range.startLine,
      highlightStartLine: range.startLine,
      highlightEndLine: range.startLine,
      meta: nonEmpty([entry.code.language || entry.language || "text"]),
    };
  }

  const selectedContent =
    entry.status === "failed" || entry.status === "error"
      ? entry.stderrPreview || entry.stdoutPreview || entry.executionCommand || entry.description || "执行证据"
      : entry.stdoutPreview || entry.stderrPreview || entry.executionCommand || entry.description || "执行证据";

  return {
    kind: "monospace",
    title: entry.title || "执行输出",
    content: selectedContent,
  };
}

function buildSearchHitsPanel(entries: ToolEvidenceSearchHitEntry[]): ToolEvidencePrimaryPanel {
  const visibleEntries = entries.slice(0, 8);
  return {
    kind: "monospace",
    title: "命中清单",
    content: visibleEntries
      .map((entry) => `${entry.filePath}:${entry.matchLine} ${entry.matchText}`.trim())
      .join("\n"),
    note: entries.length > visibleEntries.length ? "仅展示前 8 条" : undefined,
  };
}

function buildFileListPanel(entry: ToolEvidenceFileListEntry): ToolEvidencePrimaryPanel {
  const orderedLines = [...entry.directories, ...entry.files];
  const visibleLines = orderedLines.slice(0, 40);
  return {
    kind: "monospace",
    title: "目录与文件",
    content: visibleLines.join("\n") || "暂无可展示条目",
    note: orderedLines.length > visibleLines.length ? "仅展示前 40 行" : undefined,
  };
}

function buildLocatorPanel(entry: ToolEvidenceLocatorResultEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "定位信息",
    items: [
      { label: "签名", value: entry.signature || entry.symbolName, mono: true },
      { label: "参数", value: entry.parameters.join(", ") || "无", mono: true },
      { label: "返回值", value: entry.returnType || "未知", mono: true },
      {
        label: "行范围",
        value: `${entry.startLine}-${entry.endLine}`,
        mono: true,
      },
    ],
  };
}

function buildOutlinePanel(entry: ToolEvidenceOutlineSummaryEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "文件概览",
    items: [
      { label: "入口", value: entry.entrypoints.join(", ") || "无", mono: true },
      { label: "关键符号", value: entry.keySymbols.join(", ") || "无", mono: true },
      { label: "导入", value: entry.imports.join(", ") || "无", mono: true },
      { label: "风险标记", value: entry.riskMarkers.join(", ") || "无" },
      { label: "框架提示", value: entry.frameworkHints.join(", ") || "无" },
    ],
  };
}

function buildFunctionSummaryPanel(entry: ToolEvidenceFunctionSummaryEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "函数摘要",
    items: [
      { label: "签名", value: entry.signature || entry.resolvedFunction, mono: true },
      { label: "职责", value: entry.purpose || "暂无说明" },
      { label: "输入", value: entry.inputs.join(", ") || "无", mono: true },
      { label: "输出", value: entry.outputs.join(", ") || "无", mono: true },
      { label: "关键调用", value: entry.keyCalls.join(", ") || "无", mono: true },
      { label: "风险点", value: entry.riskPoints.join(", ") || "无" },
    ],
  };
}

function buildAnalysisPanel(payload: Extract<ToolEvidencePayload, { renderType: "analysis_summary" }>): ToolEvidencePrimaryPanel {
  const first = payload.entries[0];
  return {
    kind: "list",
    title: "分析摘要",
    items: nonEmpty([
      first?.summary,
      ...(first?.highlights || []),
      ...(first?.nextActions || []),
    ]),
  };
}

function buildFlowPanel(entry: ToolEvidenceFlowAnalysisEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "路径分析",
    items: [
      { label: "Source", value: entry.sourceNodes.join(" -> ") || "无", mono: true },
      { label: "Sink", value: entry.sinkNodes.join(" -> ") || "无", mono: true },
      { label: "调用链", value: entry.callChain.join(" -> ") || "无", mono: true },
      { label: "Taint 步骤", value: entry.taintSteps.join(" -> ") || "无", mono: true },
      { label: "阻塞原因", value: entry.blockedReasons.join(", ") || "无" },
      { label: "后续动作", value: entry.nextActions.join(", ") || "无" },
    ],
  };
}

function buildVerificationPanel(entry: ToolEvidenceVerificationSummaryEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "验证结果",
    items: [
      { label: "Target", value: entry.target, mono: true },
      { label: "Payload", value: entry.payload || "无", mono: true },
      { label: "Evidence", value: entry.evidence || "暂无证据文本" },
      {
        label: "运行态",
        value: nonEmpty([
          entry.responseStatus ? `HTTP ${entry.responseStatus}` : "",
          entry.runtimeStatus,
          entry.error,
        ]).join(" · ") || "无",
      },
    ],
  };
}

function buildReportPanel(entry: ToolEvidenceReportSummaryEntry): ToolEvidencePrimaryPanel {
  return {
    kind: "fact-list",
    title: "报告摘要",
    items: [
      { label: "漏洞类型", value: entry.vulnerabilityType },
      { label: "定位", value: entry.location, mono: true },
      { label: "已验证", value: entry.verified ? "是" : "否" },
      { label: "建议", value: entry.recommendation || "暂无建议" },
      {
        label: "评分",
        value: `confidence ${entry.confidence.toFixed(2)} · CVSS ${entry.cvssScore.toFixed(1)}`,
        mono: true,
      },
    ],
  };
}

function buildOverviewChips(
  payload: ToolEvidencePayload,
  toolName?: string | null,
): ToolEvidenceOverviewChip[] {
  if (payload.renderType === "code_window" || payload.renderType === "symbol_body") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first) {
      chips.push({
        label: "位置",
        value: formatLocation(first.filePath, first.startLine, first.endLine),
        mono: true,
      });
    }
    if (first?.focusLine) {
      chips.push({ label: "焦点", value: `焦点行 ${first.focusLine}`, mono: true });
    }
    if (first?.language) {
      chips.push({ label: "语言", value: first.language, mono: true });
    }
    chips.push({ label: "条目数", value: formatCount(payload.entries.length, "条目") });
    return chips;
  }

  if (payload.renderType === "search_hits") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [
      { label: "工具", value: String(toolName || "search_hits"), mono: true },
      { label: "命中数", value: formatCount(payload.entries.length, "条命中") },
      { label: "首个文件", value: first?.filePath || "未知", mono: true },
      { label: "命令起点", value: firstCommandStep(payload, toolName), mono: true },
    ];
    if (payload.entries.length > 8) {
      chips.push({ label: "展示", value: "仅展示前 8 条" });
    }
    return chips;
  }

  if (payload.renderType === "execution_result") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first) {
      chips.push({ label: "状态", value: `状态 ${first.status}` });
      chips.push({ label: "退出码", value: `退出码 ${first.exitCode}`, mono: true });
    }
    if (first?.language) {
      chips.push({ label: "语言", value: first.language, mono: true });
    }
    if (first?.runtimeImage) {
      chips.push({ label: "运行镜像", value: first.runtimeImage, mono: true });
    }
    if (first?.executionCommand) {
      chips.push({ label: "命令", value: first.executionCommand, mono: true });
    }
    return chips;
  }

  if (payload.renderType === "file_list") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.directory) {
      chips.push({ label: "目录", value: first.directory, mono: true });
    }
    if (first) {
      chips.push({ label: "文件数", value: formatCount(first.fileCount, "文件") });
      chips.push({ label: "目录数", value: formatCount(first.dirCount, "目录") });
    }
    if (first?.truncated) {
      chips.push({ label: "状态", value: "结果已截断" });
    }
    return chips;
  }

  if (payload.renderType === "locator_result") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.symbolName) {
      chips.push({ label: "符号", value: first.symbolName, mono: true });
    }
    if (first) {
      chips.push({
        label: "位置",
        value: formatLocation(first.filePath, first.line),
        mono: true,
      });
    }
    if (first?.engine) {
      chips.push({ label: "Engine", value: first.engine, mono: true });
    }
    if (typeof first?.confidence === "number") {
      chips.push({
        label: "Confidence",
        value: first.confidence.toFixed(2),
        mono: true,
      });
    }
    if (first) {
      chips.push({
        label: "状态",
        value: first.degraded ? "degraded" : "stable",
        mono: true,
      });
    }
    return chips;
  }

  if (payload.renderType === "outline_summary") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.filePath) {
      chips.push({ label: "文件", value: first.filePath, mono: true });
    }
    if (first?.fileRole) {
      chips.push({ label: "角色", value: first.fileRole });
    }
    chips.push({ label: "条目数", value: formatCount(payload.entries.length, "条目") });
    return chips;
  }

  if (payload.renderType === "function_summary") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.resolvedFunction) {
      chips.push({ label: "函数", value: first.resolvedFunction, mono: true });
    }
    if (first?.filePath) {
      chips.push({ label: "文件", value: first.filePath, mono: true });
    }
    chips.push({ label: "条目数", value: formatCount(payload.entries.length, "条目") });
    return chips;
  }

  if (payload.renderType === "analysis_summary") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.title) {
      chips.push({ label: "标题", value: first.title });
    }
    if (first) {
      chips.push({ label: "发现数", value: formatCount(first.hitCount, "发现") });
    }
    const severityText = Object.entries(first?.severityStats || {})
      .map(([key, count]) => `${key}:${count}`)
      .join(" · ");
    if (severityText) {
      chips.push({ label: "严重度", value: severityText, mono: true });
    }
    return chips;
  }

  if (payload.renderType === "flow_analysis") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.engine) {
      chips.push({ label: "Engine", value: first.engine, mono: true });
    }
    if (first?.reachability) {
      chips.push({ label: "Reachability", value: first.reachability, mono: true });
    }
    if (typeof first?.pathScore === "number") {
      chips.push({ label: "Score", value: first.pathScore.toFixed(2), mono: true });
    }
    if (first) {
      chips.push({
        label: "路径命中",
        value: `path=${String(first.pathFound)}`,
        mono: true,
      });
    }
    return chips;
  }

  if (payload.renderType === "verification_summary") {
    const first = payload.entries[0];
    const chips: ToolEvidenceOverviewChip[] = [];
    if (first?.vulnerabilityType) {
      chips.push({ label: "漏洞类型", value: first.vulnerabilityType });
    }
    if (first?.verdict) {
      chips.push({ label: "结论", value: first.verdict });
    }
    if (first?.target) {
      chips.push({ label: "目标", value: first.target, mono: true });
    }
    return chips;
  }

  const first = payload.entries[0];
  if (payload.renderType === "report_summary" && first) {
    return [
      { label: "标题", value: first.title },
      { label: "严重度", value: first.severity },
      { label: "定位", value: first.location, mono: true },
    ];
  }

  return [];
}

function buildPrimaryPanels(payload: ToolEvidencePayload): ToolEvidencePrimaryPanel[] {
  if (payload.renderType === "code_window") {
    return buildCodeWindowPanels(payload.entries, "代码窗口");
  }
  if (payload.renderType === "symbol_body") {
    return buildCodeWindowPanels(payload.entries, "符号源码");
  }
  if (payload.renderType === "search_hits") {
    return [buildSearchHitsPanel(payload.entries)];
  }
  if (payload.renderType === "execution_result") {
    return payload.entries.map((entry) => buildExecutionPanel(entry));
  }
  if (payload.renderType === "file_list") {
    return payload.entries.map((entry) => buildFileListPanel(entry));
  }
  if (payload.renderType === "locator_result") {
    return payload.entries.map((entry) => buildLocatorPanel(entry));
  }
  if (payload.renderType === "outline_summary") {
    return payload.entries.map((entry) => buildOutlinePanel(entry));
  }
  if (payload.renderType === "function_summary") {
    return payload.entries.map((entry) => buildFunctionSummaryPanel(entry));
  }
  if (payload.renderType === "analysis_summary") {
    return [buildAnalysisPanel(payload)];
  }
  if (payload.renderType === "flow_analysis") {
    return payload.entries.map((entry) => buildFlowPanel(entry));
  }
  if (payload.renderType === "verification_summary") {
    return payload.entries.map((entry) => buildVerificationPanel(entry));
  }
  if (payload.renderType === "report_summary") {
    return payload.entries.map((entry) => buildReportPanel(entry));
  }
  return [];
}

export function buildToolEvidenceDetailViewModel(
  args: BuildToolEvidenceDetailViewModelArgs,
): ToolEvidenceDetailViewModel | null {
  const parsed = asParsedToolEvidence(args.evidence);
  if (!parsed?.payload) return null;

  const payload = parsed.payload;
  return {
    headerBadges: buildHeaderBadges(parsed),
    notices: parsed.notices || [],
    overview: {
      chips: buildOverviewChips(payload, args.toolName),
    },
    primaryEvidence: {
      panels: buildPrimaryPanels(payload),
    },
    rawData: {
      title: "原始数据",
      triggerLabel: "查看原始数据",
      content: prettyJson(parsed.rawOutput ?? args.rawOutput ?? payload),
    },
  };
}
