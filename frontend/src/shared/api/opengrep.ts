/**
 * Opengrep Rules API Client
 * API calls for opengrep rule management
 */

import { apiClient } from "@/shared/api/serverClient";

export const DEFAULT_OPENGREP_RULES_LIMIT = 10;
export const ALL_OPENGREP_RULES_LIMIT = 10_000;

export interface OpengrepRule {
    id: string;
    name: string;
    language: string;
    severity: string;
    confidence?: string;
    description?: string;
    cwe?: string[];
    source: "internal" | "patch" | "json" | "upload";
    correct: boolean;
    is_active: boolean;
    created_at: string;
}

export interface OpengrepRuleDetail extends OpengrepRule {
    pattern_yaml: string;
    patch?: string;
}

export interface OpengrepRulesListResponse {
    data: OpengrepRule[];
    total: number;
}

export interface OpengrepRuleStatsResponse {
    total: number;
    active: number;
    inactive: number;
    language_count: number;
    languages: string[];
    vulnerability_type_count: number;
}

export interface OpengrepRulesQueryParams {
    language?: string;
    source?: "internal" | "patch";
    is_active?: boolean;
    keyword?: string;
    confidence?: string;
    severity?: string;
    skip?: number;
    limit?: number;
}

function normalizeOpengrepRulesListResponse(
    payload: unknown,
): OpengrepRulesListResponse {
    if (Array.isArray(payload)) {
        return {
            data: payload as OpengrepRule[],
            total: payload.length,
        };
    }

    const normalized = payload as Partial<OpengrepRulesListResponse> | null;
    const data = Array.isArray(normalized?.data) ? normalized.data : [];
    const total =
        typeof normalized?.total === "number" && Number.isFinite(normalized.total)
            ? normalized.total
            : data.length;

    return {
        data,
        total,
    };
}

/**
 * Get opengrep rules list
 */
export async function getOpengrepRulesPage(
    params?: OpengrepRulesQueryParams,
): Promise<OpengrepRulesListResponse> {
    const searchParams = new URLSearchParams();
    const limit = params?.limit ?? DEFAULT_OPENGREP_RULES_LIMIT;
    if (params?.language) searchParams.set("language", params.language);
    if (params?.source) searchParams.set("source", params.source);
    if (params?.is_active !== undefined)
        searchParams.set("is_active", String(params.is_active));
    if (params?.keyword) searchParams.set("keyword", params.keyword);
    if (params?.confidence) searchParams.set("confidence", params.confidence);
    if (params?.severity) searchParams.set("severity", params.severity);
    if (params?.skip !== undefined)
        searchParams.set("skip", String(params.skip));
    searchParams.set("limit", String(limit));

    const query = searchParams.toString();
    const response = await apiClient.get(
        `/static-tasks/rules${query ? `?${query}` : ""}`,
    );
    return normalizeOpengrepRulesListResponse(response.data);
}

export async function getOpengrepRules(
    params?: OpengrepRulesQueryParams,
): Promise<OpengrepRule[]> {
    const response = await getOpengrepRulesPage(params);
    return response.data;
}

export async function getAllOpengrepRules(params?: {
    language?: string;
    source?: "internal" | "patch";
    is_active?: boolean;
    keyword?: string;
    confidence?: string;
    severity?: string;
    skip?: number;
}): Promise<OpengrepRule[]> {
    return getOpengrepRules({
        ...params,
        limit: ALL_OPENGREP_RULES_LIMIT,
    });
}

export async function getOpengrepRuleStats(): Promise<OpengrepRuleStatsResponse> {
    const response = await apiClient.get(`/static-tasks/rules/stats`);
    return response.data;
}

/**
 * Get opengrep rule detail
 */
export async function getOpengrepRule(
    ruleId: string,
): Promise<OpengrepRuleDetail> {
    const response = await apiClient.get(`/static-tasks/rules/${ruleId}`);
    return response.data;
}

/**
 * Toggle opengrep rule activation status
 */
export async function toggleOpengrepRule(
    ruleId: string,
): Promise<{ message: string; rule_id: string; is_active: boolean }> {
    const response = await apiClient.put(`/static-tasks/rules/${ruleId}`);
    return response.data;
}

/**
 * Delete opengrep rule
 */
export async function deleteOpengrepRule(
    ruleId: string,
): Promise<{ message: string; rule_id: string }> {
    const response = await apiClient.delete(`/static-tasks/rules/${ruleId}`);
    return response.data;
}

/**
 * Generate opengrep rule from patch
 */
export async function generateOpengrepRule(params: {
    repo_owner: string;
    repo_name: string;
    commit_hash: string;
    commit_content: string;
}): Promise<any> {
    const response = await apiClient.post(`/static-tasks/rules/create`, params);
    return response.data;
}

export async function createOpengrepGenericRule(params: {
    rule_yaml: string;
}): Promise<any> {
    const response = await apiClient.post(
        `/static-tasks/rules/create-generic`,
        params,
    );
    return response.data;
}

/**
 * Upload single rule via JSON
 */
export async function uploadOpengrepRuleJSON(params: {
    id?: string;
    name: string;
    pattern_yaml: string;
    language: string;
    severity?: string;
    confidence?: string;
    description?: string;
    cwe?: string[];
    source?: string;
    patch?: string;
    correct?: boolean;
    is_active?: boolean;
}): Promise<any> {
    const response = await apiClient.post(
        `/static-tasks/rules/upload/json`,
        params,
    );
    return response.data;
}

/**
 * Upload compressed rules file
 */
export async function uploadOpengrepRulesCompressed(file: File): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await apiClient.post(
        `/static-tasks/rules/upload`,
        formData,
        {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        },
    );
    return response.data;
}

/**
 * Upload rules from directory
 */
export async function uploadOpengrepRulesDirectory(
    files: File[],
): Promise<any> {
    const formData = new FormData();
    files.forEach((file) => {
        formData.append("files", file);
    });
    const response = await apiClient.post(
        `/static-tasks/rules/upload/directory`,
        formData,
        {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        },
    );
    return response.data;
}

/**
 * Patch 上传响应接口
 */
export interface PatchUploadResponse {
    total_files: number;
    success_count: number;
    failed_count: number;
    skipped_count: number;
    details: Array<{
        filename: string;
        status: "success" | "failed" | "error" | "skipped";
        attempts?: number;
        message: string;
    }>;
}

/**
 * Patch 规则创建响应接口（新流程）
 */
export interface PatchRuleCreationResponse {
    rule_ids: string[];
    total_files: number;
    message: string;
}

/**
 * Upload patch archive (zip) to generate rules
 */
export async function uploadPatchArchive(file: File): Promise<PatchRuleCreationResponse> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await apiClient.post(
        `/static-tasks/rules/upload/patch-archive`,
        formData,
        {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        },
    );
    return response.data;
}

/**
 * Upload patch directory to generate rules
 */
export async function uploadPatchDirectory(files: File[]): Promise<PatchRuleCreationResponse> {
    const formData = new FormData();
    files.forEach((file) => {
        formData.append("files", file);
    });
    const response = await apiClient.post(
        `/static-tasks/rules/upload/patch-directory`,
        formData,
        {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        },
    );
    return response.data;
}

/**
 * Get all rules that are currently being generated (patch source, correct=false)
 */
export async function getGeneratingRules(): Promise<OpengrepRule[]> {
    const response = await apiClient.get(`/static-tasks/rules/generating/status`);
    return response.data;
}

export interface OpengrepRuleUpdateRequest {
    name?: string;
    pattern_yaml?: string;
    language?: string;
    severity?: "ERROR" | "WARNING" | "INFO";
    is_active?: boolean;
}

export async function updateOpengrepRule(
    ruleId: string,
    params: OpengrepRuleUpdateRequest,
): Promise<{ message: string; rule: OpengrepRuleDetail }> {
    const response = await apiClient.patch(`/static-tasks/rules/${ruleId}`, params);
    return response.data;
}

export type StaticScanEngine = "opengrep" | "codeql";

export interface OpengrepScanTask {
    id: string;
    engine?: StaticScanEngine;
    project_id: string;
    project_name?: string | null;
    name: string;
    status: string;
    target_path: string;
    total_findings: number;
    critical_count?: number;
    high_count?: number;
    medium_count?: number;
    low_count?: number;
    error_count: number;
    warning_count: number;
    high_confidence_count?: number;
    scan_duration_ms: number;
    files_scanned: number;
    lines_scanned: number;
    created_at: string;
    updated_at?: string | null;
}

export interface OpengrepScanProgressLog {
    timestamp: string;
    stage: string;
    message: string;
    progress: number;
    level: string;
}

export interface CodeqlExplorationProgressEvent {
    timestamp: string;
    event_type: string;
    stage: string;
    progress: number;
    round?: number | null;
    redaction?: {
        applied?: boolean;
        patterns?: string[];
    } | Record<string, unknown>;
    payload?: Record<string, unknown>;
}

export interface OpengrepScanProgress {
    task_id: string;
    engine?: StaticScanEngine;
    status: string;
    progress: number;
    current_stage?: string | null;
    message?: string | null;
    started_at?: string | null;
    updated_at?: string | null;
    logs: OpengrepScanProgressLog[];
    events?: CodeqlExplorationProgressEvent[];
    llm_model?: string | null;
}

export interface OpengrepFinding {
    id: string;
    scan_task_id: string;
    engine?: StaticScanEngine;
    rule: Record<string, any>;
    rule_name?: string | null;
    cwe?: string[] | null;
    description?: string | null;
    file_path: string;
    start_line?: number | null;
    resolved_file_path?: string | null;
    resolved_line_start?: number | null;
    code_snippet?: string | null;
    severity: string;
    status: string;
    confidence?: string | null;
}

export interface OpengrepFindingContextLine {
    line_number: number;
    content: string;
    is_hit: boolean;
}

export interface OpengrepFindingContext {
    task_id: string;
    finding_id: string;
    file_path: string;
    start_line: number;
    end_line: number;
    before: number;
    after: number;
    total_lines: number;
    lines: OpengrepFindingContextLine[];
}

export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";

function normalizeConfidence(
    confidence?: string | null,
): ConfidenceLevel | null {
    const normalized = String(confidence || "").trim().toUpperCase();
    if (normalized === "HIGH") return "HIGH";
    if (normalized === "LOW") return "LOW";
    if (normalized === "MEDIUM") return "MEDIUM";
    return null;
}

export async function createOpengrepScanTask(params: {
    project_id: string;
    name?: string;
    rule_ids: string[];
    target_path?: string;
}): Promise<OpengrepScanTask> {
    const response = await apiClient.post(`/static-tasks/tasks`, params);
    return response.data;
}

export async function createCodeqlScanTask(params: {
    project_id: string;
    name?: string;
    target_path?: string;
    languages?: string[];
    build_mode?: "none" | "autobuild" | "manual";
    allow_network?: boolean;
}): Promise<OpengrepScanTask> {
    const response = await apiClient.post(`/static-tasks/codeql/tasks`, params);
    return response.data;
}

export async function getOpengrepScanTask(
    taskId: string,
): Promise<OpengrepScanTask> {
    const response = await apiClient.get(`/static-tasks/tasks/${taskId}`);
    return response.data;
}

export async function getCodeqlScanTask(
    taskId: string,
): Promise<OpengrepScanTask> {
    const response = await apiClient.get(`/static-tasks/codeql/tasks/${taskId}`);
    return response.data;
}

export async function interruptOpengrepScanTask(
    taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
    const response = await apiClient.post(`/static-tasks/tasks/${taskId}/interrupt`);
    return response.data;
}

export async function interruptCodeqlScanTask(
    taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/codeql/tasks/${taskId}/interrupt`,
    );
    return response.data;
}

export async function deleteStaticScanTask(
    engine: StaticScanEngine,
    taskId: string,
): Promise<{ message: string; task_id: string }> {
    const basePath =
        engine === "codeql" ? "/static-tasks/codeql/tasks" : "/static-tasks/tasks";
    const response = await apiClient.delete(`${basePath}/${taskId}`);
    return response.data;
}

export async function resetCodeqlProjectBuildPlan(
    projectId: string,
): Promise<{ message: string; project_id: string; language: string; reset_count: number }> {
    const response = await apiClient.post(
        `/static-tasks/codeql/projects/${projectId}/build-plan/reset`,
    );
    return response.data;
}

export async function getOpengrepScanProgress(
    taskId: string,
    includeLogs: boolean = false,
): Promise<OpengrepScanProgress> {
    const response = await apiClient.get(`/static-tasks/tasks/${taskId}/progress`, {
        params: { include_logs: includeLogs },
    });
    return response.data;
}

export async function getCodeqlScanProgress(
    taskId: string,
    includeLogs: boolean = false,
): Promise<OpengrepScanProgress> {
    const response = await apiClient.get(
        `/static-tasks/codeql/tasks/${taskId}/progress`,
        {
            params: { include_logs: includeLogs },
        },
    );
    return response.data;
}

function staticFindingsQuery(params: {
    severity?: string;
    confidence?: string;
    status?: string;
    skip?: number;
    limit?: number;
}): string {
    const searchParams = new URLSearchParams();
    if (params.severity) searchParams.set("severity", params.severity);
    if (params.confidence) searchParams.set("confidence", params.confidence);
    if (params.status) searchParams.set("status", params.status);
    if (params.skip !== undefined)
        searchParams.set("skip", String(params.skip));
    if (params.limit !== undefined)
        searchParams.set("limit", String(params.limit));
    return searchParams.toString();
}

export async function getOpengrepScanFindings(params: {
    taskId: string;
    severity?: string;
    confidence?: string;
    status?: string;
    skip?: number;
    limit?: number;
}): Promise<OpengrepFinding[]> {
    const query = staticFindingsQuery(params);
    const response = await apiClient.get(
        `/static-tasks/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
    );
    const findings = Array.isArray(response.data) ? response.data : [];
    return findings.map((item) => ({
        ...item,
        confidence: normalizeConfidence(item?.confidence),
    }));
}

export async function getCodeqlScanFindings(params: {
    taskId: string;
    severity?: string;
    confidence?: string;
    status?: string;
    skip?: number;
    limit?: number;
}): Promise<OpengrepFinding[]> {
    const query = staticFindingsQuery(params);
    const response = await apiClient.get(
        `/static-tasks/codeql/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
    );
    const findings = Array.isArray(response.data) ? response.data : [];
    return findings.map((item) => ({
        ...item,
        confidence: normalizeConfidence(item?.confidence),
    }));
}

export async function getOpengrepScanFinding(params: {
    taskId: string;
    findingId: string;
}): Promise<OpengrepFinding> {
    const response = await apiClient.get(
        `/static-tasks/tasks/${params.taskId}/findings/${params.findingId}`,
    );
    return {
        ...response.data,
        confidence: normalizeConfidence(response.data?.confidence),
    };
}

export async function getOpengrepFindingContext(params: {
    taskId: string;
    findingId: string;
    before?: number;
    after?: number;
}): Promise<OpengrepFindingContext> {
    const response = await apiClient.get(
        `/static-tasks/tasks/${params.taskId}/findings/${params.findingId}/context`,
        {
            params: {
                before: params.before ?? 5,
                after: params.after ?? 5,
            },
        },
    );
    return response.data;
}

export async function getCodeqlScanFinding(params: {
    taskId: string;
    findingId: string;
}): Promise<OpengrepFinding> {
    const response = await apiClient.get(
        `/static-tasks/codeql/tasks/${params.taskId}/findings/${params.findingId}`,
    );
    return {
        ...response.data,
        confidence: normalizeConfidence(response.data?.confidence),
    };
}

export async function getCodeqlFindingContext(params: {
    taskId: string;
    findingId: string;
    before?: number;
    after?: number;
}): Promise<OpengrepFindingContext> {
    const response = await apiClient.get(
        `/static-tasks/codeql/tasks/${params.taskId}/findings/${params.findingId}/context`,
        {
            params: {
                before: params.before ?? 5,
                after: params.after ?? 5,
            },
        },
    );
    return response.data;
}

export async function getStaticScanTasks(
    engine: StaticScanEngine,
    params?: {
        projectId?: string;
        skip?: number;
        limit?: number;
    },
): Promise<OpengrepScanTask[]> {
    const searchParams = new URLSearchParams();
    if (params?.projectId) searchParams.set("project_id", params.projectId);
    if (params?.skip !== undefined)
        searchParams.set("skip", String(params.skip));
    if (params?.limit !== undefined)
        searchParams.set("limit", String(params.limit));
    const query = searchParams.toString();
    const basePath =
        engine === "codeql" ? "/static-tasks/codeql/tasks" : "/static-tasks/tasks";
    const response = await apiClient.get(
        `${basePath}${query ? `?${query}` : ""}`,
    );
    return response.data;
}

export async function getOpengrepScanTasks(params?: {
    projectId?: string;
    skip?: number;
    limit?: number;
}): Promise<OpengrepScanTask[]> {
    return getStaticScanTasks("opengrep", params);
}

export async function getCodeqlScanTasks(params?: {
    projectId?: string;
    skip?: number;
    limit?: number;
}): Promise<OpengrepScanTask[]> {
    return getStaticScanTasks("codeql", params);
}

export async function updateOpengrepFindingStatus(params: {
    findingId: string;
    status: "open" | "verified" | "false_positive";
}): Promise<{ message: string; finding_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/findings/${params.findingId}/status`,
        undefined,
        { params: { status: params.status } },
    );
    return response.data;
}

export async function updateCodeqlFindingStatus(params: {
    findingId: string;
    status: "open" | "verified" | "false_positive";
}): Promise<{ message: string; finding_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/codeql/findings/${params.findingId}/status`,
        undefined,
        { params: { status: params.status } },
    );
    return response.data;
}

/**
 * Batch update opengrep rules
 */
export async function batchUpdateOpengrepRules(params: {
    rule_ids?: string[];
    keyword?: string;
    language?: string;
    source?: "internal" | "patch";
    severity?: string;
    confidence?: string;
    current_is_active?: boolean;
    is_active: boolean;
}): Promise<{ message: string; updated_count: number; is_active: boolean }> {
    const response = await apiClient.post(`/static-tasks/rules/select`, params);
    return response.data;
}

/**
 * Get supported languages
 */
export const SUPPORTED_LANGUAGES = [
    { value: "python", label: "Python" },
    { value: "javascript", label: "JavaScript" },
    { value: "typescript", label: "TypeScript" },
    { value: "java", label: "Java" },
    { value: "go", label: "Go" },
    { value: "rust", label: "Rust" },
    { value: "cpp", label: "C++" },
    { value: "csharp", label: "C#" },
    { value: "php", label: "PHP" },
    { value: "ruby", label: "Ruby" },
    { value: "swift", label: "Swift" },
    { value: "kotlin", label: "Kotlin" },
];

export interface AiAnalysisStatusResponse {
    status: "not_started" | "analyzing" | "completed" | "failed";
    current_step: number | null;
    step_name: string | null;
    model: string | null;
    started_at: string | null;
    completed_at: string | null;
    result?: {
        rules: Array<{
            ruleName: string;
            severity: string;
            hitCount: number;
            problem: string;
            codeExamples?: Array<{ file: string; code: string }>;
            suggestion: string;
            priority: string;
        }>;
    };
    error?: string | null;
}

export async function triggerAiAnalysis(
    taskId: string,
): Promise<{ message: string; task_id: string }> {
    const response = await apiClient.post(`/static-tasks/tasks/${taskId}/ai-analysis/start`);
    return response.data;
}

export async function getAiAnalysisStatus(
    taskId: string,
): Promise<AiAnalysisStatusResponse> {
    const response = await apiClient.get(`/static-tasks/tasks/${taskId}/ai-analysis/status`);
    return response.data;
}

export const RULE_SOURCES = [
    { value: "internal", label: "内置规则" },
    { value: "patch", label: "补丁生成" },
];

export const SEVERITIES = [
    { value: "ERROR", label: "错误" },
    { value: "WARNING", label: "警告" },
    { value: "INFO", label: "信息" },
];

export const ACTIVE_STATUS = [
    { value: "true", label: "已启用" },
    { value: "false", label: "已禁用" },
];
