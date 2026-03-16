import test from "node:test";
import assert from "node:assert/strict";

import { getTerminalStatusTransitionPolicy } from "../src/pages/AgentAudit/terminalStatePolicy.ts";

test("terminal status transition triggers reconcile and backfill without boundary promotion", () => {
  const policy = getTerminalStatusTransitionPolicy({
    previousStatus: "running",
    currentStatus: "completed",
  });

  assert.equal(policy.didEnterTerminal, true);
  assert.equal(policy.shouldReconcileLogs, true);
  assert.equal(policy.shouldBackfill, true);
  assert.equal(policy.shouldMarkBoundaryFromStatus, false);
});

test("non-terminal status transition does not trigger terminal recovery policy", () => {
  const policy = getTerminalStatusTransitionPolicy({
    previousStatus: "running",
    currentStatus: "running",
  });

  assert.deepEqual(policy, {
    didEnterTerminal: false,
    shouldReconcileLogs: false,
    shouldBackfill: false,
    shouldMarkBoundaryFromStatus: false,
  });
});
