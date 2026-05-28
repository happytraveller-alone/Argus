/**
 * Intelligent Tasks API Client
 * API calls for intelligent audit task management
 */

import { apiClient } from "@/shared/api/serverClient";

export type IntelligentTaskStatus =
	| "pending"
	| "running"
	| "completed"
	| "failed"
	| "cancelled";

export interface PocResult {
	language: string;
	exitCode: number;
	stdout: string;
	stderr: string;
	reproduced: boolean;
}

export interface EvidenceCodeSnippet {
	file?: string | null;
	lineStart?: number | null;
	lineEnd?: number | null;
	code: string;
	language?: string | null;
}

export interface CallHop {
	file?: string | null;
	line?: number | null;
	function?: string | null;
	snippet?: string | null;
	language?: string | null;
}

export interface IntelligentTaskFinding {
	id: string;
	severity: string;
	summary: string;
	evidence: string;
	file?: string | null;
	lineStart?: number | null;
	lineEnd?: number | null;
	vulnClass?: string | null;
	confidence?: number | null;
	pocResult?: PocResult | null;
	validationStatus?: string | null;
	reachable?: boolean | null;
	traceSummary?: string | null;
	coverageMatrix?: Record<string, unknown> | null;
	/** User verdict: null=pending, "verified"=true positive, "false_positive"=false positive */
	userVerdict?: string | null;
	/** Phase D: camelCase fields from backend serde output */
	cweId?: string | null;
	scopeType?: "file" | "module";
	module?: string | null;
	resolvedFilePath?: string | null;
	evidenceCodeSnippets?: EvidenceCodeSnippet[];
	evidenceProse?: string;
	reachabilityChain?: CallHop[];
	reachabilityEntryPoint?: string;
}

export interface IntelligentTaskEventLogEntry {
	kind: string;
	timestamp: string;
	message?: string;
	data?: unknown;
}

export interface IntelligentTaskRecord {
	taskId: string;
	projectId: string;
	projectName?: string | null;
	projectRoot?: string | null;
	status: IntelligentTaskStatus;
	createdAt: string;
	startedAt?: string;
	completedAt?: string;
	durationMs?: number;
	llmModel: string;
	llmFingerprint: string;
	inputSummary: string;
	eventLog: IntelligentTaskEventLogEntry[];
	reportSummary: string;
	findings: IntelligentTaskFinding[];
	failureReason?: string;
	failureStage?: string;
	/** True when scan ran in degraded mode (codegraph indexing unavailable) */
	partialAnalysis?: boolean;
}

/**
 * Create a new intelligent audit task
 */
export async function createIntelligentTask(
	projectId: string,
): Promise<IntelligentTaskRecord> {
	const response = await apiClient.post(`/intelligent-tasks`, { projectId });
	return response.data;
}

/**
 * List recent intelligent tasks
 */
export async function listIntelligentTasks(
	limit?: number,
	options?: { projectId?: string; skip?: number },
): Promise<IntelligentTaskRecord[]> {
	const params: Record<string, string> = {};
	if (limit !== undefined) {
		params.limit = String(limit);
	}
	if (options?.skip !== undefined) {
		params.skip = String(options.skip);
	}
	if (options?.projectId) {
		params.projectId = options.projectId;
	}
	const response = await apiClient.get(`/intelligent-tasks`, { params });
	return Array.isArray(response.data) ? response.data : [];
}

export async function listAllProjectIntelligentTasks(
	projectId: string,
): Promise<IntelligentTaskRecord[]> {
	const batchSize = 200;
	const tasks: IntelligentTaskRecord[] = [];
	let skip = 0;

	while (true) {
		const page = await listIntelligentTasks(batchSize, { projectId, skip });
		if (page.length === 0) break;
		tasks.push(...page);
		if (page.length < batchSize) break;
		skip += page.length;
	}

	return tasks;
}

/**
 * Get a single intelligent task by ID
 */
export async function getIntelligentTask(
	taskId: string,
): Promise<IntelligentTaskRecord> {
	const response = await apiClient.get(`/intelligent-tasks/${taskId}`);
	return response.data;
}

/**
 * Cancel an intelligent task
 */
export async function cancelIntelligentTask(
	taskId: string,
): Promise<IntelligentTaskRecord> {
	const response = await apiClient.post(`/intelligent-tasks/${taskId}/cancel`);
	return response.data;
}

export async function deleteIntelligentTask(taskId: string): Promise<{
	deleted: boolean;
	taskId: string;
	terminalStatus: IntelligentTaskStatus;
}> {
	const response = await apiClient.delete(`/intelligent-tasks/${taskId}`);
	return response.data;
}

/**
 * Set user verdict on an intelligent task finding.
 * verdict: "verified" | "false_positive" | null (revert to pending)
 */
export async function setIntelligentFindingVerdict(
	taskId: string,
	findingId: string,
	verdict: string | null,
): Promise<IntelligentTaskFinding> {
	const response = await apiClient.post(
		`/intelligent-tasks/${taskId}/findings/${findingId}/verdict`,
		{ verdict },
	);
	return response.data;
}
