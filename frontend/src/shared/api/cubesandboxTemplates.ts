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
}

export async function getCodeqlCppTemplateStatus(): Promise<CubesandboxTemplateRecord> {
  const response = await apiClient.get<CubesandboxTemplateRecord>(
    "/api/v1/cubesandbox/templates/codeql-cpp",
  );
  return response.data;
}

export async function provisionCodeqlCppTemplate(): Promise<CubesandboxTemplateRecord> {
  const response = await apiClient.post<CubesandboxTemplateRecord>(
    "/api/v1/cubesandbox/templates/codeql-cpp/provision",
  );
  return response.data;
}

export async function invalidateCodeqlCppTemplate(): Promise<{ affected: number }> {
  const response = await apiClient.post<{ affected: number }>(
    "/api/v1/cubesandbox/templates/codeql-cpp/invalidate",
  );
  return response.data;
}

export function getCodeqlCppTemplateStreamUrl(): string {
  return `${getApiBaseUrl()}/api/v1/cubesandbox/templates/codeql-cpp/stream`;
}
