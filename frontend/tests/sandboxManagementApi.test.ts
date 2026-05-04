import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  cleanupFailedSandboxTemplates,
  deleteFailedSandboxTemplateRecord,
  getSandboxTemplateManagementOverview,
  resetSandboxTemplateKind,
} from "../src/shared/api/cubesandboxTemplates.ts";

test("sandbox template management api uses bounded cubesandbox template routes", async () => {
  const originalGet = apiClient.get;
  const originalPost = apiClient.post;
  const originalDelete = apiClient.delete;
  const calls: Array<{ method: string; url: string }> = [];

  apiClient.get = (async (url: string) => {
    calls.push({ method: "GET", url });
    return { data: { templates: [], failedCount: 0, actions: { deleteScope: "failed_templates_only" } } };
  }) as typeof apiClient.get;
  apiClient.post = (async (url: string) => {
    calls.push({ method: "POST", url });
    return {
      data: {
        scope: "failed_templates_only",
        invalidatedRecords: 1,
        deletedRecords: 1,
        deletedTemplates: 1,
        targetStatus: "ready",
        record: { status: "pending", templateId: null, artifactId: null, jobId: null, errorMessage: null, buildLogTail: "" },
      },
    };
  }) as typeof apiClient.post;
  apiClient.delete = (async (url: string) => {
    calls.push({ method: "DELETE", url });
    return { data: { scope: "failed_templates_only", deletedRecords: 1 } };
  }) as typeof apiClient.delete;

  try {
    await getSandboxTemplateManagementOverview();
    await cleanupFailedSandboxTemplates();
    await deleteFailedSandboxTemplateRecord("record-1");
    await resetSandboxTemplateKind("codeql_cpp");
    await resetSandboxTemplateKind("opengrep");
  } finally {
    apiClient.get = originalGet;
    apiClient.post = originalPost;
    apiClient.delete = originalDelete;
  }

  assert.deepEqual(calls, [
    { method: "GET", url: "/cubesandbox/templates" },
    { method: "POST", url: "/cubesandbox/templates/cleanup-failed" },
    { method: "DELETE", url: "/cubesandbox/templates/records/record-1" },
    { method: "POST", url: "/cubesandbox/templates/codeql-cpp/reset" },
    { method: "POST", url: "/cubesandbox/templates/opengrep/reset" },
  ]);
});
