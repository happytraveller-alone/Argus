import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStatsSummary,
  createTokenUsageAccumulator,
} from "../src/pages/AgentAudit/detailViewModel.ts";

test("buildStatsSummary uses the task management progress heuristic for agent detail pages", () => {
  const now = new Date("2026-03-12T08:00:00.000Z");

  const runningSummary = buildStatsSummary({
    task: {
      status: "running",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: "2026-03-12T07:45:00.000Z",
      progress_percentage: 2,
    },
    displayFindings: [],
    tokenUsage: createTokenUsageAccumulator(),
    now,
  });

  assert.equal(runningSummary.progressPercent, 95);

  const pendingSummary = buildStatsSummary({
    task: {
      status: "pending",
      created_at: "2026-03-12T07:00:00.000Z",
      started_at: null,
      progress_percentage: 88,
    },
    displayFindings: [],
    tokenUsage: createTokenUsageAccumulator(),
    now,
  });

  assert.equal(pendingSummary.progressPercent, 15);
});

test("buildStatsSummary treats terminal agent states as 100 percent regardless of backend progress_percentage", () => {
  const now = new Date("2026-03-12T08:00:00.000Z");

  for (const status of [
    "completed",
    "failed",
    "cancelled",
    "interrupted",
  ]) {
    const summary = buildStatsSummary({
      task: {
        status,
        created_at: "2026-03-12T07:00:00.000Z",
        started_at: "2026-03-12T07:10:00.000Z",
        completed_at: "2026-03-12T07:50:00.000Z",
        progress_percentage: 11,
      },
      displayFindings: [],
      tokenUsage: createTokenUsageAccumulator(),
      now,
    });

    assert.equal(summary.progressPercent, 100, `${status} should show 100%`);
  }
});
