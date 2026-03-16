import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  batchUpdateBanditRulesEnabled,
  getBanditRule,
  getBanditRules,
  updateBanditRuleEnabled,
} from "../src/shared/api/bandit.ts";

test("bandit rules api client maps rules endpoints", async () => {
  const originalPost = apiClient.post;
  const originalGet = apiClient.get;
  const calls: Array<{ method: string; url: string }> = [];

  apiClient.post = (async (url: string) => {
    calls.push({ method: "post", url });
    return { data: { ok: true } };
  }) as typeof apiClient.post;

  apiClient.get = (async (url: string) => {
    calls.push({ method: "get", url });
    return { data: [] };
  }) as typeof apiClient.get;

  try {
    await getBanditRules({ is_active: true, source: "builtin", keyword: "B10", skip: 1, limit: 5 });
    await getBanditRule("B101");
    await updateBanditRuleEnabled({ ruleId: "B101", is_active: false });
    await batchUpdateBanditRulesEnabled({ rule_ids: ["B101"], is_active: true });
  } finally {
    apiClient.post = originalPost;
    apiClient.get = originalGet;
  }

  assert.deepEqual(
    calls.map((item) => `${item.method}:${item.url}`),
    [
      "get:/static-tasks/bandit/rules?is_active=true&source=builtin&keyword=B10&skip=1&limit=5",
      "get:/static-tasks/bandit/rules/B101",
      "post:/static-tasks/bandit/rules/B101/enabled",
      "post:/static-tasks/bandit/rules/batch/enabled",
    ],
  );
});
