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
    status: "open" | "verified" | "false_positive" | "fixed";
}): Promise<{ message: string; finding_id: string; status: string }> {
    const response = await apiClient.post(
        `/static-tasks/gitleaks/findings/${params.findingId}/status`,
        undefined,
        { params: { status: params.status } },
    );
    return response.data;
}
