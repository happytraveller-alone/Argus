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

export interface IntelligentTaskFinding {
	id: string;
	severity: string;
	summary: string;
	evidence: string;
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
): Promise<IntelligentTaskRecord[]> {
	const params: Record<string, string> = {};
	if (limit !== undefined) {
		params.limit = String(limit);
	}
	const response = await apiClient.get(`/intelligent-tasks`, { params });
	return Array.isArray(response.data) ? response.data : [];
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
	const response = await apiClient.post(
		`/intelligent-tasks/${taskId}/cancel`,
	);
	return response.data;
}
