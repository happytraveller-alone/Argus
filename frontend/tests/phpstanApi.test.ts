import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  createPhpstanScanTask,
  getPhpstanScanTask,
  getPhpstanScanTasks,
  getPhpstanFindings,
  updatePhpstanFindingStatus,
} from "../src/shared/api/phpstan.ts";

test("phpstan api client maps task and finding endpoints", async () => {
  const originalPost = apiClient.post;
  const originalGet = apiClient.get;
  const calls: Array<{ method: string; url: string; payload?: unknown }> = [];

  apiClient.post = (async (url: string, payload?: unknown) => {
    calls.push({ method: "post", url, payload });
    return { data: { ok: true } };
  }) as typeof apiClient.post;

  apiClient.get = (async (url: string) => {
    calls.push({ method: "get", url });
    return { data: [] };
  }) as typeof apiClient.get;

  try {
    await createPhpstanScanTask({ project_id: "p1", level: 6 });
    await getPhpstanScanTask("task-1");
    await getPhpstanScanTasks({ projectId: "p1", status: "completed", skip: 2, limit: 10 });
    await getPhpstanFindings({ taskId: "task-1", status: "open", skip: 1, limit: 5 });
    await updatePhpstanFindingStatus({ findingId: "f-1", status: "verified" });
  } finally {
    apiClient.post = originalPost;
    apiClient.get = originalGet;
  }

  assert.deepEqual(
    calls.map((item) => `${item.method}:${item.url}`),
    [
      "post:/static-tasks/phpstan/scan",
      "get:/static-tasks/phpstan/tasks/task-1",
      "get:/static-tasks/phpstan/tasks?project_id=p1&status=completed&skip=2&limit=10",
      "get:/static-tasks/phpstan/tasks/task-1/findings?status=open&skip=1&limit=5",
      "post:/static-tasks/phpstan/findings/f-1/status",
    ],
  );
});
