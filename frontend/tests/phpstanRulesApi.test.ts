import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
  batchUpdatePhpstanRulesEnabled,
  getPhpstanRule,
  getPhpstanRules,
  updatePhpstanRuleEnabled,
} from "../src/shared/api/phpstan.ts";

test("phpstan rules api client maps rules endpoints", async () => {
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
    await getPhpstanRules({ is_active: true, source: "official_extension", keyword: "strict", skip: 1, limit: 5 });
    await getPhpstanRule("pkg:RuleClass");
    await updatePhpstanRuleEnabled({ ruleId: "pkg:RuleClass", is_active: false });
    await batchUpdatePhpstanRulesEnabled({ rule_ids: ["pkg:RuleClass"], is_active: true });
  } finally {
    apiClient.post = originalPost;
    apiClient.get = originalGet;
  }

  assert.deepEqual(
    calls.map((item) => `${item.method}:${item.url}`),
    [
      "get:/static-tasks/phpstan/rules?is_active=true&source=official_extension&keyword=strict&skip=1&limit=5",
      "get:/static-tasks/phpstan/rules/pkg%3ARuleClass",
      "post:/static-tasks/phpstan/rules/pkg%3ARuleClass/enabled",
      "post:/static-tasks/phpstan/rules/batch/enabled",
    ],
  );
});
