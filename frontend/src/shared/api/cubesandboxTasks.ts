import { apiClient } from "@/shared/api/serverClient";

export type CubeSandboxTaskStatus =
  | "queued"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "interrupted"
  | "cleanup_failed";

export interface CubeSandboxTaskRecord {
  taskId: string;
  status: CubeSandboxTaskStatus;
  code: string;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  durationMs: number | null;
  sandboxId: string | null;
  errorCategory: string | null;
  errorMessage: string | null;
  cleanupStatus: "not_started" | "completed" | "failed";
  cleanupError: string | null;
  interruptRequested: boolean;
  timeoutSeconds: number | null;
  metadata: {
    source?: string;
    engine?: "opengrep" | "codeql" | string;
    projectId?: string;
    projectName?: string;
    taskName?: string;
    detailPath?: string;
    [key: string]: unknown;
  } | null;
}

export async function listCubeSandboxTasks(limit = 50): Promise<CubeSandboxTaskRecord[]> {
  const response = await apiClient.get<CubeSandboxTaskRecord[]>("/cubesandbox-tasks", {
    params: { limit },
  });
  return response.data;
}
