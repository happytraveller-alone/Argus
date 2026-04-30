import type { AgentEvent, AgentFinding } from "@/shared/api/agentTasks";
import type {
  RealtimeDisplaySeverity,
  RealtimeMergedFindingItem,
  RealtimeVerificationProgress,
} from "./components/RealtimeFindingsPanel";
import { normalizeAuditRelativePath } from "./utils";

type FalsePositiveSignalInput = {
  status?: unknown;
  authenticity?: unknown;
  verdict?: unknown;
};

type VerificationProgressInput = FalsePositiveSignalInput & {
  eventType?: unknown;
  verificationStatus?: unknown;
  isVerified?: unknown;
};

function toSafeTrimmedString(value: unknown): string {
  return String(value ?? "").trim();
}

function toOptionalString(value: unknown): string | null {
  const text = toSafeTrimmedString(value);
  return text ? text : null;
}

function toOptionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toOptionalConfidence(value: unknown): number | null {
  const numeric = toOptionalNumber(value);
  if (numeric === null) return null;
  if (numeric < 0 || numeric > 1) return null;
  return numeric;
}

function toNormalizedToken(value: unknown): string {
  return toSafeTrimmedString(value).toLowerCase().replace(/[-\s]+/g, "_");
}

function normalizeFindingPath(value: unknown): string | null {
  return normalizeAuditRelativePath(toSafeTrimmedString(value));
}

function buildFindingFingerprint(input: {
  vulnerabilityType: unknown;
  filePath: unknown;
  lineStart: unknown;
  cweId?: unknown;
}): string {
  const vulnerabilityType = toSafeTrimmedString(input.vulnerabilityType) || "unknown";
  const filePath =
    normalizeAuditRelativePath(toSafeTrimmedString(input.filePath)) || "";
  const lineStart =
    typeof input.lineStart === "number" && Number.isFinite(input.lineStart)
      ? String(input.lineStart)
      : "";
  const cweId = toSafeTrimmedString(input.cweId);
  return [vulnerabilityType, filePath, lineStart, cweId].join("|");
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function isTruthyBoolean(value: unknown): boolean {
  return value === true;
}

function hasLegacyVerificationSignal(metadata: Record<string, unknown>): boolean {
  if (typeof metadata.status === "string" && metadata.status.trim()) return true;
  if (typeof metadata.authenticity === "string" && metadata.authenticity.trim()) {
    return true;
  }
  if (typeof metadata.verdict === "string" && metadata.verdict.trim()) return true;
  return isTruthyBoolean(metadata.is_verified);
}

function shouldIncludeEventFinding(
  metadata: Record<string, unknown>,
  eventType: string,
): boolean {
  const scope = toNormalizedToken(metadata.finding_scope);
  if (scope === "verification_queue") return true;
  if (scope === "analysis_preview") return false;

  if (eventType === "finding_verified") return true;
  return hasLegacyVerificationSignal(metadata);
}

function buildMergeKey(input: {
  verificationTodoId?: unknown;
  verificationFingerprint?: unknown;
  fallbackFingerprint: string;
}): string {
  return (
    toOptionalString(input.verificationTodoId) ||
    toOptionalString(input.verificationFingerprint) ||
    input.fallbackFingerprint
  );
}

export function isFalsePositiveSignal(input: FalsePositiveSignalInput): boolean {
  const status = toNormalizedToken(input.status);
  const authenticity = toNormalizedToken(input.authenticity);
  const verdict = toNormalizedToken(input.verdict);
  return (
    status === "false_positive" ||
    authenticity === "false_positive" ||
    verdict === "false_positive"
  );
}

export function normalizeVerificationProgress(
  input: VerificationProgressInput,
): RealtimeVerificationProgress {
  const status = toNormalizedToken(input.status);
  const verificationStatus = toNormalizedToken(input.verificationStatus);
  if (status === "verified" || verificationStatus === "verified") {
    return "verified";
  }
  return "pending";
}

export function normalizeDisplaySeverity(
  severity: unknown,
  isFalsePositive: boolean,
): RealtimeDisplaySeverity {
  if (isFalsePositive) return "invalid";

  const normalized = toNormalizedToken(severity);
  if (normalized === "critical" || normalized === "严重") {
    return "critical";
  }
  if (normalized === "high" || normalized === "高危" || normalized === "高") {
    return "high";
  }
  if (normalized === "medium" || normalized === "中危" || normalized === "中") {
    return "medium";
  }
  if (normalized === "low" || normalized === "低危" || normalized === "低") {
    return "low";
  }
  if (
    normalized === "info" ||
    normalized === "informational" ||
    normalized === "信息"
  ) {
    return "low";
  }
  if (normalized === "invalid" || normalized === "无效") {
    return "invalid";
  }
  return "medium";
}

export function fromAgentFinding(
  finding: AgentFinding,
): RealtimeMergedFindingItem {
  const findingRecord = finding as unknown as Record<string, unknown>;
  const normalizedFilePath = normalizeFindingPath(finding.file_path);
  const fingerprint = buildFindingFingerprint({
    vulnerabilityType: finding.vulnerability_type,
    filePath: normalizedFilePath,
    lineStart: finding.line_start,
    cweId: finding.cwe_id,
  });
  const mergeKey = buildMergeKey({
    verificationTodoId: findingRecord.verification_todo_id,
    verificationFingerprint: findingRecord.verification_fingerprint,
    fallbackFingerprint: fingerprint,
  });
  const falsePositive = isFalsePositiveSignal({
    status: finding.status,
  });
  const verificationProgress = normalizeVerificationProgress({
    status: finding.status,
    verificationStatus: findingRecord.verification_status,
    isVerified: finding.is_verified,
  });
  const displaySeverity = normalizeDisplaySeverity(finding.severity, falsePositive);

  return {
    id: finding.id,
    merge_key: mergeKey,
    fingerprint,
    title: toSafeTrimmedString(finding.title) || "发现漏洞",
    display_title: toOptionalString(finding.display_title),
    description: toOptionalString(finding.description),
    description_markdown: toOptionalString(finding.description_markdown),
    severity: toSafeTrimmedString(finding.severity) || "medium",
    display_severity: displaySeverity,
    verification_progress: verificationProgress,
    vulnerability_type: toSafeTrimmedString(finding.vulnerability_type) || "unknown",
    file_path: normalizedFilePath,
    line_start: finding.line_start ?? null,
    line_end: finding.line_end ?? null,
    cwe_id: toOptionalString(finding.cwe_id),
    status: toOptionalString(finding.status),
    verdict: toOptionalString(finding.verdict),
    verification_status: toOptionalString(findingRecord.verification_status),
    code_snippet: finding.code_snippet ?? null,
    code_context: finding.code_context ?? null,
    function_trigger_flow:
      Array.isArray(finding.function_trigger_flow) &&
      finding.function_trigger_flow.length > 0
        ? finding.function_trigger_flow.map((item) => String(item))
        : null,
    verification_evidence: finding.verification_evidence ?? null,
    reachability_file: normalizeFindingPath(finding.reachability_file),
    reachability_function: finding.reachability_function ?? null,
    reachability_function_start_line: finding.reachability_function_start_line ?? null,
    reachability_function_end_line: finding.reachability_function_end_line ?? null,
    context_start_line: finding.context_start_line ?? null,
    context_end_line: finding.context_end_line ?? null,
    authenticity: toOptionalString(finding.authenticity),
    confidence: toOptionalConfidence(finding.ai_confidence ?? finding.confidence),
    timestamp: finding.created_at ?? null,
    is_verified: toNormalizedToken(finding.status) === "verified",
    verification_todo_id: toOptionalString(findingRecord.verification_todo_id),
    verification_fingerprint: toOptionalString(
      findingRecord.verification_fingerprint,
    ),
    detailMode: falsePositive ? "false_positive_reason" : "detail",
  };
}

export function fromAgentEvent(event: AgentEvent): RealtimeMergedFindingItem | null {
  const eventType = toNormalizedToken(event.event_type);
  if (
    eventType !== "finding" &&
    eventType !== "finding_new" &&
    eventType !== "finding_update" &&
    eventType !== "finding_verified"
  ) {
    return null;
  }

  const metadata = asRecord(event.metadata);
  if (!shouldIncludeEventFinding(metadata, eventType)) {
    return null;
  }
  const falsePositive = isFalsePositiveSignal({
    status: metadata.status,
  });
  const verificationProgress = normalizeVerificationProgress({
    eventType,
    status: metadata.status,
    verificationStatus: metadata.verification_status,
    isVerified: metadata.is_verified,
  });

  const displayTitle = toOptionalString(metadata.display_title);
  const title =
    displayTitle ||
    toOptionalString(metadata.title) ||
    toOptionalString(event.message) ||
    "发现漏洞";
  const severity = toSafeTrimmedString(metadata.severity) || "medium";
  const vulnerabilityType =
    toSafeTrimmedString(metadata.vulnerability_type) || "unknown";
  const filePath = normalizeFindingPath(metadata.file_path);
  const lineStart = toOptionalNumber(metadata.line_start);
  const confidence = toOptionalConfidence(
    metadata.confidence ?? metadata.ai_confidence,
  );
  const timestamp =
    toOptionalString(event.timestamp) || toOptionalString(metadata.timestamp);
  const fingerprint = buildFindingFingerprint({
    vulnerabilityType,
    filePath,
    lineStart,
    cweId: metadata.cwe_id,
  });
  const mergeKey = buildMergeKey({
    verificationTodoId: metadata.verification_todo_id,
    verificationFingerprint: metadata.verification_fingerprint,
    fallbackFingerprint: fingerprint,
  });

  return {
    id:
      toSafeTrimmedString(event.finding_id) ||
      toSafeTrimmedString(metadata.id) ||
      toSafeTrimmedString(event.id) ||
      `finding-${Date.now()}`,
    merge_key: mergeKey,
    fingerprint,
    title: toOptionalString(metadata.title) || title,
    display_title: displayTitle,
    description: toOptionalString(metadata.description),
    description_markdown: toOptionalString(metadata.description_markdown),
    severity,
    display_severity: normalizeDisplaySeverity(severity, falsePositive),
    verification_progress: verificationProgress,
    vulnerability_type: vulnerabilityType,
    file_path: filePath,
    line_start: lineStart,
    line_end: toOptionalNumber(metadata.line_end),
    cwe_id: toOptionalString(metadata.cwe_id),
    status: toOptionalString(metadata.status),
    verification_status: toOptionalString(metadata.verification_status),
    code_snippet: toOptionalString(metadata.code_snippet),
    code_context: toOptionalString(metadata.code_context),
    function_trigger_flow: Array.isArray(metadata.function_trigger_flow)
      ? metadata.function_trigger_flow.map((item) => String(item))
      : null,
    verification_evidence:
      toOptionalString(metadata.verification_evidence) ||
      toOptionalString(metadata.verification_details),
    reachability_file: normalizeFindingPath(metadata.reachability_file),
    reachability_function: toOptionalString(metadata.reachability_function),
    reachability_function_start_line: toOptionalNumber(
      metadata.reachability_function_start_line,
    ),
    reachability_function_end_line: toOptionalNumber(
      metadata.reachability_function_end_line,
    ),
    context_start_line: toOptionalNumber(metadata.context_start_line),
    context_end_line: toOptionalNumber(metadata.context_end_line),
    authenticity: toOptionalString(metadata.authenticity),
    confidence,
    timestamp,
    is_verified: toNormalizedToken(metadata.status) === "verified",
    verification_todo_id: toOptionalString(metadata.verification_todo_id),
    verification_fingerprint: toOptionalString(metadata.verification_fingerprint),
    detailMode: falsePositive ? "false_positive_reason" : "detail",
  };
}
