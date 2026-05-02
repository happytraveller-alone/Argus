import { DEFAULT_API_BASE_URL, normalizeApiBaseUrl } from "@/shared/api/apiBase";
import { apiClient } from "@/shared/api/serverClient";

export interface AgentTaskDefectSummary {
	scope?: string | null;
	total_count?: number | null;
	severity_counts?: {
		critical?: number | null;
		high?: number | null;
		medium?: number | null;
		low?: number | null;
		info?: number | null;
	} | null;
	status_counts?: {
		pending?: number | null;
		verified?: number | null;
		false_positive?: number | null;
		[key: string]: number | null | undefined;
	} | null;
}

export interface AgentTask {
	id: string;
	project_id: string;
	name: string;
	description?: string | null;
	task_type?: string | null;
	status: string;
	current_phase?: string | null;
	current_step?: string | null;
	total_files?: number | null;
	indexed_files?: number | null;
	analyzed_files?: number | null;
	files_with_findings?: number | null;
	total_chunks?: number | null;
	findings_count?: number | null;
	verified_count?: number | null;
	false_positive_count?: number | null;
	total_iterations?: number | null;
	tool_calls_count?: number | null;
	tokens_used?: number | null;
	critical_count?: number | null;
	high_count?: number | null;
	medium_count?: number | null;
	low_count?: number | null;
	verified_critical_count?: number | null;
	verified_high_count?: number | null;
	verified_medium_count?: number | null;
	verified_low_count?: number | null;
	defect_summary?: AgentTaskDefectSummary | null;
	quality_score?: number | null;
	security_score?: number | null;
	created_at: string;
	started_at?: string | null;
	completed_at?: string | null;
	updated_at?: string | null;
	progress_percentage?: number | null;
	audit_scope?: Record<string, unknown> | null;
	target_vulnerabilities?: string[] | null;
	verification_level?: string | null;
	tool_evidence_protocol?: string | null;
	exclude_patterns?: string[] | null;
	target_files?: string[] | null;
	error_message?: string | null;
	[key: string]: unknown;
}

export interface AgentFinding {
	id: string;
	task_id: string;
	vulnerability_type?: string | null;
	severity?: string | null;
	title?: string | null;
	display_title?: string | null;
	description?: string | null;
	description_markdown?: string | null;
	file_path?: string | null;
	line_start?: number | null;
	line_end?: number | null;
	resolved_file_path?: string | null;
	resolved_line_start?: number | null;
	code_snippet?: string | null;
	code_context?: string | null;
	cwe_id?: string | null;
	cwe_name?: string | null;
	context_start_line?: number | null;
	context_end_line?: number | null;
	status?: string | null;
	is_verified?: boolean | null;
	verdict?: string | null;
	reachability?: string | null;
	authenticity?: string | null;
	verification_evidence?: string | null;
	verification_todo_id?: string | null;
	verification_fingerprint?: string | null;
	reachability_file?: string | null;
	reachability_function?: string | null;
	reachability_function_start_line?: number | null;
	reachability_function_end_line?: number | null;
	flow_path_score?: number | null;
	flow_call_chain?: string[] | null;
	function_trigger_flow?: string[] | null;
	flow_control_conditions?: string | null;
	logic_authz_evidence?: string | null;
	has_poc?: boolean | null;
	poc_code?: string | null;
	trigger_flow?: string | null;
	poc_trigger_chain?: string[] | null;
	suggestion?: string | null;
	fix_code?: string | null;
	report?: string | null;
	ai_explanation?: string | null;
	ai_confidence?: number | null;
	confidence?: number | null;
	source_node_id?: string | null;
	source_node_name?: string | null;
	created_at?: string | null;
	[key: string]: unknown;
}

export interface CreateAgentTaskPayload {
	project_id: string;
	name: string;
	description?: string | null;
	audit_scope?: Record<string, unknown> | null;
	target_vulnerabilities?: string[] | null;
	exclude_patterns?: string[] | null;
	target_files?: string[] | null;
	verification_level?: string | null;
	max_iterations?: number | null;
	token_budget?: number | null;
	[key: string]: unknown;
}

export type AgentFindingStatus =
	| "pending"
	| "verified"
	| "false_positive"
	| "open"
	| string;

export interface AgentFindingsQuery {
	include_false_positive?: boolean;
	skip?: number;
	limit?: number;
}

export type AgentReportFormat = "pdf" | "markdown" | "md" | "json" | string;

const ACTIVE_AGENT_TASK_PAYLOAD_KEYS = new Set(["project_id", "name", "description", "audit_scope"]);

function sanitizeCreateAgentTaskPayload(
	payload: CreateAgentTaskPayload,
): Partial<CreateAgentTaskPayload> {
	return Object.fromEntries(
		Object.entries(payload).filter(([key, value]) => {
			if (!ACTIVE_AGENT_TASK_PAYLOAD_KEYS.has(key)) return false;
			return value !== undefined;
		}),
	) as Partial<CreateAgentTaskPayload>;
}

function buildQuery(params?: Record<string, unknown>): string {
	const searchParams = new URLSearchParams();
	for (const [key, value] of Object.entries(params || {})) {
		if (value === undefined || value === null || value === "") continue;
		searchParams.set(key, String(value));
	}
	const query = searchParams.toString();
	return query ? `?${query}` : "";
}

function buildFindingsQuery(params?: AgentFindingsQuery): string {
	return buildQuery(params as Record<string, unknown> | undefined);
}

export function buildAgentTaskEventsUrl(taskId: string, afterSequence?: number): string {
	const query =
		afterSequence === undefined || afterSequence === null
			? ""
			: `?${new URLSearchParams({ after_sequence: String(afterSequence) }).toString()}`;
	return `${normalizeApiBaseUrl(DEFAULT_API_BASE_URL)}/agent-tasks/${encodeURIComponent(taskId)}/events${query}`;
}

export async function createAgentTask(
	payload: CreateAgentTaskPayload,
): Promise<AgentTask> {
	const response = await apiClient.post(
		"/agent-tasks/",
		sanitizeCreateAgentTaskPayload(payload),
	);
	return response.data;
}

export async function startAgentTask(taskId: string): Promise<AgentTask> {
	const response = await apiClient.post(
		`/agent-tasks/${encodeURIComponent(taskId)}/start`,
	);
	return response.data;
}

export async function getAgentTask(taskId: string): Promise<AgentTask> {
	const response = await apiClient.get(`/agent-tasks/${encodeURIComponent(taskId)}`);
	return response.data;
}

export async function getAgentTasks(params?: {
	project_id?: string;
	status?: string;
	skip?: number;
	limit?: number;
}): Promise<AgentTask[]> {
	const response = await apiClient.get(`/agent-tasks/${buildQuery(params)}`);
	return response.data;
}

export async function getAgentFindings(
	taskId: string,
	params?: AgentFindingsQuery,
): Promise<AgentFinding[]> {
	const response = await apiClient.get(
		`/agent-tasks/${encodeURIComponent(taskId)}/findings${buildFindingsQuery(params)}`,
	);
	return response.data;
}

export async function getAgentFinding(
	taskId: string,
	findingId: string,
	params?: Pick<AgentFindingsQuery, "include_false_positive">,
): Promise<AgentFinding> {
	const response = await apiClient.get(
		`/agent-tasks/${encodeURIComponent(taskId)}/findings/${encodeURIComponent(findingId)}${buildFindingsQuery(params)}`,
	);
	return response.data;
}

export async function updateAgentFindingStatus(
	taskId: string,
	findingId: string,
	status: AgentFindingStatus,
): Promise<{ message: string; finding_id: string; status: string }> {
	const response = await apiClient.patch(
		`/agent-tasks/${encodeURIComponent(taskId)}/findings/${encodeURIComponent(findingId)}/status`,
		undefined,
		{
			params: {
				status,
			},
		},
	);
	return response.data;
}

function getHeaderValue(
	headers: Record<string, unknown> | Headers | undefined,
	name: string,
): string {
	if (!headers) return "";
	if (headers instanceof Headers) return headers.get(name) || "";
	const direct = headers[name];
	if (typeof direct === "string") return direct;
	const lower = headers[name.toLowerCase()];
	return typeof lower === "string" ? lower : "";
}

function parseContentDispositionFilename(header: string): string | null {
	const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
	if (utf8Match?.[1]) {
		try {
			return decodeURIComponent(utf8Match[1].trim().replace(/^"|"$/g, ""));
		} catch {
			return utf8Match[1].trim().replace(/^"|"$/g, "") || null;
		}
	}
	const filenameMatch = header.match(/filename="?([^";]+)"?/i);
	return filenameMatch?.[1]?.trim() || null;
}

function resolveReportFilename(
	taskId: string,
	format: AgentReportFormat,
	headers: Record<string, unknown> | Headers | undefined,
): string {
	const fromHeader = parseContentDispositionFilename(
		getHeaderValue(headers, "content-disposition"),
	);
	if (fromHeader) return fromHeader;
	const extension = format === "markdown" ? "md" : String(format || "pdf");
	const date = new Date().toISOString().slice(0, 10);
	return `漏洞报告-${taskId.slice(0, 8)}-${date}.${extension}`;
}

export async function downloadAgentReport(
	taskId: string,
	format: AgentReportFormat = "pdf",
): Promise<void> {
	const response = await apiClient.get(
		`/agent-tasks/${encodeURIComponent(taskId)}/report`,
		{
			params: { format },
			responseType: "blob",
		},
	);

	const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
	const url = window.URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = resolveReportFilename(taskId, format, response.headers);
	document.body.appendChild(anchor);
	anchor.click();
	if (typeof anchor.remove === "function") {
		anchor.remove();
	} else {
		anchor.parentNode?.removeChild(anchor);
	}
	window.URL.revokeObjectURL(url);
}
