import type { RealtimeMergedFindingItem } from "./components/RealtimeFindingsPanel";
import { normalizeDisplaySeverity } from "./realtimeFindingMapper";

function resolveRealtimeFindingMergeKey(item: RealtimeMergedFindingItem): string {
  const mergeKey = String(item.merge_key || "").trim();
  if (mergeKey) return mergeKey;
  return String(item.fingerprint || "").trim();
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

function normalizeRealtimeToken(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function resolveMergedFalsePositiveState(input: {
  mergedAuthenticity: string | null;
  mergedSeverity: string;
  mergedDisplaySeverity: RealtimeMergedFindingItem["display_severity"];
  mergedDetailMode: RealtimeMergedFindingItem["detailMode"];
}): {
  displaySeverity: RealtimeMergedFindingItem["display_severity"];
  detailMode: RealtimeMergedFindingItem["detailMode"];
} {
  const mergedAuthenticity = normalizeRealtimeToken(input.mergedAuthenticity);
  const falsePositive =
    mergedAuthenticity === "false_positive" ||
    (mergedAuthenticity.length === 0 &&
      (input.mergedDetailMode === "false_positive_reason" ||
        input.mergedDisplaySeverity === "invalid"));

  if (falsePositive) {
    return {
      displaySeverity: "invalid",
      detailMode: "false_positive_reason",
    };
  }

  return {
    displaySeverity:
      input.mergedDisplaySeverity && input.mergedDisplaySeverity !== "invalid"
        ? input.mergedDisplaySeverity
        : normalizeDisplaySeverity(input.mergedSeverity, false),
    detailMode: "detail",
  };
}

export function mergeRealtimeFindingsBatch(
  prev: RealtimeMergedFindingItem[],
  incoming: RealtimeMergedFindingItem[],
  options: { source: "db" | "event" },
): RealtimeMergedFindingItem[] {
  if (!incoming.length) return prev;

  const byMergeKey = new Map<string, RealtimeMergedFindingItem>();
  for (const item of prev) {
    const key = resolveRealtimeFindingMergeKey(item);
    if (!key) continue;
    if (!byMergeKey.has(key)) {
      byMergeKey.set(key, item);
    }
  }

  for (const item of incoming) {
    const mergeKey = resolveRealtimeFindingMergeKey(item);
    if (!mergeKey) continue;
    const existing = byMergeKey.get(mergeKey);
    if (!existing) {
      byMergeKey.set(mergeKey, item);
      continue;
    }

    const preferIncoming = options.source === "db";
    const verificationProgress =
      existing.verification_progress === "verified" ||
      item.verification_progress === "verified"
        ? "verified"
        : "pending";
    const mergedSeverity = preferIncoming
      ? (item.severity || existing.severity)
      : (existing.severity || item.severity);
    const mergedDisplaySeverity = preferIncoming
      ? (item.display_severity || existing.display_severity)
      : (existing.display_severity || item.display_severity);
    const mergedAuthenticity = preferIncoming
      ? (item.authenticity ?? existing.authenticity ?? null)
      : (existing.authenticity ?? item.authenticity ?? null);
    const mergedDetailMode = preferIncoming
      ? (item.detailMode ?? existing.detailMode ?? "detail")
      : (existing.detailMode ?? item.detailMode ?? "detail");
    const falsePositiveState = resolveMergedFalsePositiveState({
      mergedAuthenticity,
      mergedSeverity,
      mergedDisplaySeverity,
      mergedDetailMode,
    });

    byMergeKey.set(mergeKey, {
      ...existing,
      merge_key: preferIncoming
        ? (item.merge_key || existing.merge_key || mergeKey)
        : (existing.merge_key || item.merge_key || mergeKey),
      id: preferIncoming ? (item.id || existing.id) : (existing.id || item.id),
      fingerprint: preferIncoming
        ? (item.fingerprint || existing.fingerprint)
        : (existing.fingerprint || item.fingerprint),
      title: preferIncoming
        ? (item.title || existing.title)
        : (existing.title || item.title),
      severity: mergedSeverity,
      display_severity: falsePositiveState.displaySeverity,
      verification_progress: verificationProgress,
      vulnerability_type: preferIncoming
        ? (item.vulnerability_type || existing.vulnerability_type)
        : (existing.vulnerability_type || item.vulnerability_type),
      display_title: preferIncoming
        ? (item.display_title ?? existing.display_title)
        : (existing.display_title ?? item.display_title),
      description: preferIncoming
        ? (item.description ?? existing.description)
        : (existing.description ?? item.description),
      description_markdown: preferIncoming
        ? (item.description_markdown ?? existing.description_markdown)
        : (existing.description_markdown ?? item.description_markdown),
      file_path: preferIncoming
        ? (item.file_path ?? existing.file_path)
        : (existing.file_path ?? item.file_path),
      line_start: preferIncoming
        ? (item.line_start ?? existing.line_start)
        : (existing.line_start ?? item.line_start),
      line_end: preferIncoming
        ? (item.line_end ?? existing.line_end)
        : (existing.line_end ?? item.line_end),
      cwe_id: preferIncoming
        ? (item.cwe_id ?? existing.cwe_id)
        : (existing.cwe_id ?? item.cwe_id),
      code_snippet: preferIncoming
        ? (item.code_snippet ?? existing.code_snippet)
        : (existing.code_snippet ?? item.code_snippet),
      code_context: preferIncoming
        ? (item.code_context ?? existing.code_context)
        : (existing.code_context ?? item.code_context),
      function_trigger_flow: preferIncoming
        ? (item.function_trigger_flow ?? existing.function_trigger_flow)
        : (existing.function_trigger_flow ?? item.function_trigger_flow),
      verification_evidence: preferIncoming
        ? (item.verification_evidence ?? existing.verification_evidence)
        : (existing.verification_evidence ?? item.verification_evidence),
      verification_todo_id: preferIncoming
        ? (item.verification_todo_id ?? existing.verification_todo_id ?? null)
        : (existing.verification_todo_id ?? item.verification_todo_id ?? null),
      verification_fingerprint: preferIncoming
        ? (item.verification_fingerprint ?? existing.verification_fingerprint ?? null)
        : (existing.verification_fingerprint ?? item.verification_fingerprint ?? null),
      authenticity: mergedAuthenticity,
      detailMode: falsePositiveState.detailMode,
      reachability_file: preferIncoming
        ? (item.reachability_file ?? existing.reachability_file)
        : (existing.reachability_file ?? item.reachability_file),
      reachability_function: preferIncoming
        ? (item.reachability_function ?? existing.reachability_function)
        : (existing.reachability_function ?? item.reachability_function),
      reachability_function_start_line: preferIncoming
        ? (item.reachability_function_start_line ?? existing.reachability_function_start_line)
        : (existing.reachability_function_start_line ?? item.reachability_function_start_line),
      reachability_function_end_line: preferIncoming
        ? (item.reachability_function_end_line ?? existing.reachability_function_end_line)
        : (existing.reachability_function_end_line ?? item.reachability_function_end_line),
      context_start_line: preferIncoming
        ? (item.context_start_line ?? existing.context_start_line)
        : (existing.context_start_line ?? item.context_start_line),
      context_end_line: preferIncoming
        ? (item.context_end_line ?? existing.context_end_line)
        : (existing.context_end_line ?? item.context_end_line),
      confidence: preferIncoming
        ? (item.confidence ?? existing.confidence ?? null)
        : (existing.confidence ?? item.confidence ?? null),
      timestamp: pickNewerIsoTimestamp(existing.timestamp, item.timestamp),
      is_verified: verificationProgress === "verified",
    });
  }

  const merged = Array.from(byMergeKey.values());
  merged.sort((a, b) =>
    String(b.timestamp || "").localeCompare(String(a.timestamp || "")),
  );
  return merged.slice(0, 500);
}
