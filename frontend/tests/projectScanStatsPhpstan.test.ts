import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectScanRunsChartData,
  buildProjectVulnsChartData,
} from "../src/features/dashboard/services/projectScanStats.ts";

test("dashboard scan runs includes completed phpstan tasks", () => {
  const rows = buildProjectScanRunsChartData({
    projects: [{ id: "p1", name: "demo" }] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [] as any,
    phpstanTasks: [
      {
        id: "ps1",
        project_id: "p1",
        status: "completed",
      },
    ] as any,
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.staticRuns, 1);
});

test("dashboard vulnerability stats includes phpstan findings", () => {
  const rows = buildProjectVulnsChartData({
    projects: [{ id: "p1", name: "demo" }] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [] as any,
    phpstanTasks: [
      {
        id: "ps1",
        project_id: "p1",
        total_findings: 9,
      },
    ] as any,
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.staticVulns, 9);
});
