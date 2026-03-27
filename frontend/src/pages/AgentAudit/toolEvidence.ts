export type ToolEvidenceRenderType =
  | "code_window"
  | "search_hits"
  | "execution_result"
  | "outline_summary"
  | "function_summary"
  | "symbol_body"
  | "file_list"
  | "locator_result"
  | "analysis_summary"
  | "flow_analysis"
  | "verification_summary"
  | "report_summary";
export type ToolEvidenceLineKind = "context" | "focus" | "match";
export type ToolEvidenceCompatibilityState = "native";

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
  language?: string;
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

export interface ToolEvidenceFileListEntry {
  directory: string;
  pattern?: string;
  recursive: boolean;
  files: string[];
  directories: string[];
  fileCount: number;
  dirCount: number;
  truncated: boolean;
  recommendedNextDirectories: string[];
}

export interface ToolEvidenceLocatorResultEntry {
  filePath: string;
  line: number;
  symbolName: string;
  startLine: number;
  endLine: number;
  signature?: string;
  parameters: string[];
  returnType?: string | null;
  engine: string;
  confidence: number;
  degraded: boolean;
}

export interface ToolEvidenceAnalysisSummaryEntry {
  title: string;
  summary: string;
  severityStats: Record<string, number>;
  hitCount: number;
  keyFiles: string[];
  highlights: string[];
  nextActions: string[];
}

export interface ToolEvidenceFlowAnalysisEntry {
  sourceNodes: string[];
  sinkNodes: string[];
  taintSteps: string[];
  callChain: string[];
  blockedReasons: string[];
  reachability: string;
  pathFound: boolean;
  pathScore: number;
  confidence: number;
  engine: string;
  nextActions: string[];
  filePath?: string;
}

export interface ToolEvidenceVerificationSummaryEntry {
  vulnerabilityType: string;
  target: string;
  payload: string;
  verdict: string;
  evidence: string;
  responseStatus?: number | null;
  runtimeStatus?: string;
  error?: string | null;
}

export interface ToolEvidenceReportSummaryEntry {
  reportId: string;
  title: string;
  severity: string;
  vulnerabilityType: string;
  location: string;
  verified: boolean;
  recommendation: string;
  confidence: number;
  cvssScore: number;
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
    }
  | {
      renderType: "file_list";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceFileListEntry[];
    }
  | {
      renderType: "locator_result";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceLocatorResultEntry[];
    }
  | {
      renderType: "analysis_summary";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceAnalysisSummaryEntry[];
    }
  | {
      renderType: "flow_analysis";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceFlowAnalysisEntry[];
    }
  | {
      renderType: "verification_summary";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceVerificationSummaryEntry[];
    }
  | {
      renderType: "report_summary";
      commandChain: string[];
      displayCommand: string;
      entries: ToolEvidenceReportSummaryEntry[];
    };

export interface ParsedToolEvidence {
  state: ToolEvidenceCompatibilityState;
  payload: ToolEvidencePayload | null;
  rawOutput: unknown;
  notices?: string[];
}

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
  "list_files",
  "locate_enclosing_function",
  "smart_scan",
  "quick_audit",
  "pattern_match",
  "dataflow_analysis",
  "controlflow_analysis_light",
  "logic_authz_analysis",
  "verify_vulnerability",
  "create_vulnerability_report",
]);

const NATIVE_EVIDENCE_TOOLS = new Set([
  "get_code_window",
  "search_code",
  "get_file_outline",
  "get_function_summary",
  "get_symbol_body",
  "run_code",
  "sandbox_exec",
  "list_files",
  "locate_enclosing_function",
  "smart_scan",
  "quick_audit",
  "pattern_match",
  "dataflow_analysis",
  "controlflow_analysis_light",
  "logic_authz_analysis",
  "verify_vulnerability",
  "create_vulnerability_report",
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
      language: toStringValue(record.language) || undefined,
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

function parseStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "").trim()).filter(Boolean);
}

function parseStringNumberRecord(value: unknown): Record<string, number> {
  const record = asRecord(value);
  if (!record) return {};
  return Object.fromEntries(
    Object.entries(record)
      .map(([key, item]) => [key, Number(item)])
      .filter(([, item]) => Number.isFinite(item)),
  );
}

function parseFileListEntries(value: unknown): ToolEvidenceFileListEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceFileListEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const directory = toStringValue(record.directory).trim();
    const recursive = typeof record.recursive === "boolean" ? record.recursive : null;
    const fileCount = toInt(record.file_count);
    const dirCount = toInt(record.dir_count);
    const truncated = typeof record.truncated === "boolean" ? record.truncated : null;
    if (!directory || recursive === null || fileCount === null || dirCount === null || truncated === null) {
      return null;
    }
    parsed.push({
      directory,
      pattern: toStringValue(record.pattern) || undefined,
      recursive,
      files: parseStringArray(record.files),
      directories: parseStringArray(record.directories),
      fileCount,
      dirCount,
      truncated,
      recommendedNextDirectories: parseStringArray(record.recommended_next_directories),
    });
  }
  return parsed;
}

function parseLocatorEntries(value: unknown): ToolEvidenceLocatorResultEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceLocatorResultEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const filePath = toStringValue(record.file_path).trim();
    const line = toInt(record.line);
    const startLine = toInt(record.start_line);
    const endLine = toInt(record.end_line);
    const symbolName = toStringValue(record.symbol_name).trim();
    const confidence = Number(record.confidence);
    const degraded = typeof record.degraded === "boolean" ? record.degraded : null;
    if (!filePath || !symbolName || line === null || startLine === null || endLine === null || !Number.isFinite(confidence) || degraded === null) {
      return null;
    }
    parsed.push({
      filePath,
      line,
      symbolName,
      startLine,
      endLine,
      signature: toStringValue(record.signature) || undefined,
      parameters: parseStringArray(record.parameters).length > 0
        ? parseStringArray(record.parameters)
        : Array.isArray(record.parameters)
          ? record.parameters.map((item) => asRecord(item)?.name).filter(Boolean).map(String)
          : [],
      returnType: toStringValue(record.return_type) || null,
      engine: toStringValue(record.engine),
      confidence,
      degraded,
    });
  }
  return parsed;
}

function parseAnalysisSummaryEntries(value: unknown): ToolEvidenceAnalysisSummaryEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceAnalysisSummaryEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const title = toStringValue(record.title).trim();
    const summary = toStringValue(record.summary).trim();
    const hitCount = toInt(record.hit_count);
    if (!title || !summary || hitCount === null) return null;
    parsed.push({
      title,
      summary,
      severityStats: parseStringNumberRecord(record.severity_stats),
      hitCount,
      keyFiles: parseStringArray(record.key_files),
      highlights: parseStringArray(record.highlights),
      nextActions: parseStringArray(record.next_actions),
    });
  }
  return parsed;
}

function parseFlowAnalysisEntries(value: unknown): ToolEvidenceFlowAnalysisEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceFlowAnalysisEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const pathScore = Number(record.path_score);
    const confidence = Number(record.confidence);
    const pathFound = typeof record.path_found === "boolean" ? record.path_found : null;
    const reachability = toStringValue(record.reachability).trim();
    const engine = toStringValue(record.engine).trim();
    if (!Number.isFinite(pathScore) || !Number.isFinite(confidence) || pathFound === null || !reachability || !engine) {
      return null;
    }
    parsed.push({
      sourceNodes: parseStringArray(record.source_nodes),
      sinkNodes: parseStringArray(record.sink_nodes),
      taintSteps: parseStringArray(record.taint_steps),
      callChain: parseStringArray(record.call_chain),
      blockedReasons: parseStringArray(record.blocked_reasons),
      reachability,
      pathFound,
      pathScore,
      confidence,
      engine,
      nextActions: parseStringArray(record.next_actions),
      filePath: toStringValue(record.file_path) || undefined,
    });
  }
  return parsed;
}

function parseVerificationSummaryEntries(value: unknown): ToolEvidenceVerificationSummaryEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceVerificationSummaryEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const vulnerabilityType = toStringValue(record.vulnerability_type).trim();
    const target = toStringValue(record.target).trim();
    const payload = toStringValue(record.payload);
    const verdict = toStringValue(record.verdict).trim();
    if (!vulnerabilityType || !target || !verdict) return null;
    parsed.push({
      vulnerabilityType,
      target,
      payload,
      verdict,
      evidence: toStringValue(record.evidence),
      responseStatus: toInt(record.response_status),
      runtimeStatus: toStringValue(record.runtime_status) || undefined,
      error: toStringValue(record.error) || null,
    });
  }
  return parsed;
}

function parseReportSummaryEntries(value: unknown): ToolEvidenceReportSummaryEntry[] | null {
  if (!Array.isArray(value)) return null;
  const parsed: ToolEvidenceReportSummaryEntry[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) return null;
    const reportId = toStringValue(record.report_id).trim();
    const title = toStringValue(record.title).trim();
    const severity = toStringValue(record.severity).trim();
    const vulnerabilityType = toStringValue(record.vulnerability_type).trim();
    const location = toStringValue(record.location).trim();
    const recommendation = toStringValue(record.recommendation);
    const confidence = Number(record.confidence);
    const cvssScore = Number(record.cvss_score);
    const verified = typeof record.verified === "boolean" ? record.verified : null;
    if (!reportId || !title || !severity || !vulnerabilityType || !location || verified === null || !Number.isFinite(confidence) || !Number.isFinite(cvssScore)) {
      return null;
    }
    parsed.push({
      reportId,
      title,
      severity,
      vulnerabilityType,
      location,
      verified,
      recommendation,
      confidence,
      cvssScore,
    });
  }
  return parsed;
}

export function asParsedToolEvidence(
  value: ParsedToolEvidence | ToolEvidencePayload | null | undefined,
): ParsedToolEvidence | null {
  if (!value) return null;
  if ("state" in value) return value;
  return {
    state: "native",
    payload: value,
    rawOutput: value,
  };
}

export function getToolEvidencePayload(
  value: ParsedToolEvidence | ToolEvidencePayload | null | undefined,
): ToolEvidencePayload | null {
  return asParsedToolEvidence(value)?.payload ?? null;
}

export function isToolEvidenceCapableTool(toolName: string | null | undefined): boolean {
  return TOOL_EVIDENCE_TOOLS.has(String(toolName || "").trim().toLowerCase());
}

export function expectsNativeToolEvidence(toolName: string | null | undefined): boolean {
  return NATIVE_EVIDENCE_TOOLS.has(String(toolName || "").trim().toLowerCase());
}

function parseToolEvidenceCandidate(metadata: Record<string, unknown> | null): ToolEvidencePayload | null {
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

  if (renderType === "file_list") {
    const entries = parseFileListEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "locator_result") {
    const entries = parseLocatorEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "analysis_summary") {
    const entries = parseAnalysisSummaryEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "flow_analysis") {
    const entries = parseFlowAnalysisEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "verification_summary") {
    const entries = parseVerificationSummaryEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  if (renderType === "report_summary") {
    const entries = parseReportSummaryEntries(metadata.entries);
    return entries ? { renderType, commandChain, displayCommand, entries } : null;
  }

  return null;
}

export function parseToolEvidence(value: unknown): ToolEvidencePayload | null {
  const container = asRecord(value);
  return parseToolEvidenceCandidate(asRecord(container?.metadata) || container);
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
      language: detectLanguageFromPath(filePath),
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

function wrapParsedEvidence(
  state: ToolEvidenceCompatibilityState,
  payload: ToolEvidencePayload | null,
  rawOutput: unknown,
  notices?: string[],
): ParsedToolEvidence {
  return { state, payload, rawOutput, notices };
}

function extractPrimaryRecord(value: unknown): Record<string, unknown> | null {
  const direct = asRecord(value);
  if (!direct) return null;
  return asRecord(direct.data) || direct;
}

function synthesizeFileListEvidence(toolOutput: unknown, toolMetadata?: unknown): ToolEvidencePayload | null {
  const source = asRecord(toolMetadata) || extractPrimaryRecord(toolOutput);
  if (!source) return null;
  const directory = toStringValue(source.directory).trim();
  const recursive = typeof source.recursive === "boolean" ? source.recursive : false;
  if (!directory) return null;
  const commandChain = buildFallbackCommandChain({ toolName: "list_files", toolMetadata });
  return {
    renderType: "file_list",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        directory,
        pattern: toStringValue(source.pattern) || undefined,
        recursive,
        files: parseStringArray(source.files),
        directories: parseStringArray(source.directories),
        fileCount: toInt(source.file_count) ?? parseStringArray(source.files).length,
        dirCount: toInt(source.dir_count) ?? parseStringArray(source.directories).length,
        truncated: Boolean(source.truncated),
        recommendedNextDirectories: parseStringArray(source.recommended_next_directories),
      },
    ],
  };
}

function synthesizeLocatorEvidence(toolOutput: unknown, toolMetadata?: unknown): ToolEvidencePayload | null {
  const source = extractPrimaryRecord(toolOutput) || asRecord(toolMetadata);
  const symbol = asRecord(source?.symbol);
  const resolution = asRecord(source?.resolution);
  if (!source || !symbol || !resolution) return null;
  const filePath = toStringValue(source.file_path).trim();
  const line = toInt(source.line);
  const startLine = toInt(symbol.start_line);
  const endLine = toInt(symbol.end_line);
  const symbolName = toStringValue(symbol.name).trim();
  if (!filePath || line === null || startLine === null || endLine === null || !symbolName) return null;
  const commandChain = buildFallbackCommandChain({ toolName: "locate_enclosing_function", toolMetadata });
  return {
    renderType: "locator_result",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        filePath,
        line,
        symbolName,
        startLine,
        endLine,
        signature: toStringValue(symbol.signature) || undefined,
        parameters: Array.isArray(symbol.parameters)
          ? symbol.parameters.map((item) => asRecord(item)?.name).filter(Boolean).map(String)
          : [],
        returnType: toStringValue(symbol.return_type) || null,
        engine: toStringValue(resolution.engine || resolution.method),
        confidence: Number(resolution.confidence) || 0,
        degraded: Boolean(resolution.degraded),
      },
    ],
  };
}

function synthesizeAnalysisSummaryEvidence(
  toolName: string,
  toolOutput: unknown,
  toolMetadata?: unknown,
): ToolEvidencePayload | null {
  const metadata = asRecord(toolMetadata) || {};
  const source = extractPrimaryRecord(toolOutput) || metadata;
  const findings = Array.isArray(source.findings) ? source.findings : [];
  const details = Array.isArray(source.details) ? source.details : [];
  const severityStats =
    parseStringNumberRecord(source.by_severity) ||
    parseStringNumberRecord(source.severity_stats);
  const hitCount =
    toInt(source.total_findings) ??
    toInt(source.findings_count) ??
    toInt(source.matches) ??
    findings.length ??
    details.length;
  const keyFiles = Array.from(
    new Set(
      [
        ...parseStringArray(source.high_risk_files),
        ...findings.map((item) => toStringValue(asRecord(item)?.file_path)),
        ...details.map((item) => toStringValue(asRecord(item)?.file_path)),
      ].filter(Boolean),
    ),
  );
  const highlights = [
    ...findings.slice(0, 5).map((item) => {
      const record = asRecord(item);
      return `${toStringValue(record?.vulnerability_type || record?.type)} @ ${toStringValue(record?.file_path)}:${toInt(record?.line_number ?? record?.line) ?? "?"}`;
    }),
    ...details.slice(0, 5).map((item) => {
      const record = asRecord(item);
      return `${toStringValue(record?.type)} @ ${toStringValue(record?.file_path)}:${toInt(record?.line) ?? "?"}`;
    }),
  ].filter(Boolean);
  const summary =
    toStringValue(source.summary) ||
    `${toolName} 发现 ${hitCount ?? 0} 个潜在问题。`;
  const commandChain = buildFallbackCommandChain({ toolName, toolMetadata });
  if (hitCount === null) return null;
  return {
    renderType: "analysis_summary",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        title: `${toolName} summary`,
        summary,
        severityStats,
        hitCount,
        keyFiles,
        highlights,
        nextActions: parseStringArray(source.next_actions).length > 0
          ? parseStringArray(source.next_actions)
          : ["继续查看关键命中上下文并确认可利用性。"],
      },
    ],
  };
}

function synthesizeFlowAnalysisEvidence(
  toolName: string,
  toolOutput: unknown,
  toolMetadata?: unknown,
): ToolEvidencePayload | null {
  const metadata = asRecord(toolMetadata) || {};
  const dataRecord = extractPrimaryRecord(toolOutput) || metadata;
  const analysis = asRecord(dataRecord.analysis) || asRecord(dataRecord.flow) || dataRecord;
  if (!analysis) return null;
  const commandChain = buildFallbackCommandChain({ toolName, toolMetadata });
  const sourceNodes = parseStringArray(analysis.source_nodes).length > 0
    ? parseStringArray(analysis.source_nodes)
    : parseStringArray(analysis.proof_nodes);
  const sinkNodes = parseStringArray(analysis.sink_nodes).length > 0
    ? parseStringArray(analysis.sink_nodes)
    : parseStringArray(analysis.evidence);
  const taintSteps = parseStringArray(analysis.taint_steps).length > 0
    ? parseStringArray(analysis.taint_steps)
    : parseStringArray(analysis.evidence);
  const callChain = parseStringArray(analysis.call_chain).length > 0
    ? parseStringArray(analysis.call_chain)
    : parseStringArray(analysis.proof_nodes);
  const blockedReasons = parseStringArray(analysis.blocked_reasons);
  const pathFound =
    typeof analysis.path_found === "boolean"
      ? analysis.path_found
      : Boolean(
          analysis.missing_authz_checks || analysis.resource_scope_mismatch || analysis.idor_path,
        );
  const pathScore = Number(analysis.path_score ?? analysis.confidence ?? (pathFound ? 1 : 0));
  const confidence = Number(analysis.confidence ?? pathScore ?? 0);
  return {
    renderType: "flow_analysis",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        sourceNodes,
        sinkNodes,
        taintSteps,
        callChain,
        blockedReasons,
        reachability: toStringValue(analysis.reachability) || (pathFound ? "reachable" : blockedReasons.length > 0 ? "blocked" : "unknown"),
        pathFound,
        pathScore: Number.isFinite(pathScore) ? pathScore : 0,
        confidence: Number.isFinite(confidence) ? confidence : 0,
        engine: toStringValue(metadata.engine || analysis.analysis_engine || "legacy"),
        nextActions: parseStringArray(analysis.next_actions).length > 0
          ? parseStringArray(analysis.next_actions)
          : ["补充上下文后继续验证路径与控制条件。"],
        filePath: toStringValue(metadata.file_path || dataRecord.file_path) || undefined,
      },
    ],
  };
}

function synthesizeVerificationSummaryEvidence(
  toolOutput: unknown,
  toolMetadata?: unknown,
  toolInput?: unknown,
): ToolEvidencePayload | null {
  const metadata = asRecord(toolMetadata) || {};
  const dataRecord = extractPrimaryRecord(toolOutput) || metadata;
  const inputRecord = asRecord(toolInput);
  const vulnerabilityType = toStringValue(metadata.vulnerability_type || dataRecord.vulnerability_type || inputRecord?.vulnerability_type).trim();
  const target = toStringValue(inputRecord?.target_url || metadata.target || dataRecord.target).trim();
  const payloadValue = toStringValue(inputRecord?.payload || metadata.payload || dataRecord.payload);
  if (!vulnerabilityType || !target) return null;
  const isVulnerable = Boolean(metadata.is_vulnerable ?? dataRecord.is_vulnerable);
  const commandChain = buildFallbackCommandChain({ toolName: "verify_vulnerability", toolMetadata });
  return {
    renderType: "verification_summary",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        vulnerabilityType,
        target,
        payload: payloadValue,
        verdict: isVulnerable ? "confirmed" : "not_confirmed",
        evidence: toStringValue(metadata.evidence || dataRecord.evidence),
        responseStatus: toInt(metadata.response_status || dataRecord.response_status),
        runtimeStatus: toStringValue(metadata.runtime_status || dataRecord.runtime_status) || undefined,
        error: toStringValue(metadata.error || dataRecord.error) || null,
      },
    ],
  };
}

function synthesizeReportSummaryEvidence(toolOutput: unknown, toolMetadata?: unknown): ToolEvidencePayload | null {
  const source = extractPrimaryRecord(toolOutput) || asRecord(toolMetadata);
  if (!source) return null;
  const reportId = toStringValue(source.report_id || source.id).trim();
  const title = toStringValue(source.title).trim();
  const severity = toStringValue(source.severity).trim();
  const vulnerabilityType = toStringValue(source.vulnerability_type).trim();
  const location = (() => {
    const filePath = toStringValue(source.file_path).trim();
    const lineStart = toInt(source.line_start);
    return filePath ? `${filePath}${lineStart !== null ? `:${lineStart}` : ""}` : "";
  })();
  if (!reportId || !title || !severity || !vulnerabilityType || !location) return null;
  const commandChain = buildFallbackCommandChain({ toolName: "create_vulnerability_report", toolMetadata });
  return {
    renderType: "report_summary",
    commandChain,
    displayCommand: buildDisplayCommand(commandChain),
    entries: [
      {
        reportId,
        title,
        severity,
        vulnerabilityType,
        location,
        verified: Boolean(source.is_verified ?? true),
        recommendation: toStringValue(source.recommendation),
        confidence: Number(source.confidence) || 0,
        cvssScore: Number(source.cvss_score) || 0,
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
}): ParsedToolEvidence | null {
  const toolOutputRecord = asRecord(args.toolOutput);

  const outputMetadataPayload = parseToolEvidenceCandidate(asRecord(toolOutputRecord?.metadata));
  if (outputMetadataPayload) {
    return wrapParsedEvidence("native", outputMetadataPayload, args.toolOutput);
  }

  const directOutputPayload = parseToolEvidenceCandidate(toolOutputRecord);
  if (directOutputPayload) {
    return wrapParsedEvidence("native", directOutputPayload, args.toolOutput);
  }

  const metadataPayload = parseToolEvidenceCandidate(asRecord(args.toolMetadata));
  if (metadataPayload) {
    return wrapParsedEvidence("native", metadataPayload, args.toolOutput);
  }

  return null;
}

export function toolEvidenceLinesToCode(lines: ToolEvidenceLine[]): string {
  return lines.map((line) => line.text).join("\n");
}
