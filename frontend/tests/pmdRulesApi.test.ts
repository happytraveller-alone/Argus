import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  createPmdScanTask,
  deletePmdRuleConfig,
  getPmdFinding,
  getPmdFindings,
  getPmdBuiltinRuleset,
  getPmdBuiltinRulesets,
  getPmdPresets,
  getPmdRuleConfig,
  getPmdRuleConfigs,
  getPmdScanTask,
  getPmdScanTasks,
  interruptPmdScanTask,
  importPmdRuleConfig,
  updatePmdRuleConfig,
  updatePmdFindingStatus,
} from "../src/shared/api/pmd.ts";

test("pmd api client maps preset, ruleset, config, and scan endpoints", async () => {
  const originalGet = apiClient.get;
  const originalPost = apiClient.post;
  const originalPatch = apiClient.patch;
  const originalDelete = apiClient.delete;
  const calls: Array<{ method: string; url: string; payload?: unknown }> = [];

  apiClient.get = (async (url: string) => {
    calls.push({ method: "get", url });
    return { data: [] };
  }) as typeof apiClient.get;

  apiClient.post = (async (url: string, payload?: unknown) => {
    calls.push({ method: "post", url, payload });
    return { data: { ok: true } };
  }) as typeof apiClient.post;

  apiClient.patch = (async (url: string, payload?: unknown) => {
    calls.push({ method: "patch", url, payload });
    return { data: { ok: true } };
  }) as typeof apiClient.patch;

  apiClient.delete = (async (url: string) => {
    calls.push({ method: "delete", url });
    return { data: { ok: true } };
  }) as typeof apiClient.delete;

  try {
    await getPmdPresets();
    await getPmdBuiltinRulesets({ keyword: "crypto", language: "java", limit: 20 });
    await getPmdBuiltinRuleset("category/apex/security.xml");
    await importPmdRuleConfig({
      name: "custom-pmd",
      description: "demo",
      xmlFile: new File(["<ruleset />"], "custom.xml", { type: "text/xml" }),
    });
    await getPmdRuleConfigs({ is_active: true, keyword: "custom", skip: 1, limit: 5 });
    await getPmdRuleConfig("cfg/1");
    await updatePmdRuleConfig("cfg/1", {
      name: "updated",
      description: "updated desc",
      is_active: false,
    });
    await createPmdScanTask({
      project_id: "project-1",
      name: "PMD Scan",
      target_path: ".",
      ruleset: "security",
    });
    await getPmdScanTasks({ project_id: "project-1", skip: 2, limit: 20 });
    await getPmdScanTask("task-1");
    await getPmdFindings({ taskId: "task-1", status: "open", skip: 3, limit: 40 });
    await getPmdFinding({ taskId: "task-1", findingId: "finding-1" });
    await updatePmdFindingStatus("finding-1", "verified");
    await interruptPmdScanTask("task-1");
    await deletePmdRuleConfig("cfg/1");
  } finally {
    apiClient.get = originalGet;
    apiClient.post = originalPost;
    apiClient.patch = originalPatch;
    apiClient.delete = originalDelete;
  }

  assert.equal(calls[3]?.payload instanceof FormData, true);
  assert.deepEqual(
    calls.map((item) => `${item.method}:${item.url}`),
    [
      "get:/static-tasks/pmd/presets",
      "get:/static-tasks/pmd/builtin-rulesets?keyword=crypto&language=java&limit=20",
      "get:/static-tasks/pmd/builtin-rulesets/category%2Fapex%2Fsecurity.xml",
      "post:/static-tasks/pmd/rule-configs/import",
      "get:/static-tasks/pmd/rule-configs?is_active=true&keyword=custom&skip=1&limit=5",
      "get:/static-tasks/pmd/rule-configs/cfg%2F1",
      "patch:/static-tasks/pmd/rule-configs/cfg%2F1",
      "post:/static-tasks/pmd/scan",
      "get:/static-tasks/pmd/tasks?project_id=project-1&skip=2&limit=20",
      "get:/static-tasks/pmd/tasks/task-1",
      "get:/static-tasks/pmd/tasks/task-1/findings?status=open&skip=3&limit=40",
      "get:/static-tasks/pmd/tasks/task-1/findings/finding-1",
      "post:/static-tasks/pmd/findings/finding-1/status?status=verified",
      "post:/static-tasks/pmd/tasks/task-1/interrupt",
      "delete:/static-tasks/pmd/rule-configs/cfg%2F1",
    ],
  );
});
