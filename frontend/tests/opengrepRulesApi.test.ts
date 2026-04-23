import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { getOpengrepRules } from "../src/shared/api/opengrep.ts";

test("getOpengrepRules requests full default rule set when limit is omitted", async () => {
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
    "/static-tasks/rules?limit=10000",
    "/static-tasks/rules?is_active=true&limit=10000",
  ]);
});
