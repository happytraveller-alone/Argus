import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  createOpengrepScanTask,
  getAllOpengrepRules,
  getOpengrepRuleStats,
  getOpengrepRules,
  getOpengrepRulesPage,
} from "../src/shared/api/opengrep.ts";

test("getOpengrepRules requests the first page by default", async () => {
  const originalGet = apiClient.get;
  const calls: string[] = [];

  apiClient.get = (async (url: string) => {
    calls.push(url);
    return { data: [] };
  }) as typeof apiClient.get;

  try {
    await getOpengrepRules();
    await getOpengrepRules({ is_active: true });
  } finally {
    apiClient.get = originalGet;
  }

  assert.deepEqual(calls, [
    "/static-tasks/rules?limit=10",
    "/static-tasks/rules?is_active=true&limit=10",
  ]);
});

test("getOpengrepRulesPage preserves backend total for server-side pagination", async () => {
  const originalGet = apiClient.get;

  apiClient.get = (async () => {
    return {
      data: {
        data: [{ id: "r-1", name: "rule-1" }],
        total: 37,
      },
    };
  }) as typeof apiClient.get;

  try {
    const response = await getOpengrepRulesPage({ skip: 10, limit: 10 });
    assert.equal(response.total, 37);
    assert.deepEqual(response.data, [{ id: "r-1", name: "rule-1" }]);
  } finally {
    apiClient.get = originalGet;
  }
});

test("getAllOpengrepRules preserves the full-list contract for callers that need every rule", async () => {
  const originalGet = apiClient.get;
  const calls: string[] = [];

  apiClient.get = (async (url: string) => {
    calls.push(url);
    return { data: [] };
  }) as typeof apiClient.get;

  try {
    await getAllOpengrepRules();
    await getAllOpengrepRules({ is_active: true });
  } finally {
    apiClient.get = originalGet;
  }

  assert.deepEqual(calls, [
    "/static-tasks/rules?limit=10000",
    "/static-tasks/rules?is_active=true&limit=10000",
  ]);
});

test("getOpengrepRuleStats maps the dedicated stats endpoint", async () => {
  const originalGet = apiClient.get;
  const calls: string[] = [];

  apiClient.get = (async (url: string) => {
    calls.push(url);
    return {
      data: {
        total: 12,
        active: 10,
        inactive: 2,
        language_count: 3,
        languages: ["go", "python", "rust"],
        vulnerability_type_count: 1,
      },
    };
  }) as typeof apiClient.get;

  try {
    const response = await getOpengrepRuleStats();
    assert.equal(response.total, 12);
    assert.deepEqual(response.languages, ["go", "python", "rust"]);
  } finally {
    apiClient.get = originalGet;
  }

  assert.deepEqual(calls, ["/static-tasks/rules/stats"]);
});

test("createOpengrepScanTask sends the selected sandbox mode", async () => {
  const originalPost = apiClient.post;
  const calls: Array<{ url: string; body: unknown }> = [];

  apiClient.post = (async (url: string, body: unknown) => {
    calls.push({ url, body });
    return {
      data: {
        id: "og-1",
        engine: "opengrep",
        project_id: "project-1",
        name: "scan",
        status: "running",
        target_path: ".",
        total_findings: 0,
        error_count: 0,
        warning_count: 0,
        scan_duration_ms: 0,
        files_scanned: 0,
        lines_scanned: 0,
        created_at: "2026-05-04T00:00:00Z",
      },
    };
  }) as typeof apiClient.post;

  try {
    await createOpengrepScanTask({
      project_id: "project-1",
      name: "scan",
      rule_ids: ["rule-1"],
      target_path: ".",
      opengrep_sandbox: "oci_cubesandbox",
    });
  } finally {
    apiClient.post = originalPost;
  }

  assert.deepEqual(calls, [
    {
      url: "/static-tasks/tasks",
      body: {
        project_id: "project-1",
        name: "scan",
        rule_ids: ["rule-1"],
        target_path: ".",
        opengrep_sandbox: "oci_cubesandbox",
      },
    },
  ]);
});
