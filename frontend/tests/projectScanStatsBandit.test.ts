import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectScanRunsChartData,
  buildProjectVulnsChartData,
} from "../src/features/dashboard/services/projectScanStats.ts";

test("dashboard scan runs includes completed bandit tasks", () => {
  const rows = buildProjectScanRunsChartData({
    projects: [{ id: "p1", name: "demo" }] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [
      {
        id: "b1",
        project_id: "p1",
        status: "completed",
      },
    ] as any,
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.staticRuns, 1);
  assert.equal(rows[0]?.totalRuns, 1);
});

test("dashboard vulnerability stats includes bandit high/medium/low", () => {
  const rows = buildProjectVulnsChartData({
    projects: [{ id: "p1", name: "demo" }] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [
      {
        id: "b1",
        project_id: "p1",
        high_count: 2,
        medium_count: 3,
        low_count: 1,
      },
    ] as any,
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.staticVulns, 6);
  assert.equal(rows[0]?.totalVulns, 6);
});

