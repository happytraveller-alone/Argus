import test from "node:test";
import assert from "node:assert/strict";

test("getEstimatedTaskProgressPercent follows the task management progress rules", async () => {
  const { getEstimatedTaskProgressPercent } = await import(
    "../src/features/tasks/services/taskProgress.ts"
  );

  const baseCreatedAt = "2026-03-12T07:00:00.000Z";

  assert.equal(
    getEstimatedTaskProgressPercent({
      status: "pending",
      createdAt: baseCreatedAt,
      startedAt: null,
    }),
    15,
  );

  assert.equal(
    getEstimatedTaskProgressPercent(
      {
        status: "running",
        createdAt: baseCreatedAt,
        startedAt: "2026-03-12T07:00:00.000Z",
      },
      Date.parse("2026-03-12T07:00:00.000Z"),
    ),
    35,
  );

  assert.equal(
    getEstimatedTaskProgressPercent(
      {
        status: "running",
        createdAt: baseCreatedAt,
        startedAt: "2026-03-12T07:10:00.000Z",
      },
      Date.parse("2026-03-12T07:20:00.000Z"),
    ),
    75,
  );

  assert.equal(
    getEstimatedTaskProgressPercent(
      {
        status: "running",
        createdAt: baseCreatedAt,
        startedAt: "2026-03-12T07:00:00.000Z",
      },
      Date.parse("2026-03-12T08:00:00.000Z"),
    ),
    95,
  );

  for (const terminalStatus of [
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "aborted",
  ]) {
    assert.equal(
      getEstimatedTaskProgressPercent({
        status: terminalStatus,
        createdAt: baseCreatedAt,
        startedAt: "2026-03-12T07:10:00.000Z",
      }),
      100,
      `${terminalStatus} should map to 100%`,
    );
  }
});

test("getEstimatedTaskProgressPercent falls back safely for invalid timestamps and unknown statuses", async () => {
  const { getEstimatedTaskProgressPercent } = await import(
    "../src/features/tasks/services/taskProgress.ts"
  );

  assert.equal(
    getEstimatedTaskProgressPercent(
      {
        status: "running",
        createdAt: "not-a-date",
        startedAt: null,
      },
      Date.parse("2026-03-12T07:00:00.000Z"),
    ),
    35,
  );

  assert.equal(
    getEstimatedTaskProgressPercent({
      status: "queued",
      createdAt: "2026-03-12T07:00:00.000Z",
      startedAt: null,
    }),
    0,
  );
});
