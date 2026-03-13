import test from "node:test";
import assert from "node:assert/strict";

import {
  getProjectCardRecentTasks,
  getProjectFoundIssuesBreakdown,
} from "../src/features/projects/services/projectCardPreview.ts";

test("project issue breakdown adds bandit findings", () => {
  const breakdown = getProjectFoundIssuesBreakdown({
    projectId: "p1",
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [
      {
        project_id: "p1",
        high_count: 1,
        medium_count: 2,
        low_count: 3,
      },
    ] as any,
  });

  assert.equal(breakdown.staticIssues, 6);
  assert.equal(breakdown.totalIssues, 6);
});

test("project recent tasks includes bandit route when only bandit is enabled", () => {
  const tasks = getProjectCardRecentTasks({
    projectId: "p1",
    auditTasks: [] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [] as any,
    banditTasks: [
      {
        id: "bandit-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-12T07:00:00.000Z",
        updated_at: "2026-03-12T07:01:00.000Z",
        scan_duration_ms: 1000,
        files_scanned: 5,
        total_findings: 4,
      },
    ] as any,
  });

  assert.equal(tasks.length, 1);
  assert.equal(tasks[0]?.route.includes("tool=bandit"), true);
  assert.equal(tasks[0]?.vulnerabilities, 4);
});

test("project recent tasks groups gitleaks and bandit into one static item", () => {
  const tasks = getProjectCardRecentTasks({
    projectId: "p1",
    auditTasks: [] as any,
    agentTasks: [] as any,
    opengrepTasks: [] as any,
    gitleaksTasks: [
      {
        id: "gl-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-12T07:00:00.000Z",
        updated_at: "2026-03-12T07:00:30.000Z",
        total_findings: 2,
        scan_duration_ms: 400,
      },
    ] as any,
    banditTasks: [
      {
        id: "ba-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-12T07:00:20.000Z",
        updated_at: "2026-03-12T07:01:00.000Z",
        total_findings: 3,
        scan_duration_ms: 600,
      },
    ] as any,
  });

  assert.equal(tasks.length, 1);
  assert.equal(tasks[0]?.route.includes("gitleaksTaskId=gl-1"), true);
  assert.equal(tasks[0]?.route.includes("banditTaskId=ba-1"), true);
  assert.equal(tasks[0]?.vulnerabilities, 5);
});
