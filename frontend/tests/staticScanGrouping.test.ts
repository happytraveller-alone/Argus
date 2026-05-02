import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStaticScanGroups,
  resolveStaticScanGroupStatus,
} from "../src/features/tasks/services/staticScanGrouping.ts";
import { appendStaticScanBatchMarker } from "../src/shared/utils/staticScanBatch.ts";

test("groups engines with same static batch id", () => {
  const batchId = "batch-1";
  const groups = buildStaticScanGroups({
    opengrepTasks: [
      {
        id: "og-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-13T10:00:00.000Z",
        name: appendStaticScanBatchMarker("静态分析-Opengrep-p1", batchId),
      },
    ] as any,
    codeqlTasks: [
      {
        id: "cq-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-13T10:05:00.000Z",
        name: appendStaticScanBatchMarker("静态分析-CodeQL-p1", batchId),
      },
    ] as any,
  });

  assert.equal(groups.length, 1);
  assert.equal(groups[0]?.opengrepTask?.id, "og-1");
  assert.equal(groups[0]?.codeqlTask?.id, "cq-1");
});

test("does not merge different static batches even within pairing window", () => {
  const groups = buildStaticScanGroups({
    opengrepTasks: [
      {
        id: "og-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-13T10:00:00.000Z",
        name: appendStaticScanBatchMarker("静态分析-Opengrep-p1", "batch-1"),
      },
    ] as any,
    codeqlTasks: [
      {
        id: "cq-1",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-13T10:00:20.000Z",
        name: appendStaticScanBatchMarker("静态分析-CodeQL-p1", "batch-2"),
      },
    ] as any,
  });

  assert.equal(groups.length, 2);
});

test("resolveStaticScanGroupStatus returns failed/interrupted/pending without OTHER", () => {
  assert.equal(
    resolveStaticScanGroupStatus({
      opengrepTask: {
        id: "og-1",
        project_id: "p1",
        status: "failed",
        created_at: "2026-03-17T00:00:00.000Z",
      } as any,
    }),
    "failed",
  );

  assert.equal(
    resolveStaticScanGroupStatus({
      codeqlTask: {
        id: "cq-1",
        project_id: "p1",
        status: "interrupted",
        created_at: "2026-03-17T00:00:00.000Z",
      } as any,
    }),
    "interrupted",
  );

  assert.equal(
    resolveStaticScanGroupStatus({
      codeqlTask: {
        id: "cq-2",
        project_id: "p1",
        status: "pending",
        created_at: "2026-03-17T00:00:01.000Z",
      } as any,
    }),
    "pending",
  );

  assert.equal(
    resolveStaticScanGroupStatus({
      opengrepTask: {
        id: "og-2",
        project_id: "p1",
        status: "pending",
        created_at: "2026-03-17T00:00:00.000Z",
      } as any
    }),
    "pending",
  );

  assert.equal(
    resolveStaticScanGroupStatus({
      codeqlTask: {
        id: "cq-3",
        project_id: "p1",
        status: "completed",
        created_at: "2026-03-17T00:00:00.000Z",
      } as any
    }),
    "completed",
  );
});
