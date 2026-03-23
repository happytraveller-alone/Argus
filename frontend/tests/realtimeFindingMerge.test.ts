import test from "node:test";
import assert from "node:assert/strict";

import { mergeRealtimeFindingsBatch } from "../src/pages/AgentAudit/realtimeFindingMerge.ts";
import { isVisibleVerifiedVulnerability } from "../src/pages/AgentAudit/detailViewModel.ts";
import * as detailViewModel from "../src/pages/AgentAudit/detailViewModel.ts";
import type { RealtimeMergedFindingItem } from "../src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx";

function createFinding(
  overrides: Partial<RealtimeMergedFindingItem> = {},
): RealtimeMergedFindingItem {
  return {
    id: overrides.id ?? "finding-1",
    merge_key: overrides.merge_key ?? "merge-1",
    fingerprint: overrides.fingerprint ?? "fingerprint-1",
    title: overrides.title ?? "SQL Injection",
    severity: overrides.severity ?? "high",
    display_severity: overrides.display_severity ?? "high",
    verification_progress: overrides.verification_progress ?? "pending",
    vulnerability_type: overrides.vulnerability_type ?? "SQL Injection",
    is_verified: overrides.is_verified ?? false,
    timestamp: overrides.timestamp ?? "2026-03-23T08:00:00.000Z",
    ...overrides,
  };
}

test("mergeRealtimeFindingsBatch 不会把 is_verified=true 的可见漏洞降级回 pending", () => {
  const eventFinding = createFinding({
    id: "event-finding",
    merge_key: "same-finding",
    fingerprint: "same-finding",
    is_verified: true,
    verification_progress: "pending",
    confidence: 0.91,
    timestamp: "2026-03-23T08:00:00.000Z",
  });
  const dbFinding = createFinding({
    id: "db-finding",
    merge_key: "same-finding",
    fingerprint: "same-finding",
    is_verified: true,
    verification_progress: "pending",
    confidence: 0.91,
    timestamp: "2026-03-23T08:05:00.000Z",
  });

  assert.equal(isVisibleVerifiedVulnerability(eventFinding), true);
  assert.equal(isVisibleVerifiedVulnerability(dbFinding), true);

  const merged = mergeRealtimeFindingsBatch([eventFinding], [dbFinding], {
    source: "db",
  });

  assert.equal(merged.length, 1);
  assert.equal(merged[0]?.is_verified, true);
  assert.equal(merged[0]?.verification_progress, "verified");
  assert.equal(isVisibleVerifiedVulnerability(merged[0]!), true);
});

test("verified-only 列表翻到下一页后仍保持 verified-only 总数和内容", () => {
  const merged = mergeRealtimeFindingsBatch(
    [
      createFinding({
        id: "event-1",
        merge_key: "finding-1",
        fingerprint: "finding-1",
        is_verified: true,
        verification_progress: "pending",
        confidence: 0.91,
        timestamp: "2026-03-23T08:01:00.000Z",
      }),
      createFinding({
        id: "event-2",
        merge_key: "finding-2",
        fingerprint: "finding-2",
        is_verified: true,
        verification_progress: "verified",
        confidence: 0.86,
        timestamp: "2026-03-23T08:02:00.000Z",
      }),
      createFinding({
        id: "event-3",
        merge_key: "finding-3",
        fingerprint: "finding-3",
        is_verified: true,
        verification_progress: "pending",
        confidence: 0.72,
        timestamp: "2026-03-23T08:03:00.000Z",
      }),
      createFinding({
        id: "event-4",
        merge_key: "finding-4",
        fingerprint: "finding-4",
        is_verified: true,
        verification_progress: "verified",
        confidence: 0.68,
        timestamp: "2026-03-23T08:04:00.000Z",
      }),
    ],
    [
      createFinding({
        id: "db-1",
        merge_key: "finding-1",
        fingerprint: "finding-1",
        is_verified: true,
        verification_progress: "pending",
        confidence: 0.91,
        timestamp: "2026-03-23T08:11:00.000Z",
      }),
      createFinding({
        id: "db-2",
        merge_key: "finding-2",
        fingerprint: "finding-2",
        is_verified: true,
        verification_progress: "verified",
        confidence: 0.86,
        timestamp: "2026-03-23T08:12:00.000Z",
      }),
      createFinding({
        id: "db-3",
        merge_key: "finding-3",
        fingerprint: "finding-3",
        is_verified: true,
        verification_progress: "pending",
        confidence: 0.72,
        timestamp: "2026-03-23T08:13:00.000Z",
      }),
      createFinding({
        id: "db-4",
        merge_key: "finding-4",
        fingerprint: "finding-4",
        is_verified: true,
        verification_progress: "verified",
        confidence: 0.68,
        timestamp: "2026-03-23T08:14:00.000Z",
      }),
    ],
    { source: "db" },
  );

  const pageOne = detailViewModel.buildFindingTableState({
    items: merged,
    filters: {
      keyword: "",
      severity: "all",
    },
    page: 1,
    pageSize: 3,
  });
  const pageTwo = detailViewModel.buildFindingTableState({
    items: merged,
    filters: {
      keyword: "",
      severity: "all",
    },
    page: 2,
    pageSize: 3,
  });

  assert.equal(pageOne.totalRows, 4);
  assert.equal(pageTwo.totalRows, 4);
  assert.equal(pageOne.rows.length, 3);
  assert.equal(pageTwo.rows.length, 1);
  assert.equal(pageTwo.page, 2);
  assert.ok(pageTwo.rows.every((row) => isVisibleVerifiedVulnerability(row.raw)));
});

test("历史事件回放不会把空置信度的 verified 漏洞重新带回列表", () => {
  const persisted = [
    createFinding({
      id: "db-visible",
      merge_key: "visible",
      fingerprint: "visible",
      is_verified: true,
      verification_progress: "verified",
      confidence: 0.91,
      timestamp: "2026-03-23T08:11:00.000Z",
    }),
  ];
  const historicalReplay = [
    createFinding({
      id: "event-hidden",
      merge_key: "hidden",
      fingerprint: "hidden",
      is_verified: true,
      verification_progress: "verified",
      confidence: null,
      timestamp: "2026-03-23T08:12:00.000Z",
    }),
  ];

  const visible = mergeRealtimeFindingsBatch(
    historicalReplay.filter((item) => isVisibleVerifiedVulnerability(item)),
    persisted.filter((item) => isVisibleVerifiedVulnerability(item)),
    { source: "db" },
  );

  assert.deepEqual(visible.map((item) => item.id), ["db-visible"]);
});
