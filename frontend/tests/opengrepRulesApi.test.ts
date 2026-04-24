import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import {
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
