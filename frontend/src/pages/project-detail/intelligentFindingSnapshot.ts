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
	const evidence = String(finding.evidence ?? "").trim();
	const traceSummary = String(finding.traceSummary ?? "").trim();
	const validationStatus = String(finding.validationStatus ?? "").trim();
	const isFalsePositive = finding.userVerdict === "false_positive";

	const sections: string[] = [];
	if (evidence) sections.push(`### 根因解释\n${evidence}`);
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
		description: evidence || null,
		description_markdown: descriptionMarkdown || evidence || null,
		file_path: finding.file ?? null,
		line_start: finding.lineStart ?? null,
		line_end: finding.lineEnd ?? null,
		code_snippet: null,
		code_context: null,
		confidence: finding.confidence ?? null,
		ai_confidence: finding.confidence ?? null,
		verdict: finding.userVerdict ?? null,
		status: isFalsePositive ? "false_positive" : validationStatus || null,
		authenticity: isFalsePositive ? "false_positive" : null,
		verification_evidence: traceSummary || evidence || null,
		projectId: record.projectId,
		projectName: record.projectName ?? null,
		llmModel: record.llmModel,
		projectRoot: record.projectRoot ?? null,
	};
}
