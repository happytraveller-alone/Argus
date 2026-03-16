import { apiClient } from "@/shared/api/serverClient";

export interface BanditScanTask {
  id: string;
  project_id: string;
  name: string;
  status: string;
  target_path: string;
  severity_level: string;
  confidence_level: string;
  total_findings: number;
  high_count: number;
  medium_count: number;
  low_count: number;
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
  code_snippet?: string | null;
  more_info?: string | null;
  status: string;
  created_at?: string;
}

export interface BanditRule {
  id: string;
  test_id: string;
  name: string;
  description: string;
  description_summary: string;
  checks: string[];
  source: string;
  bandit_version: string;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export async function createBanditScanTask(params: {
  project_id: string;
  name?: string;
  target_path?: string;
  severity_level?: string;
  confidence_level?: string;
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

export async function getBanditRules(params?: {
  is_active?: boolean;
  source?: string;
  keyword?: string;
  skip?: number;
  limit?: number;
}): Promise<BanditRule[]> {
  const searchParams = new URLSearchParams();
  if (params?.is_active !== undefined) {
    searchParams.set("is_active", String(params.is_active));
  }
  if (params?.source) searchParams.set("source", params.source);
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  searchParams.set("limit", String(params?.limit ?? 1000));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/bandit/rules${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getBanditRule(ruleId: string): Promise<BanditRule> {
  const response = await apiClient.get(`/static-tasks/bandit/rules/${ruleId}`);
  return response.data;
}

export async function updateBanditRuleEnabled(params: {
  ruleId: string;
  is_active: boolean;
}): Promise<{ message: string; rule_id: string; is_active: boolean }> {
  const response = await apiClient.post(
    `/static-tasks/bandit/rules/${params.ruleId}/enabled`,
    { is_active: params.is_active },
  );
  return response.data;
}

export async function batchUpdateBanditRulesEnabled(params: {
  rule_ids?: string[];
  source?: string;
  keyword?: string;
  current_is_active?: boolean;
  is_active: boolean;
}): Promise<{ message: string; updated_count: number; is_active: boolean }> {
  const response = await apiClient.post(`/static-tasks/bandit/rules/batch/enabled`, params);
  return response.data;
}
