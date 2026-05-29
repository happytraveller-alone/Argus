import type { AgentFinding } from "@/shared/api/agentTasks";
import type {
	IntelligentTaskFinding,
	IntelligentTaskRecord,
} from "@/shared/api/intelligentTasks";

/**
 * Project intelligent-task findings onto the legacy AgentFinding shape used by
 * the unified finding-detail view. Intelligent finding detail currently relies
 * on route state instead of a dedicated backend finding endpoint.
 */
export function buildProjectDetailAgentFindingSnapshot(
	finding: IntelligentTaskFinding,
	record: IntelligentTaskRecord,
): AgentFinding {
	// Root-cause body precedence:
	//   1. evidenceProse — clean prose written by the hunt LLM (no path:line tokens).
	//   2. summary       — the hunt prompt's `description` field, also clean prose.
	//   3. evidence      — last-resort fallback. Backend's `enrich_evidence()` prepends
	//                      "{file}:{line_start}-{line_end} [{vuln_class}]" which the
	//                      viewModel's stripPathSentences erases sentence-by-sentence,
	//                      so this path tends to render blank — preferred over silently
	//                      losing data, but #1/#2 should usually win.
	const evidenceProse = String(finding.evidenceProse ?? "").trim();
	const summary = String(finding.summary ?? "").trim();
	const evidenceFallback = String(finding.evidence ?? "").trim();
	const rootCauseBody = evidenceProse || summary || evidenceFallback;
	const traceSummary = String(finding.traceSummary ?? "").trim();
	const validationStatus = String(finding.validationStatus ?? "").trim();
	const isFalsePositive = finding.userVerdict === "false_positive";

	const sections: string[] = [];
	if (rootCauseBody) sections.push(`### 根因解释\n${rootCauseBody}`);
	const verificationParts: string[] = [];
	if (traceSummary) verificationParts.push(traceSummary);
	if (validationStatus) verificationParts.push(`验证状态：${validationStatus}`);
	if (finding.reachable != null) {
		verificationParts.push(`可达性：${finding.reachable ? "可达" : "不可达"}`);
	}
	if (verificationParts.length > 0) {
		sections.push(`### 验证结论\n${verificationParts.join("\n\n")}`);
	}

	const descriptionMarkdown = sections.join("\n\n");

	return {
		id: finding.id,
		task_id: record.taskId,
		vulnerability_type: finding.vulnClass ?? null,
		severity: finding.severity ?? null,
		title: finding.summary ?? null,
		display_title: finding.summary ?? null,
		description: rootCauseBody || null,
		description_markdown: descriptionMarkdown || rootCauseBody || null,
		file_path: finding.file ?? null,
		line_start: finding.lineStart ?? null,
		line_end: finding.lineEnd ?? null,
		resolved_file_path: finding.resolvedFilePath ?? null,
		code_snippet: null,
		code_context: null,
		cwe_id: finding.cweId ?? null,
		confidence: finding.confidence ?? null,
		ai_confidence: finding.confidence ?? null,
		verdict: finding.userVerdict ?? null,
		status: isFalsePositive ? "false_positive" : validationStatus || null,
		authenticity: isFalsePositive ? "false_positive" : null,
		verification_evidence: traceSummary || rootCauseBody || null,
		projectId: record.projectId,
		projectName: record.projectName ?? null,
		llmModel: record.llmModel,
		projectRoot: record.projectRoot ?? null,
		evidenceCodeSnippets: finding.evidenceCodeSnippets,
		evidenceProse: finding.evidenceProse,
		reachabilityChain: finding.reachabilityChain,
		reachabilityEntryPoint: finding.reachabilityEntryPoint,
	};
}
