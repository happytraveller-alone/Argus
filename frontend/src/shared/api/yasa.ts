import { apiClient } from "@/shared/api/serverClient";

export interface YasaScanTask {
  id: string;
  project_id: string;
  name: string;
  status: string;
  target_path: string;
  language: string;
  checker_pack_ids?: string | null;
  checker_ids?: string | null;
  rule_config_file?: string | null;
  total_findings: number;
  scan_duration_ms: number;
  files_scanned: number;
  diagnostics_summary?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface YasaFinding {
  id: string;
  scan_task_id: string;
  rule_id?: string | null;
  rule_name?: string | null;
  level: string;
  message: string;
  file_path: string;
  start_line?: number | null;
  end_line?: number | null;
  status: string;
}

export interface YasaRule {
  checker_id: string;
  checker_path?: string | null;
  description?: string | null;
  checker_packs: string[];
  languages: string[];
  demo_rule_config_path?: string | null;
  source: string;
}

export async function createYasaScanTask(params: {
  project_id: string;
  name?: string;
  target_path?: string;
  language?: string;
  checker_pack_ids?: string[];
  checker_ids?: string[];
  rule_config_file?: string;
}): Promise<YasaScanTask> {
  const response = await apiClient.post("/static-tasks/yasa/scan", params);
  return response.data;
}

export async function getYasaScanTask(taskId: string): Promise<YasaScanTask> {
  const response = await apiClient.get(`/static-tasks/yasa/tasks/${taskId}`);
  return response.data;
}

export async function interruptYasaScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
  const response = await apiClient.post(`/static-tasks/yasa/tasks/${taskId}/interrupt`);
  return response.data;
}

export async function deleteYasaScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string }> {
  const response = await apiClient.delete(`/static-tasks/yasa/tasks/${taskId}`);
  return response.data;
}

export async function getYasaScanTasks(params?: {
  projectId?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<YasaScanTask[]> {
  const searchParams = new URLSearchParams();
  if (params?.projectId) searchParams.set("project_id", params.projectId);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(`/static-tasks/yasa/tasks${query ? `?${query}` : ""}`);
  return response.data;
}

export async function getYasaFindings(params: {
  taskId: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<YasaFinding[]> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/yasa/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getYasaFinding(params: {
  taskId: string;
  findingId: string;
}): Promise<YasaFinding> {
  const response = await apiClient.get(
    `/static-tasks/yasa/tasks/${params.taskId}/findings/${params.findingId}`,
  );
  return response.data;
}

export async function updateYasaFindingStatus(params: {
  findingId: string;
  status: "open" | "verified" | "false_positive";
}): Promise<{ message: string; finding_id: string; status: string }> {
  const response = await apiClient.post(
    `/static-tasks/yasa/findings/${params.findingId}/status`,
    undefined,
    { params: { status: params.status } },
  );
  return response.data;
}

export async function getYasaRules(params?: {
  checkerPackId?: string;
  language?: string;
  keyword?: string;
  skip?: number;
  limit?: number;
}): Promise<YasaRule[]> {
  const searchParams = new URLSearchParams();
  if (params?.checkerPackId) searchParams.set("checker_pack_id", params.checkerPackId);
  if (params?.language) searchParams.set("language", params.language);
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(`/static-tasks/yasa/rules${query ? `?${query}` : ""}`);
  return response.data;
}
