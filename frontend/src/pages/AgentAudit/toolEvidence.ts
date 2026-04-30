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














function wrapParsedEvidence(
  state: ToolEvidenceCompatibilityState,
  payload: ToolEvidencePayload | null,
  rawOutput: unknown,
  notices?: string[],
): ParsedToolEvidence {
  return { state, payload, rawOutput, notices };
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
