import { apiClient } from "@/shared/api/serverClient";

export interface PmdScanTask {
  id: string;
  project_id: string;
  name: string;
  status: string;
  target_path: string;
  ruleset: string;
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

export interface PmdFinding {
  id: string;
  scan_task_id: string;
  file_path: string;
  begin_line?: number | null;
  end_line?: number | null;
  resolved_file_path?: string | null;
  resolved_line_start?: number | null;
  rule?: string | null;
  ruleset?: string | null;
  priority?: number | null;
  message: string;
  status: string;
}

export interface PmdPreset {
  id: string;
  name: string;
  alias: string;
  description: string;
  categories: string[];
}

export interface PmdRuleDetail {
  name?: string | null;
  ref?: string | null;
  language?: string | null;
  message?: string | null;
  class_name?: string | null;
  priority?: number | null;
  since?: string | null;
  external_info_url?: string | null;
  description?: string | null;
}

export interface PmdRulesetSummary {
  id: string;
  name: string;
  description?: string | null;
  filename: string;
  is_active: boolean;
  source: string;
  ruleset_name: string;
  rule_count: number;
  languages: string[];
  priorities: number[];
  external_info_urls: string[];
  rules: PmdRuleDetail[];
  raw_xml: string;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type PmdRuleConfig = PmdRulesetSummary;

export async function createPmdScanTask(params: {
  project_id: string;
  name?: string;
  target_path?: string;
  ruleset?: string;
}): Promise<PmdScanTask> {
  const response = await apiClient.post("/static-tasks/pmd/scan", params);
  return response.data;
}

export async function getPmdScanTasks(params?: {
  project_id?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<PmdScanTask[]> {
  const searchParams = new URLSearchParams();
  if (params?.project_id) searchParams.set("project_id", params.project_id);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(`/static-tasks/pmd/tasks${query ? `?${query}` : ""}`);
  return response.data;
}

export async function getPmdScanTask(taskId: string): Promise<PmdScanTask> {
  const response = await apiClient.get(`/static-tasks/pmd/tasks/${taskId}`);
  return response.data;
}

export async function interruptPmdScanTask(
  taskId: string,
): Promise<{ message: string; task_id: string; status: string }> {
  const response = await apiClient.post(`/static-tasks/pmd/tasks/${taskId}/interrupt`);
  return response.data;
}

export async function getPmdFindings(params: {
  taskId: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<PmdFinding[]> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set("status", params.status);
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/pmd/tasks/${params.taskId}/findings${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getPmdFinding(params: {
  taskId: string;
  findingId: string;
}): Promise<PmdFinding> {
  const response = await apiClient.get(
    `/static-tasks/pmd/tasks/${params.taskId}/findings/${params.findingId}`,
  );
  return response.data;
}

export async function updatePmdFindingStatus(
  findingId: string,
  status: "open" | "verified" | "false_positive",
): Promise<{ message: string; finding_id: string; status: string }> {
  const response = await apiClient.post(
    `/static-tasks/pmd/findings/${findingId}/status?status=${encodeURIComponent(status)}`,
  );
  return response.data;
}

export async function getPmdPresets(): Promise<PmdPreset[]> {
  const response = await apiClient.get("/static-tasks/pmd/presets");
  return response.data;
}

export async function getPmdBuiltinRulesets(params?: {
  keyword?: string;
  language?: string;
  limit?: number;
}): Promise<PmdRulesetSummary[]> {
  const searchParams = new URLSearchParams();
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.language) searchParams.set("language", params.language);
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/pmd/builtin-rulesets${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getPmdBuiltinRuleset(
  rulesetId: string,
): Promise<PmdRulesetSummary> {
  const response = await apiClient.get(
    `/static-tasks/pmd/builtin-rulesets/${encodeURIComponent(rulesetId)}`,
  );
  return response.data;
}

export async function importPmdRuleConfig(params: {
  name: string;
  description?: string;
  xmlFile: File;
}): Promise<PmdRuleConfig> {
  const formData = new FormData();
  formData.append("name", params.name);
  if (params.description) formData.append("description", params.description);
  formData.append("xml_file", params.xmlFile);
  const response = await apiClient.post("/static-tasks/pmd/rule-configs/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function getPmdRuleConfigs(params?: {
  is_active?: boolean;
  keyword?: string;
  skip?: number;
  limit?: number;
}): Promise<PmdRuleConfig[]> {
  const searchParams = new URLSearchParams();
  if (params?.is_active !== undefined) {
    searchParams.set("is_active", String(params.is_active));
  }
  if (params?.keyword) searchParams.set("keyword", params.keyword);
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  const query = searchParams.toString();
  const response = await apiClient.get(
    `/static-tasks/pmd/rule-configs${query ? `?${query}` : ""}`,
  );
  return response.data;
}

export async function getPmdRuleConfig(ruleConfigId: string): Promise<PmdRuleConfig> {
  const response = await apiClient.get(
    `/static-tasks/pmd/rule-configs/${encodeURIComponent(ruleConfigId)}`,
  );
  return response.data;
}

export async function updatePmdRuleConfig(
  ruleConfigId: string,
  payload: {
    name?: string;
    description?: string;
    is_active?: boolean;
  },
): Promise<PmdRuleConfig> {
  const response = await apiClient.patch(
    `/static-tasks/pmd/rule-configs/${encodeURIComponent(ruleConfigId)}`,
    payload,
  );
  return response.data;
}

export async function deletePmdRuleConfig(
  ruleConfigId: string,
): Promise<{ message: string; id: string }> {
  const response = await apiClient.delete(
    `/static-tasks/pmd/rule-configs/${encodeURIComponent(ruleConfigId)}`,
  );
  return response.data;
}
