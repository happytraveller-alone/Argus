import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  batchDeleteBanditRules,
  batchRestoreBanditRules,
  batchUpdateBanditRulesEnabled,
  deleteBanditRule,
  getBanditRule,
  getBanditRules,
  restoreBanditRule,
  updateBanditRule,
  updateBanditRuleEnabled,
} from "../src/shared/api/bandit.ts";

test("bandit rules api client maps rules endpoints", async () => {
  const originalPost = apiClient.post;
  const originalGet = apiClient.get;
  const originalPatch = apiClient.patch;
  const calls: Array<{ method: string; url: string }> = [];

  apiClient.post = (async (url: string) => {
    calls.push({ method: "post", url });
    return { data: { ok: true } };
  }) as typeof apiClient.post;

  apiClient.get = (async (url: string) => {
    calls.push({ method: "get", url });
    return { data: [] };
  }) as typeof apiClient.get;

  apiClient.patch = (async (url: string) => {
    calls.push({ method: "patch", url });
    return { data: { ok: true } };
  }) as typeof apiClient.patch;

  try {
    await getBanditRules({ is_active: true, source: "builtin", keyword: "B10", deleted: "false", skip: 1, limit: 5 });
    await getBanditRule("B101");
    await updateBanditRule({ ruleId: "B101", name: "assert_used_custom" });
    await updateBanditRuleEnabled({ ruleId: "B101", is_active: false });
    await batchUpdateBanditRulesEnabled({ rule_ids: ["B101"], is_active: true });
    await deleteBanditRule("B101");
    await restoreBanditRule("B101");
    await batchDeleteBanditRules({ rule_ids: ["B101"] });
    await batchRestoreBanditRules({ rule_ids: ["B101"] });
  } finally {
    apiClient.post = originalPost;
    apiClient.get = originalGet;
    apiClient.patch = originalPatch;
  }

  assert.deepEqual(
    calls.map((item) => `${item.method}:${item.url}`),
    [
      "get:/static-tasks/bandit/rules?is_active=true&source=builtin&keyword=B10&deleted=false&skip=1&limit=5",
      "get:/static-tasks/bandit/rules/B101",
      "patch:/static-tasks/bandit/rules/B101",
      "post:/static-tasks/bandit/rules/B101/enabled",
      "post:/static-tasks/bandit/rules/batch/enabled",
      "post:/static-tasks/bandit/rules/B101/delete",
      "post:/static-tasks/bandit/rules/B101/restore",
      "post:/static-tasks/bandit/rules/batch/delete",
      "post:/static-tasks/bandit/rules/batch/restore",
    ],
  );
});
