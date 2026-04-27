import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { updateAgentFindingStatus } from "../src/shared/api/agentTasks.ts";

test("updateAgentFindingStatus 调用 /status 路径并通过 query 传递状态", async () => {
  const originalPatch = apiClient.patch;
  const calls: Array<{ url: string; payload: unknown; config: unknown }> = [];

  apiClient.patch = (async (url: string, payload?: unknown, config?: unknown) => {
    calls.push({ url, payload, config });
    return {
      data: {
        message: "状态已更新",
        finding_id: "finding-1",
        status: "false_positive",
      },
    };
  }) as typeof apiClient.patch;

  try {
    const result = await updateAgentFindingStatus(
      "task-1",
      "finding-1",
      "false_positive",
    );

    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "/agent-tasks/task-1/findings/finding-1/status");
    assert.equal(calls[0]?.payload, undefined);
    assert.deepEqual(calls[0]?.config, {
      params: {
        status: "false_positive",
      },
    });
    assert.deepEqual(result, {
      message: "状态已更新",
      finding_id: "finding-1",
      status: "false_positive",
    });
  } finally {
    apiClient.patch = originalPatch;
  }
});

test("createAgentTask strips static/bootstrap candidate fields before posting", async () => {
  const originalPost = apiClient.post;
  const calls: Array<{ url: string; payload: unknown }> = [];

  apiClient.post = (async (url: string, payload?: unknown) => {
    calls.push({ url, payload });
    return {
      data: {
        id: "agent-task-1",
        project_id: "project-1",
      },
    };
  }) as typeof apiClient.post;

  try {
    const { createAgentTask } = await import("../src/shared/api/agentTasks.ts");
    await createAgentTask({
      project_id: "project-1",
      name: "智能审计",
      audit_scope: { mode: "project" },
      target_vulnerabilities: ["sql_injection"],
      exclude_patterns: ["vendor/**"],
      target_files: ["src/app.ts"],
      verification_level: "analysis_with_poc_plan",
      max_iterations: 3,
      token_budget: 1000,
    });

    assert.equal(calls[0]?.url, "/agent-tasks/");
    assert.deepEqual(calls[0]?.payload, {
      project_id: "project-1",
      name: "智能审计",
      audit_scope: { mode: "project" },
    });
    assert.equal("target_vulnerabilities" in (calls[0]?.payload as Record<string, unknown>), false);
    assert.equal("target_files" in (calls[0]?.payload as Record<string, unknown>), false);
    assert.equal("exclude_patterns" in (calls[0]?.payload as Record<string, unknown>), false);
  } finally {
    apiClient.post = originalPost;
  }
});
