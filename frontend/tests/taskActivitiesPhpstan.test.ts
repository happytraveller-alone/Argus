import test from "node:test";
import assert from "node:assert/strict";

import { appendStaticScanBatchMarker } from "../src/shared/utils/staticScanBatch.ts";
import { apiClient } from "../src/shared/api/serverClient.ts";
import { fetchTaskActivities } from "../src/features/tasks/services/taskActivities.ts";

test("task activities build phpstan-only static route with tool=phpstan", async () => {
  const originalGet = apiClient.get;
  apiClient.get = (async (url: string) => {
    if (url.startsWith("/agent-tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/gitleaks/tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/bandit/tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/phpstan/tasks")) {
      return {
        data: [
          {
            id: "ps-1",
            project_id: "project-1",
            name: "静态分析-PHPStan",
            status: "completed",
            total_findings: 3,
            scan_duration_ms: 800,
            files_scanned: 5,
            created_at: "2026-03-14T10:00:00.000Z",
            updated_at: "2026-03-14T10:01:00.000Z",
          },
        ],
      };
    }
    throw new Error(`Unexpected apiClient.get call: ${url}`);
  }) as typeof apiClient.get;

  try {
    const activities = await fetchTaskActivities(
      [{ id: "project-1", name: "Demo Project" }] as any,
      20,
    );
    assert.equal(activities.length, 1);
    assert.equal(activities[0]?.route.includes("tool=phpstan"), true);
    assert.equal(activities[0]?.route.includes("phpstanTaskId=ps-1"), true);
    assert.deepEqual(activities[0]?.staticFindingStats, {
      critical: 0,
      high: 0,
      medium: 0,
      low: 3,
    });
  } finally {
    apiClient.get = originalGet;
  }
});

test("task activities groups phpstan with same batch static tasks", async () => {
  const originalGet = apiClient.get;
  const batchId = "batch-phpstan-1";

  apiClient.get = (async (url: string) => {
    if (url.startsWith("/agent-tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/tasks")) {
      return {
        data: [
          {
            id: "og-1",
            project_id: "project-1",
            name: appendStaticScanBatchMarker("静态分析-Opengrep", batchId),
            status: "completed",
            total_findings: 1,
            error_count: 1,
            warning_count: 0,
            scan_duration_ms: 300,
            files_scanned: 1,
            lines_scanned: 10,
            created_at: "2026-03-14T11:00:00.000Z",
            updated_at: "2026-03-14T11:01:00.000Z",
          },
        ],
      };
    }
    if (url.startsWith("/static-tasks/gitleaks/tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/bandit/tasks")) return { data: [] };
    if (url.startsWith("/static-tasks/phpstan/tasks")) {
      return {
        data: [
          {
            id: "ps-1",
            project_id: "project-1",
            name: appendStaticScanBatchMarker("静态分析-PHPStan", batchId),
            status: "completed",
            total_findings: 2,
            scan_duration_ms: 600,
            files_scanned: 3,
            created_at: "2026-03-14T11:00:10.000Z",
            updated_at: "2026-03-14T11:01:00.000Z",
          },
        ],
      };
    }
    throw new Error(`Unexpected apiClient.get call: ${url}`);
  }) as typeof apiClient.get;

  try {
    const activities = await fetchTaskActivities(
      [{ id: "project-1", name: "Demo Project" }] as any,
      20,
    );
    assert.equal(activities.length, 1);
    assert.equal(activities[0]?.route.includes("opengrepTaskId=og-1"), true);
    assert.equal(activities[0]?.route.includes("phpstanTaskId=ps-1"), true);
  } finally {
    apiClient.get = originalGet;
  }
});
