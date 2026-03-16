import test from "node:test";
import assert from "node:assert/strict";

import { api } from "../src/shared/api/database.ts";
import { apiClient } from "../src/shared/api/serverClient.ts";

test("database api createAuditTask does not send branch_name", async () => {
  const originalPost = apiClient.post;
  const originalGet = apiClient.get;
  const calls: Array<{ url: string; body?: unknown }> = [];

  apiClient.post = (async (url: string, body?: unknown) => {
    calls.push({ url, body });
    return { data: { task_id: "task-1" } };
  }) as typeof apiClient.post;
  apiClient.get = (async (url: string) => {
    calls.push({ url });
    return { data: { id: "task-1" } };
  }) as typeof apiClient.get;

  try {
    await api.createAuditTask({
      project_id: "project-1",
      task_type: "repository",
      exclude_patterns: ["node_modules"],
      branch_name: "feature/remove-me",
      scan_config: {
        file_paths: ["src/app.py"],
      },
    } as any);
  } finally {
    apiClient.post = originalPost;
    apiClient.get = originalGet;
  }

  assert.equal(calls[0]?.url, "/projects/project-1/scan");
  assert.deepEqual(calls[0]?.body, {
    file_paths: ["src/app.py"],
    full_scan: false,
    exclude_patterns: ["node_modules"],
  });
});

test("database api no longer exposes getProjectBranches", () => {
  assert.equal("getProjectBranches" in api, false);
});
