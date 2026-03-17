import test from "node:test";
import assert from "node:assert/strict";

import {
  resolveAnchoredExternalToolsPage,
  resolveExternalToolsFirstVisibleIndex,
  resolveResponsiveExternalToolsLayout,
} from "../src/pages/intelligent-scan/externalToolsResponsiveLayout.ts";

test("resolveResponsiveExternalToolsLayout 根据容器尺寸计算列数、行数和分页容量", () => {
  const layout = resolveResponsiveExternalToolsLayout({
    width: 980,
    height: 620,
    minCardWidth: 300,
    minCardHeight: 240,
    gap: 16,
  });

  assert.equal(layout.columnCount, 3);
  assert.equal(layout.rowCount, 2);
  assert.equal(layout.pageSize, 6);
});

test("resolveResponsiveExternalToolsLayout 在极小容器下至少保留 1x1 容量", () => {
  const layout = resolveResponsiveExternalToolsLayout({
    width: 180,
    height: 120,
    minCardWidth: 300,
    minCardHeight: 240,
    gap: 16,
  });

  assert.equal(layout.columnCount, 1);
  assert.equal(layout.rowCount, 1);
  assert.equal(layout.pageSize, 1);
});

test("resolveExternalToolsFirstVisibleIndex 返回当前页的首个锚点索引", () => {
  assert.equal(resolveExternalToolsFirstVisibleIndex({ page: 3, pageSize: 6 }), 12);
  assert.equal(resolveExternalToolsFirstVisibleIndex({ page: 0, pageSize: 0 }), 0);
});

test("resolveAnchoredExternalToolsPage 在 pageSize 变化后按原首项锚点重算页码", () => {
  const nextPage = resolveAnchoredExternalToolsPage({
    firstVisibleIndex: 12,
    nextPageSize: 4,
    totalRows: 20,
  });

  assert.equal(nextPage, 4);
});

test("resolveAnchoredExternalToolsPage 会把页码钳制到最后一页", () => {
  const nextPage = resolveAnchoredExternalToolsPage({
    firstVisibleIndex: 18,
    nextPageSize: 10,
    totalRows: 19,
  });

  assert.equal(nextPage, 2);
});
