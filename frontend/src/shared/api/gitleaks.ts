/**
 * Gitleaks API Client
 */

import { apiClient } from "@/shared/api/serverClient";

export interface GitleaksScanTask {
    id: string;
    project_id: string;
    name: string;
    status: string;
    target_path: string;
    no_git: string;
    total_findings: number;
    scan_duration_ms: number;
    files_scanned: number;
    error_message?: string | null;
    created_at: string;
    updated_at?: string | null;
}

export interface GitleaksFinding {
    id: string;
    scan_task_id: string;
    rule_id: string;
    description?: string | null;
    file_path: string;
    start_line?: number | null;
    end_line?: number | null;
    secret?: string | null;
    match?: string | null;
    commit?: string | null;
    author?: string | null;
    email?: string | null;
    date?: string | null;
    fingerprint?: string | null;
    status: string;
}

export interface GitleaksRule {
    id: string;
    name: string;
    description?: string | null;
    rule_id: string;
    secret_group: number;
    regex: string;
    keywords: string[];
    path?: string | null;
    tags: string[];
    entropy?: number | null;
    is_active: boolean;
    source: string;
    created_at: string;
    updated_at?: string | null;
}

export async function createGitleaksScanTask(params: {
    project_id: string;
    name?: string;
    target_path?: string;
    no_git?: boolean;
}): Promise<GitleaksScanTask> {
    const response = await apiClient.post(`/static-tasks/gitleaks/scan`, params);
    return response.data;
}

export async function getGitleaksScanTask(
    taskId: string,
): Promise<GitleaksScanTask> {
    const response = await apiClient.get(`/static-tasks/gitleaks/tasks/${taskId}`);
    return response.data;
}

export async function interruptGitleaksScanTask(
    taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/gitleaks/tasks/${taskId}/interrupt`,
    );
    return response.data;
}

export async function getGitleaksScanTasks(params?: {
    projectId?: string;
    skip?: number;
    limit?: number;
}): Promise<GitleaksScanTask[]> {
    const searchParams = new URLSearchParams();
    if (params?.projectId) searchParams.set("project_id", params.projectId);
    if (params?.skip !== undefined)
        searchParams.set("skip", String(params.skip));
    if (params?.limit !== undefined)
        searchParams.set("limit", String(params.limit));
    const query = searchParams.toString();
    const response = await apiClient.get(
        `/static-tasks/gitleaks/tasks${query ? `?${query}` : ""}`,
    );
    return response.data;
}

export async function getGitleaksFindings(params: {
    taskId: string;
    status?: string;
    skip?: number;
    limit?: number;
}): Promise<GitleaksFinding[]> {
    const searchParams = new URLSearchParams();
    if (params.status) searchParams.set("status", params.status);
    if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
    if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
    const query = searchParams.toString();
    const response = await apiClient.get(
        `/static-tasks/gitleaks/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
    );
    return response.data;
}

export async function getGitleaksFinding(params: {
    taskId: string;
    findingId: string;
}): Promise<GitleaksFinding> {
    const response = await apiClient.get(
        `/static-tasks/gitleaks/tasks/${params.taskId}/findings/${params.findingId}`,
    );
    return response.data;
}

export async function updateGitleaksFindingStatus(params: {
    findingId: string;
    status: "open" | "verified" | "false_positive";
}): Promise<{ message: string; finding_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/gitleaks/findings/${params.findingId}/status`,
        undefined,
        { params: { status: params.status } },
    );
    return response.data;
}

export async function getGitleaksRules(params?: {
    is_active?: boolean;
    source?: string;
    keyword?: string;
    tag?: string;
    skip?: number;
    limit?: number;
}): Promise<GitleaksRule[]> {
    const searchParams = new URLSearchParams();
    if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    if (params?.source) searchParams.set("source", params.source);
    if (params?.keyword) searchParams.set("keyword", params.keyword);
    if (params?.tag) searchParams.set("tag", params.tag);
    if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
    searchParams.set("limit", String(params?.limit ?? 1000));
    const query = searchParams.toString();
    const response = await apiClient.get(`/static-tasks/gitleaks/rules${query ? `?${query}` : ""}`);
    return response.data;
}

export async function getGitleaksRule(ruleId: string): Promise<GitleaksRule> {
    const response = await apiClient.get(`/static-tasks/gitleaks/rules/${ruleId}`);
    return response.data;
}

export async function createGitleaksRule(params: {
    name: string;
    description?: string;
    rule_id: string;
    secret_group?: number;
    regex: string;
    keywords?: string[];
    path?: string;
    tags?: string[];
    entropy?: number;
    is_active?: boolean;
    source?: string;
}): Promise<GitleaksRule> {
    const response = await apiClient.post(`/static-tasks/gitleaks/rules`, params);
    return response.data;
}

export async function updateGitleaksRule(
    ruleId: string,
    params: {
        name?: string;
        description?: string;
        rule_id?: string;
        secret_group?: number;
        regex?: string;
        keywords?: string[];
        path?: string;
        tags?: string[];
        entropy?: number;
        is_active?: boolean;
        source?: string;
    },
): Promise<GitleaksRule> {
    const response = await apiClient.patch(`/static-tasks/gitleaks/rules/${ruleId}`, params);
    return response.data;
}

export async function deleteGitleaksRule(
    ruleId: string,
): Promise<{ message: string; rule_id: string }> {
    const response = await apiClient.delete(`/static-tasks/gitleaks/rules/${ruleId}`);
    return response.data;
}

export async function batchUpdateGitleaksRules(params: {
    rule_ids?: string[];
    source?: string;
    keyword?: string;
    current_is_active?: boolean;
    is_active: boolean;
}): Promise<{ message: string; updated_count: number; is_active: boolean }> {
    const response = await apiClient.post(`/static-tasks/gitleaks/rules/select`, params);
    return response.data;
}

export async function toggleGitleaksRule(
    rule: GitleaksRule,
): Promise<GitleaksRule> {
    return updateGitleaksRule(rule.id, { is_active: !rule.is_active });
}
