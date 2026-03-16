import test from "node:test";
import assert from "node:assert/strict";

import {
  getProjectCardRecentTasks,
  getProjectFoundIssuesBreakdown,
} from "../src/features/projects/services/projectCardPreview.ts";

test("project issue breakdown adds phpstan findings", () => {
  const breakdown = getProjectFoundIssuesBreakdown({
    projectId: "p1",
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [] as any,
    phpstanTasks: [
      {
        project_id: "p1",
        total_findings: 5,
      },
    ] as any,
  });

  assert.equal(breakdown.staticIssues, 5);
  assert.equal(breakdown.totalIssues, 5);
});

test("project recent tasks includes phpstan route when only phpstan is enabled", () => {
  const tasks = getProjectCardRecentTasks({
    projectId: "p1",
    auditTasks: [] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [] as any,
    phpstanTasks: [
      {
        id: "phpstan-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-14T07:00:00.000Z",
        updated_at: "2026-03-14T07:01:00.000Z",
        scan_duration_ms: 1200,
        files_scanned: 4,
        total_findings: 5,
      },
    ] as any,
  });

  assert.equal(tasks.length, 1);
  assert.equal(tasks[0]?.route.includes("tool=phpstan"), true);
  assert.equal(tasks[0]?.vulnerabilities, 5);
});
