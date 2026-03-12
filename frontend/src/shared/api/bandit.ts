import { apiClient } from "@/shared/api/serverClient";

export interface BanditScanTask {
  id: string;
  project_id: string;
  name: string;
  status: string;
  target_path: string;
  total_findings: number;
  scan_duration_ms: number;
  files_scanned: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface BanditFinding {
  id: string;
  scan_task_id: string;
  test_id: string;
  test_name?: string | null;
  issue_text?: string | null;
  issue_severity: string;
  issue_confidence: string;
  file_path: string;
  line_number?: number | null;
  code?: string | null;
  more_info?: string | null;
  status: string;
  created_at?: string;
  updated_at?: string | null;
}

export async function createBanditScanTask(params: {
  project_id: string;
  name?: string;
  target_path?: string;
}): Promise<BanditScanTask> {
  const response = await apiClient.post("/static-tasks/bandit/scan", params);
  return response.data;
}

export async function getBanditScanTask(taskId: string): Promise<BanditScanTask> {
  const response = await apiClient.get(`/static-tasks/bandit/tasks/${taskId}`);
  return response.data;
}

export async function interruptBanditScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
  const response = await apiClient.post(`/static-tasks/bandit/tasks/${taskId}/interrupt`);
  return response.data;
}

export async function getBanditScanTasks(params?: {
  projectId?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<BanditScanTask[]> {
  const searchParams = new URLSearchParams();
  if (params?.projectId) searchParams.set("project_id", params.projectId);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/bandit/tasks${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getBanditFindings(params: {
  taskId: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<BanditFinding[]> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/bandit/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getBanditFinding(params: {
  taskId: string;
  findingId: string;
}): Promise<BanditFinding> {
  const response = await apiClient.get(
    `/static-tasks/bandit/tasks/${params.taskId}/findings/${params.findingId}`,
  );
  return response.data;
}

export async function updateBanditFindingStatus(params: {
  findingId: string;
  status: "open" | "verified" | "false_positive" | "fixed";
}): Promise<{ message: string; finding_id: string; status: string }> {
  const response = await apiClient.post(
    `/static-tasks/bandit/findings/${params.findingId}/status`,
    undefined,
    { params: { status: params.status } },
  );
  return response.data;
}
