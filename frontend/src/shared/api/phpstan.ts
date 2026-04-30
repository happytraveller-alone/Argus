
import { apiClient } from "@/shared/api/serverClient";

export interface PhpstanScanTask {
  id: string;
  project_id: string;
  name: string;
  status: string;
  target_path: string;
  level: number;
  total_findings: number;
  scan_duration_ms: number;
  files_scanned: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface PhpstanFinding {
  id: string;
  scan_task_id: string;
  file_path: string;
  line?: number | null;
  resolved_file_path?: string | null;
  resolved_line_start?: number | null;
  message: string;
  identifier?: string | null;
  tip?: string | null;
  status: string;
}

export interface PhpstanRule {
  id: string;
  package: string;
  repo: string;
  rule_class: string;
  name: string;
  description_summary: string;
  source_file: string;
  source: string;
  source_content?: string | null;
  is_active: boolean;
  is_deleted: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PhpstanRuleUpdateRequest {
  ruleId: string;
  package?: string;
  repo?: string;
  name?: string;
  description_summary?: string;
  source_file?: string;
  source?: string;
}

export async function createPhpstanScanTask(params: {
  project_id: string;
  name?: string;
  target_path?: string;
  level?: number;
}): Promise<PhpstanScanTask> {
  const response = await apiClient.post("/static-tasks/phpstan/scan", params);
  return response.data;
}

export async function getPhpstanScanTask(taskId: string): Promise<PhpstanScanTask> {
  const response = await apiClient.get(`/static-tasks/phpstan/tasks/${taskId}`);
  return response.data;
}

export async function interruptPhpstanScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
  const response = await apiClient.post(`/static-tasks/phpstan/tasks/${taskId}/interrupt`);
  return response.data;
}

export async function deletePhpstanScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string }> {
  const response = await apiClient.delete(`/static-tasks/phpstan/tasks/${taskId}`);
  return response.data;
}

export async function getPhpstanScanTasks(params?: {
  projectId?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<PhpstanScanTask[]> {
  const searchParams = new URLSearchParams();
  if (params?.projectId) searchParams.set("project_id", params.projectId);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/phpstan/tasks${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getPhpstanFindings(params: {
  taskId: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<PhpstanFinding[]> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/phpstan/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getPhpstanFinding(params: {
  taskId: string;
  findingId: string;
}): Promise<PhpstanFinding> {
  const response = await apiClient.get(
    `/static-tasks/phpstan/tasks/${params.taskId}/findings/${params.findingId}`,
  );
  return response.data;
}

export async function updatePhpstanFindingStatus(params: {
  findingId: string;
  status: "open" | "verified" | "false_positive";
}): Promise<{ message: string; finding_id: string; status: string }> {
  const response = await apiClient.post(
    `/static-tasks/phpstan/findings/${params.findingId}/status`,
    undefined,
    { params: { status: params.status } },
  );
  return response.data;
}

export async function getPhpstanRules(params?: {
  is_active?: boolean;
  source?: string;
  keyword?: string;
  deleted?: "false" | "true" | "all";
  skip?: number;
  limit?: number;
}): Promise<PhpstanRule[]> {
  const searchParams = new URLSearchParams();
  if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
  if (params?.source) searchParams.set("source", params.source);
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.deleted) searchParams.set("deleted", params.deleted);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  searchParams.set("limit", String(params?.limit ?? 1000));
  const query = searchParams.toString();
  const response = await apiClient.get(`/static-tasks/phpstan/rules${query ? `?${query}` : ""}`);
  return response.data;
}

export async function getPhpstanRule(ruleId: string): Promise<PhpstanRule> {
  const response = await apiClient.get(`/static-tasks/phpstan/rules/${encodeURIComponent(ruleId)}`);
  return response.data;
}

export async function updatePhpstanRule(
  params: PhpstanRuleUpdateRequest,
): Promise<{ message: string; rule: PhpstanRule }> {
  const response = await apiClient.patch(
    `/static-tasks/phpstan/rules/${encodeURIComponent(params.ruleId)}`,
    {
      package: params.package,
      repo: params.repo,
      name: params.name,
      description_summary: params.description_summary,
      source_file: params.source_file,
      source: params.source,
    },
  );
  return response.data;
}

export async function updatePhpstanRuleEnabled(params: {
  ruleId: string;
  is_active: boolean;
}): Promise<{ message: string; rule_id: string; is_active: boolean }> {
  const response = await apiClient.post(
    `/static-tasks/phpstan/rules/${encodeURIComponent(params.ruleId)}/enabled`,
    { is_active: params.is_active },
  );
  return response.data;
}

export async function batchUpdatePhpstanRulesEnabled(params: {
  rule_ids?: string[];
  source?: string;
  keyword?: string;
  current_is_active?: boolean;
  is_active: boolean;
}): Promise<{ message: string; updated_count: number; is_active: boolean }> {
  const response = await apiClient.post(`/static-tasks/phpstan/rules/batch/enabled`, params);
  return response.data;
}

export async function deletePhpstanRule(ruleId: string): Promise<{
  message: string;
  rule_id: string;
  is_deleted: boolean;
}> {
  const response = await apiClient.post(
    `/static-tasks/phpstan/rules/${encodeURIComponent(ruleId)}/delete`,
  );
  return response.data;
}

export async function restorePhpstanRule(ruleId: string): Promise<{
  message: string;
  rule_id: string;
  is_deleted: boolean;
}> {
  const response = await apiClient.post(
    `/static-tasks/phpstan/rules/${encodeURIComponent(ruleId)}/restore`,
  );
  return response.data;
}

export async function batchDeletePhpstanRules(params: {
  rule_ids?: string[];
  source?: string;
  keyword?: string;
  current_is_deleted?: boolean;
}): Promise<{ message: string; updated_count: number; is_deleted: boolean }> {
  const response = await apiClient.post(`/static-tasks/phpstan/rules/batch/delete`, params);
  return response.data;
}

export async function batchRestorePhpstanRules(params: {
  rule_ids?: string[];
  source?: string;
  keyword?: string;
  current_is_deleted?: boolean;
}): Promise<{ message: string; updated_count: number; is_deleted: boolean }> {
  const response = await apiClient.post(`/static-tasks/phpstan/rules/batch/restore`, params);
  return response.data;
}
