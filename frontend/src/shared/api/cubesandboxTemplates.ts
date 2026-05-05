import { apiClient } from "@/shared/api/serverClient";
import { getApiBaseUrl } from "@/shared/api/apiBase";

export type CubesandboxTemplateStatus =
  | "absent"
  | "pending"
  | "building"
  | "ready"
  | "failed"
  | "invalidated";

export interface CubesandboxTemplateRecord {
  id?: string;
  kind?: string;
  status: CubesandboxTemplateStatus;
  templateId: string | null;
  artifactId: string | null;
  jobId: string | null;
  imageRef?: string;
  errorMessage: string | null;
  buildLogTail: string;
  createdAt?: string;
  updatedAt?: string;
  readyAt?: string | null;
  imageFingerprint?: string | null;
  consecutiveScanFailures?: number;
}

export async function getCodeqlCppTemplateStatus(): Promise<CubesandboxTemplateRecord> {
  const response = await apiClient.get<CubesandboxTemplateRecord>(
    "/cubesandbox/templates/codeql-cpp",
  );
  return response.data;
}

export async function provisionCodeqlCppTemplate(): Promise<CubesandboxTemplateRecord> {
  const response = await apiClient.post<CubesandboxTemplateRecord>(
    "/cubesandbox/templates/codeql-cpp/provision",
  );
  return response.data;
}

export async function invalidateCodeqlCppTemplate(): Promise<{ affected: number }> {
  const response = await apiClient.post<{ affected: number }>(
    "/cubesandbox/templates/codeql-cpp/invalidate",
  );
  return response.data;
}

export function getCodeqlCppTemplateStreamUrl(): string {
  return `${getApiBaseUrl()}/cubesandbox/templates/codeql-cpp/stream`;
}


export interface SandboxTemplateManagementOverview {
  templates: CubesandboxTemplateRecord[];
  failedCount: number;
  actions: {
    deleteScope: "failed_templates_only" | "failed_or_invalidated_templates_only";
    cleanupScope?: "failed_templates_only";
    sandboxDeletion: boolean;
    resetDeletesTemplates?: boolean;
    resetRebuildsTemplate?: boolean;
    resetTargetStatus?: "ready";
  };
}

export interface SandboxTemplateCleanupSummary {
  scope: "failed_templates_only" | "failed_or_invalidated_templates_only";
  scannedFailed?: number;
  deletedRecords: number;
  deletedTemplates: number;
  failures?: Array<{
    recordId?: string;
    templateId?: string | null;
    error: string;
  }>;
}

export type SandboxTemplateResetKind = "codeql_cpp" | "opengrep";

export interface SandboxTemplateResetSummary {
  kind: SandboxTemplateResetKind | "opengrep_dedicated";
  recordKind?: string;
  invalidatedRecords: number;
  deletedRecords: number;
  deletedTemplates: number;
  targetStatus: "ready";
  record: CubesandboxTemplateRecord;
}

export async function getSandboxTemplateManagementOverview(
  statusFilter?: string,
): Promise<SandboxTemplateManagementOverview> {
  const params = statusFilter ? { status: statusFilter } : undefined;
  const response = await apiClient.get<SandboxTemplateManagementOverview>(
    "/cubesandbox/templates",
    { params },
  );
  return response.data;
}

export async function deleteFailedSandboxTemplateRecord(
  recordId: string,
): Promise<SandboxTemplateCleanupSummary> {
  const response = await apiClient.delete<SandboxTemplateCleanupSummary>(
    `/cubesandbox/templates/records/${encodeURIComponent(recordId)}`,
  );
  return response.data;
}

export async function cleanupFailedSandboxTemplates(): Promise<SandboxTemplateCleanupSummary> {
  const response = await apiClient.post<SandboxTemplateCleanupSummary>(
    "/cubesandbox/templates/cleanup-failed",
  );
  return response.data;
}

export async function resetSandboxTemplateKind(
  kind: SandboxTemplateResetKind,
): Promise<SandboxTemplateResetSummary> {
  const path = kind === "codeql_cpp" ? "codeql-cpp" : "opengrep";
  const response = await apiClient.post<SandboxTemplateResetSummary>(
    `/cubesandbox/templates/${path}/reset`,
  );
  return response.data;
}
