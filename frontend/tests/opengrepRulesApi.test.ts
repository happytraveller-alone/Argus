import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  createJoernScanTask,
  createOpengrepScanTask,
  getJoernScanFindings,
  getJoernScanProgress,
  getJoernScanTask,
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
      opengrep_sandbox: "a3s_box",
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
        opengrep_sandbox: "a3s_box",
      },
    },
  ]);
});

test("Joern static API maps task, progress and findings routes", async () => {
  const originalGet = apiClient.get;
  const originalPost = apiClient.post;
  const getCalls: string[] = [];
  const postCalls: Array<{ url: string; body: unknown }> = [];

  apiClient.post = (async (url: string, body: unknown) => {
    postCalls.push({ url, body });
    return {
      data: {
        id: "jn-1",
        engine: "joern",
        project_id: "project-1",
        name: "scan",
        status: "pending",
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

  apiClient.get = (async (url: string) => {
    getCalls.push(url);
    if (url.endsWith("/progress")) {
      return { data: { task_id: "jn-1", engine: "joern", status: "running", progress: 50, logs: [] } };
    }
    if (url.includes("/findings")) {
      return {
        data: [
          {
            id: "finding-1",
            scan_task_id: "jn-1",
            engine: "joern",
            rule: { check_id: "joern-c-buffer-overflow-libplist-cve-2017-6439" },
            file_path: "src/bplist.c",
            start_line: 288,
            severity: "ERROR",
            status: "open",
            confidence: "HIGH",
          },
        ],
      };
    }
    return {
      data: {
        id: "jn-1",
        engine: "joern",
        project_id: "project-1",
        name: "scan",
        status: "completed",
        target_path: ".",
        total_findings: 1,
        error_count: 1,
        warning_count: 0,
        scan_duration_ms: 1000,
        files_scanned: 1,
        lines_scanned: 300,
        created_at: "2026-05-04T00:00:00Z",
      },
    };
  }) as typeof apiClient.get;

  try {
    await createJoernScanTask({
      project_id: "project-1",
      name: "scan",
      target_path: ".",
    });
    await getJoernScanTask("jn-1");
    await getJoernScanProgress("jn-1", true);
    const findings = await getJoernScanFindings({
      taskId: "jn-1",
      skip: 0,
      limit: 20,
    });
    assert.equal(findings[0]?.engine, "joern");
  } finally {
    apiClient.get = originalGet;
    apiClient.post = originalPost;
  }

  assert.deepEqual(postCalls, [
    {
      url: "/static-tasks/joern/tasks",
      body: {
        project_id: "project-1",
        name: "scan",
        target_path: ".",
      },
    },
  ]);
  assert.deepEqual(getCalls, [
    "/static-tasks/joern/tasks/jn-1",
    "/static-tasks/joern/tasks/jn-1/progress",
    "/static-tasks/joern/tasks/jn-1/findings?skip=0&limit=20",
  ]);
});
