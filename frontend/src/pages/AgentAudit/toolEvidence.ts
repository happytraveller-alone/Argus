export type ToolEvidenceRenderType =
  | "code_window"
  | "search_hits"
  | "execution_result"
  | "outline_summary"
  | "function_summary"
  | "symbol_body";
export type ToolEvidenceLineKind = "context" | "focus" | "match";

export interface ToolEvidenceLine {
  lineNumber: number;
  text: string;
  kind: ToolEvidenceLineKind;
}

export interface ToolEvidenceCodeWindowEntry {
  filePath: string;
  startLine: number;
  endLine: number;
  focusLine: number | null;
  language: string;
  title?: string;
  symbolName?: string;
  symbolKind?: string;
  lines: ToolEvidenceLine[];
}

export interface ToolEvidenceSearchHitEntry {
  filePath: string;
  matchLine: number;
  matchText: string;
  column?: number | null;
  symbolName?: string;
  matchKind?: string;
}

export interface ToolEvidenceOutlineSummaryEntry {
  filePath: string;
  fileRole: string;
  keySymbols: string[];
  imports: string[];
  entrypoints: string[];
  riskMarkers: string[];
  frameworkHints: string[];
}

export interface ToolEvidenceFunctionSummaryEntry {
  filePath: string;
  resolvedFunction: string;
  signature: string;
  purpose: string;
  inputs: string[];
  outputs: string[];
  keyCalls: string[];
  riskPoints: string[];
  relatedSymbols: string[];
}

export interface ToolEvidenceSymbolBodyEntry extends ToolEvidenceCodeWindowEntry {
  body: string;
}

export interface ToolEvidenceArtifact {
  label: string;
  value: string;
}

export interface ToolEvidenceExecutionCode {
  language: string;
  lines: ToolEvidenceLine[];
}

export interface ToolEvidenceExecutionResultEntry {
  language?: string;
  exitCode: number;
  status: "passed" | "failed" | "error";
  title?: string;
  description?: string;
  runtimeImage?: string;
  executionCommand?: string;
  stdoutPreview?: string;
  stderrPreview?: string;
  artifacts: ToolEvidenceArtifact[];
  code?: ToolEvidenceExecutionCode | null;
}

export type ToolEvidencePayload =
  | {
      renderType: "code_window";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceCodeWindowEntry[];
    }
  | {
      renderType: "search_hits";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceSearchHitEntry[];
    }
  | {
      renderType: "outline_summary";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceOutlineSummaryEntry[];
    }
  | {
      renderType: "function_summary";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceFunctionSummaryEntry[];
    }
  | {
      renderType: "symbol_body";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceSymbolBodyEntry[];
    }
  | {
      renderType: "execution_result";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceExecutionResultEntry[];
    };

const TOOL_EVIDENCE_TOOLS = new Set([
  "read_file",
  "get_code_window",
  "search_code",
  "get_file_outline",
  "get_function_summary",
  "get_symbol_body",
  "extract_function",
  "run_code",
  "sandbox_exec",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function toInt(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function toStringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function parseCommandChain(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || "").trim())
    .filter((item, index, source) => item.length > 0 && source.indexOf(item) === index);
}

function buildDisplayCommand(commandChain: string[]): string {
  return commandChain.join(" -> ");
}

function parseLines(value: unknown): ToolEvidenceLine[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceLine[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const lineNumber = toInt(record.line_number);
    const kind = toStringValue(record.kind) as ToolEvidenceLineKind;
    if (lineNumber === null || !["context", "focus", "match"].includes(kind)) {
      return null;
    }
    parsed.push({
      lineNumber,
      text: toStringValue(record.text),
      kind,
    });
  }
  return parsed;
}

function parseCodeWindowEntries(value: unknown): ToolEvidenceCodeWindowEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceCodeWindowEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    const startLine = toInt(record.start_line);
    const endLine = toInt(record.end_line);
    const lines = parseLines(record.lines);
    if (!filePath || startLine === null || endLine === null || !lines) {
      return null;
    }
    parsed.push({
      filePath,
      startLine,
      endLine,
      focusLine: toInt(record.focus_line),
      language: toStringValue(record.language) || "text",
      title: toStringValue(record.title) || undefined,
      symbolName: toStringValue(record.symbol_name) || undefined,
      symbolKind: toStringValue(record.symbol_kind) || undefined,
      lines,
    });
  }
  return parsed;
}

function parseSearchHitEntries(value: unknown): ToolEvidenceSearchHitEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceSearchHitEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    const matchLine = toInt(record.match_line ?? record.line);
    if (!filePath || matchLine === null) return null;
    parsed.push({
      filePath,
      matchLine,
      matchText: toStringValue(record.match_text),
      column: toInt(record.column),
      symbolName: toStringValue(record.symbol_name) || undefined,
      matchKind: toStringValue(record.match_kind) || undefined,
    });
  }
  return parsed;
}

function parseOutlineSummaryEntries(value: unknown): ToolEvidenceOutlineSummaryEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceOutlineSummaryEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    if (!filePath) return null;
    parsed.push({
      filePath,
      fileRole: toStringValue(record.file_role) || "unknown",
      keySymbols: Array.isArray(record.key_symbols) ? record.key_symbols.map(String) : [],
      imports: Array.isArray(record.imports) ? record.imports.map(String) : [],
      entrypoints: Array.isArray(record.entrypoints) ? record.entrypoints.map(String) : [],
      riskMarkers: Array.isArray(record.risk_markers) ? record.risk_markers.map(String) : [],
      frameworkHints: Array.isArray(record.framework_hints) ? record.framework_hints.map(String) : [],
    });
  }
  return parsed;
}

function parseFunctionSummaryEntries(value: unknown): ToolEvidenceFunctionSummaryEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceFunctionSummaryEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    const resolvedFunction = toStringValue(record.resolved_function).trim();
    if (!filePath || !resolvedFunction) return null;
    parsed.push({
      filePath,
      resolvedFunction,
      signature: toStringValue(record.signature),
      purpose: toStringValue(record.purpose),
      inputs: Array.isArray(record.inputs) ? record.inputs.map(String) : [],
      outputs: Array.isArray(record.outputs) ? record.outputs.map(String) : [],
      keyCalls: Array.isArray(record.key_calls) ? record.key_calls.map(String) : [],
      riskPoints: Array.isArray(record.risk_points) ? record.risk_points.map(String) : [],
      relatedSymbols: Array.isArray(record.related_symbols)
        ? record.related_symbols.map(String)
        : [],
    });
  }
  return parsed;
}

function parseSymbolBodyEntries(value: unknown): ToolEvidenceSymbolBodyEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceSymbolBodyEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    const startLine = toInt(record.start_line);
    const endLine = toInt(record.end_line);
    const lines = parseLines(record.lines);
    if (!filePath || startLine === null || endLine === null || !lines) {
      return null;
    }
    parsed.push({
      filePath,
      startLine,
      endLine,
      focusLine: startLine,
      language: toStringValue(record.language) || "text",
      symbolName: toStringValue(record.symbol_name) || undefined,
      symbolKind: "symbol",
      title: "符号源码",
      body: toStringValue(record.body),
      lines,
    });
  }
  return parsed;
}

function parseArtifacts(value: unknown): ToolEvidenceArtifact[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const record = asRecord(item);
      if (!record) return null;
      const label = toStringValue(record.label).trim();
      if (!label) return null;
      return {
        label,
        value: toStringValue(record.value),
      };
    })
    .filter((item): item is ToolEvidenceArtifact => item !== null);
}

function parseExecutionCode(value: unknown): ToolEvidenceExecutionCode | null {
  const record = asRecord(value);
  if (!record) return null;
  const lines = parseLines(record.lines);
  if (!lines) return null;
  return {
    language: toStringValue(record.language) || "text",
    lines,
  };
}

function parseExecutionEntries(value: unknown): ToolEvidenceExecutionResultEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceExecutionResultEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const exitCode = toInt(record.exit_code);
    const status = toStringValue(record.status) as ToolEvidenceExecutionResultEntry["status"];
    const executionCommand = toStringValue(record.execution_command).trim();
    const description = toStringValue(record.description).trim();
    if (exitCode === null || !["passed", "failed", "error"].includes(status)) {
      return null;
    }
    if (!executionCommand && !description) {
      return null;
    }
    parsed.push({
      language: toStringValue(record.language) || undefined,
      exitCode,
      status,
      title: toStringValue(record.title) || undefined,
      description: description || undefined,
      runtimeImage: toStringValue(record.runtime_image) || undefined,
      executionCommand: executionCommand || undefined,
      stdoutPreview: toStringValue(record.stdout_preview) || undefined,
      stderrPreview: toStringValue(record.stderr_preview) || undefined,
      artifacts: parseArtifacts(record.artifacts),
      code: parseExecutionCode(record.code),
    });
  }
  return parsed;
}

export function isToolEvidenceCapableTool(toolName: string | null | undefined): boolean {
  return TOOL_EVIDENCE_TOOLS.has(String(toolName || "").trim().toLowerCase());
}

export function parseToolEvidence(value: unknown): ToolEvidencePayload | null {
  const container = asRecord(value);
  const metadata = asRecord(container?.metadata) || container;
  if (!metadata) return null;

  const renderType = toStringValue(metadata.render_type) as ToolEvidenceRenderType;
  const commandChain = parseCommandChain(metadata.command_chain);
  const displayCommand = toStringValue(metadata.display_command).trim();
  if (!displayCommand || commandChain.length === 0) {
    return null;
  }

  if (renderType === "code_window") {
    const entries = parseCodeWindowEntries(metadata.entries);
    return entries
      ? {
          renderType,
          commandChain,
          displayCommand,
          entries,
        }
      : null;
  }

  if (renderType === "search_hits") {
    const entries = parseSearchHitEntries(metadata.entries);
    return entries
      ? {
          renderType,
          commandChain,
          displayCommand,
          entries,
        }
      : null;
  }

  if (renderType === "outline_summary") {
    const entries = parseOutlineSummaryEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "function_summary") {
    const entries = parseFunctionSummaryEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "symbol_body") {
    const entries = parseSymbolBodyEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "execution_result") {
    const entries = parseExecutionEntries(metadata.entries);
    return entries
      ? {
          renderType,
          commandChain,
          displayCommand,
          entries,
        }
      : null;
  }

  return null;
}

function extractToolInputRecord(value: unknown): Record<string, unknown> | null {
  return asRecord(value);
}

function extractJsonObjectAfterMarker(text: string, marker: string): Record<string, unknown> | null {
  const rawText = String(text || "");
  const markerIndex = rawText.indexOf(marker);
  if (markerIndex < 0) return null;

  const start = rawText.indexOf("{", markerIndex);
  if (start < 0) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < rawText.length; index += 1) {
    const char = rawText[index];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\") {
        escaped = true;
        continue;
      }
      if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }
    if (char === "{") {
      depth += 1;
      continue;
    }
    if (char !== "}") continue;

    depth -= 1;
    if (depth !== 0) continue;
    try {
      return asRecord(JSON.parse(rawText.slice(start, index + 1)));
    } catch {
      return null;
    }
  }

  return null;
}

function extractOutputTextFromContent(content: unknown): string {
  const rawText = toStringValue(content);
  if (!rawText) return "";

  const outputMarker = "输出：";
  const outputIndex = rawText.lastIndexOf(outputMarker);
  if (outputIndex < 0) return "";
  return rawText.slice(outputIndex + outputMarker.length).trim();
}

function inferToolInput(toolInput: unknown, logContent?: unknown): Record<string, unknown> | null {
  return extractToolInputRecord(toolInput) || extractJsonObjectAfterMarker(toStringValue(logContent), "输入：");
}

function decodeEscapedText(value: string): string {
  let output = "";
  for (let index = 0; index < value.length; index += 1) {
    const current = value[index];
    if (current !== "\\" || index === value.length - 1) {
      output += current;
      continue;
    }
    const next = value[index + 1];
    index += 1;
    if (next === "n") output += "\n";
    else if (next === "r") output += "\r";
    else if (next === "t") output += "\t";
    else if (next === "\\") output += "\\";
    else if (next === "'") output += "'";
    else if (next === "\"") output += "\"";
    else output += next;
  }
  return output;
}

function unwrapCallToolText(raw: string): string {
  const marker = "text='";
  const start = raw.indexOf(marker);
  if (start < 0) return raw;
  let cursor = start + marker.length;
  let escaped = false;
  let extracted = "";
  while (cursor < raw.length) {
    const char = raw[cursor];
    if (escaped) {
      extracted += `\\${char}`;
      escaped = false;
      cursor += 1;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      cursor += 1;
      continue;
    }
    if (char === "'" && raw.slice(cursor, cursor + 14).startsWith("', annotations")) {
      return decodeEscapedText(extracted);
    }
    extracted += char;
    cursor += 1;
  }
  return raw;
}

function detectLanguageFromPath(filePath: string): string {
  const normalized = String(filePath || "").toLowerCase();
  if (normalized.endsWith(".py")) return "python";
  if (normalized.endsWith(".ts") || normalized.endsWith(".tsx")) return "typescript";
  if (normalized.endsWith(".js") || normalized.endsWith(".jsx")) return "javascript";
  if (normalized.endsWith(".java")) return "java";
  if (normalized.endsWith(".php")) return "php";
  if (normalized.endsWith(".go")) return "go";
  if (normalized.endsWith(".rb")) return "ruby";
  if (normalized.endsWith(".sh")) return "bash";
  if (normalized.endsWith(".c") || normalized.endsWith(".h")) return "c";
  if (normalized.endsWith(".cpp") || normalized.endsWith(".cc") || normalized.endsWith(".hpp")) return "cpp";
  return "text";
}

function normalizeExecutionLanguage(value: string): string | undefined {
  const normalized = String(value || "").trim();
  if (!normalized || normalized === "text") return undefined;
  return normalized;
}

function extractCommandHead(command: string): string | undefined {
  const normalized = String(command || "").trim();
  if (!normalized) return undefined;
  return normalized.split(/\s+/, 1)[0] || undefined;
}

function deriveExecutionStatus(
  toolMetadata: unknown,
  outputRecord?: Record<string, unknown> | null,
): ToolEvidenceExecutionResultEntry["status"] {
  const metadataRecord = asRecord(toolMetadata);
  const toolStatus = toStringValue(metadataRecord?.tool_status).trim().toLowerCase();
  if (toolStatus === "completed") return "passed";
  if (toolStatus === "failed") return "failed";
  if (toolStatus === "cancelled" || toolStatus === "canceled") return "error";
  const successValue = outputRecord?.success;
  if (successValue === true) return "passed";
  return "failed";
}

function deriveExecutionExitCode(
  status: ToolEvidenceExecutionResultEntry["status"],
  outputRecord?: Record<string, unknown> | null,
): number {
  const directExitCode = toInt(outputRecord?.exit_code);
  if (directExitCode !== null) return directExitCode;
  return status === "passed" ? 0 : 1;
}

function buildFallbackCommandChain(args: {
  toolName?: string | null;
  toolMetadata?: unknown;
  extras?: string[];
}): string[] {
  const metadataRecord = asRecord(args.toolMetadata);
  const metadataChain = parseCommandChain(metadataRecord?.command_chain);
  if (metadataChain.length > 0) return metadataChain;

  return parseCommandChain([
    args.toolName || "",
    ...(args.extras || []),
    toStringValue(metadataRecord?.mcp_adapter),
  ]);
}

function firstMeaningfulLine(text: string): string {
  return (
    text
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.length > 0) || ""
  );
}

function synthesizeReadFileEvidence(
  toolOutput: unknown,
  toolInput: unknown,
  toolMetadata?: unknown,
  logContent?: unknown,
): ToolEvidencePayload | null {
  const outputRecord = asRecord(toolOutput);
  const inputRecord = inferToolInput(toolInput, logContent);
  const rawResult = toStringValue(outputRecord?.result) || extractOutputTextFromContent(logContent);
  const filePath = toStringValue(inputRecord?.path ?? inputRecord?.file_path).trim();
  if (!rawResult || !filePath) return null;

  const rawText = unwrapCallToolText(rawResult);
  const rawLines = rawText.split("\n");
  const requestedStart = toInt(inputRecord?.start_line) ?? 1;
  const requestedEnd =
    toInt(inputRecord?.end_line) ??
    (requestedStart + Math.max(0, (toInt(inputRecord?.max_lines) ?? rawLines.length) - 1));

  let selectedLines = rawLines;
  let startLine = 1;
  if (rawLines.length >= requestedEnd) {
    selectedLines = rawLines.slice(Math.max(0, requestedStart - 1), requestedEnd);
    startLine = requestedStart;
  } else if (requestedStart > 1) {
    selectedLines = rawLines.slice(0, Math.max(1, requestedEnd - requestedStart + 1));
    startLine = requestedStart;
  }

  const lines = selectedLines.map((text, index) => ({
    lineNumber: startLine + index,
    text,
    kind: index === 0 ? ("focus" as const) : ("context" as const),
  }));

  return {
    renderType: "code_window",
    commandChain: buildFallbackCommandChain({
      toolName: "read_file",
      toolMetadata,
    }),
    displayCommand: buildDisplayCommand(
      buildFallbackCommandChain({
        toolName: "read_file",
        toolMetadata,
      }),
    ),
    entries: [
      {
        filePath,
        startLine,
        endLine: startLine + Math.max(0, lines.length - 1),
        focusLine: requestedStart,
        language: detectLanguageFromPath(filePath),
        title: "代码窗口",
        lines,
      },
    ],
  };
}

function synthesizeSearchCodeEvidence(
  toolOutput: unknown,
  toolMetadata?: unknown,
  logContent?: unknown,
): ToolEvidencePayload | null {
  const outputRecord = asRecord(toolOutput);
  const rawResult = toStringValue(outputRecord?.result) || extractOutputTextFromContent(logContent);
  if (!rawResult) return null;

  const rawText = unwrapCallToolText(rawResult);
  const entries: ToolEvidenceSearchHitEntry[] = [];
  const hitPattern = /^(.+?):(\d+)(?::\d+)?:([\s\S]*)$/;

  for (const line of rawText.split("\n")) {
    const matched = line.match(hitPattern);
    if (!matched) continue;
    const filePath = matched[1]?.trim();
    const matchLine = toInt(matched[2]);
    const matchText = (matched[3] || "").trim();
    if (!filePath || matchLine === null) continue;
    entries.push({
      filePath,
      matchLine,
      matchText,
    });
  }

  const emptyHints = ["未找到", "没有找到", "no matches", "0 matches", "not found"];
  if (entries.length === 0 && !emptyHints.some((hint) => rawText.toLowerCase().includes(hint.toLowerCase()))) {
    return null;
  }

  const commandChain = buildFallbackCommandChain({
    toolName: "search_code",
    toolMetadata,
    extras: ["rg"],
  });
  return {
    renderType: "search_hits",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries,
  };
}

function synthesizeExtractFunctionEvidence(
  toolOutput: unknown,
  toolInput: unknown,
  toolMetadata?: unknown,
  logContent?: unknown,
): ToolEvidencePayload | null {
  const outputRecord = asRecord(toolOutput);
  const inputRecord = inferToolInput(toolInput, logContent);
  const rawResult = toStringValue(outputRecord?.result) || extractOutputTextFromContent(logContent);
  const rawText = unwrapCallToolText(rawResult).trim();
  if (!rawText) return null;

  const looksLikeCode = rawText.includes("\n") || rawText.includes("{") || rawText.includes("def ");
  const filePath = toStringValue(inputRecord?.file_path ?? inputRecord?.path).trim();
  const startLine = toInt(inputRecord?.start_line);
  if (looksLikeCode && filePath && startLine !== null) {
    const codeLines = rawText.split("\n");
    const structuredLines = codeLines.map((text, index) => ({
      lineNumber: startLine + index,
      text,
      kind: index === 0 ? ("focus" as const) : ("context" as const),
    }));
    const commandChain = buildFallbackCommandChain({
      toolName: "extract_function",
      toolMetadata,
    });
    return {
      renderType: "code_window",
      commandChain,
      displayCommand: buildDisplayCommand(commandChain),
      entries: [
        {
          filePath,
          startLine,
          endLine: startLine + Math.max(0, structuredLines.length - 1),
          focusLine: startLine,
          language: detectLanguageFromPath(filePath),
          title: "函数提取",
          symbolName:
            toStringValue(inputRecord?.function_name ?? inputRecord?.symbol_name).trim() || undefined,
          symbolKind: "function",
          lines: structuredLines,
        },
      ],
    };
  }

  return synthesizeExecutionFallback("extract_function", toolOutput, toolInput, toolMetadata, logContent);
}

function synthesizeExecutionFallback(
  toolName: string,
  toolOutput: unknown,
  toolInput: unknown,
  toolMetadata?: unknown,
  logContent?: unknown,
): ToolEvidencePayload | null {
  const outputRecord = asRecord(toolOutput);
  const inputRecord = inferToolInput(toolInput, logContent);
  const rawResult = toStringValue(outputRecord?.result) || extractOutputTextFromContent(logContent);
  const rawText = unwrapCallToolText(rawResult).trim();
  if (!rawText) return null;

  const status = deriveExecutionStatus(toolMetadata, outputRecord);
  const executionCommand =
    toStringValue(inputRecord?.command).trim() ||
    toStringValue(inputRecord?.execution_command).trim() ||
    undefined;
  const pathValue = toStringValue(inputRecord?.file_path ?? inputRecord?.path).trim();
  const language =
    normalizeExecutionLanguage(toStringValue(inputRecord?.language).trim()) ||
    normalizeExecutionLanguage(pathValue ? detectLanguageFromPath(pathValue) : "");
  const commandExtras = [
    toStringValue(inputRecord?.shell),
    extractCommandHead(executionCommand || ""),
    language || "",
  ].filter((item): item is string => String(item).trim().length > 0);
  const commandChain = buildFallbackCommandChain({
    toolName,
    toolMetadata,
    extras: commandExtras,
  });
  const description =
    toStringValue(inputRecord?.description).trim() ||
    firstMeaningfulLine(rawText) ||
    `${toolName} 结果`;
  const inlineCode = toStringValue(inputRecord?.code).trim();

  return {
    renderType: "execution_result",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        language: language || undefined,
        exitCode: deriveExecutionExitCode(status, outputRecord),
        status,
        title: `${toolName} 结果`,
        description,
        executionCommand,
        stdoutPreview: status === "passed" ? rawText : "",
        stderrPreview: status === "passed" ? "" : rawText,
        artifacts: [],
        code: inlineCode
          ? {
              language: language || "text",
              lines: inlineCode.split("\n").map((text, index) => ({
                lineNumber: index + 1,
                text,
                kind: index === 0 ? ("focus" as const) : ("context" as const),
              })),
            }
          : null,
      },
    ],
  };
}

export function parseToolEvidenceFromLog(args: {
  toolName?: string | null;
  toolOutput: unknown;
  toolMetadata?: unknown;
  toolInput?: unknown;
  logContent?: unknown;
}): ToolEvidencePayload | null {
  const direct = parseToolEvidence(args.toolOutput);
  if (direct) return direct;

  const metadataPayload = parseToolEvidence({ metadata: args.toolMetadata });
  if (metadataPayload) return metadataPayload;

  const normalizedTool = String(args.toolName || "").trim().toLowerCase();
  if (normalizedTool === "read_file" || normalizedTool === "get_code_window") {
    return synthesizeReadFileEvidence(args.toolOutput, args.toolInput, args.toolMetadata, args.logContent);
  }

  if (normalizedTool === "search_code") {
    return synthesizeSearchCodeEvidence(args.toolOutput, args.toolMetadata, args.logContent);
  }

  if (normalizedTool === "extract_function" || normalizedTool === "get_symbol_body") {
    return synthesizeExtractFunctionEvidence(
      args.toolOutput,
      args.toolInput,
      args.toolMetadata,
      args.logContent,
    );
  }

  if (normalizedTool === "run_code" || normalizedTool === "sandbox_exec") {
    return synthesizeExecutionFallback(
      normalizedTool,
      args.toolOutput,
      args.toolInput,
      args.toolMetadata,
      args.logContent,
    );
  }

  return null;
}

export function toolEvidenceLinesToCode(lines: ToolEvidenceLine[]): string {
  return lines.map((line) => line.text).join("\n");
}
