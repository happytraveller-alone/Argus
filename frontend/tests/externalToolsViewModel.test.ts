import test from "node:test";
import assert from "node:assert/strict";

import { SKILL_TOOLS_CATALOG } from "../src/pages/intelligent-scan/skillToolsCatalog.ts";
import {
  buildExternalToolListState,
  buildExternalToolRows,
} from "../src/pages/intelligent-scan/externalToolsViewModel.ts";

const rows = buildExternalToolRows({
  mcpCatalog: [],
  skillCatalog: SKILL_TOOLS_CATALOG,
  skillAvailability: {},
});

test("buildExternalToolListState 支持动态 pageSize 切片", () => {
  const listState = buildExternalToolListState({
    rows,
    searchQuery: "",
    page: 2,
    pageSize: 4,
  });

  assert.equal(listState.page, 2);
  assert.equal(listState.pageSize, 4);
  assert.equal(listState.startIndex, 4);
  assert.equal(listState.pageRows.length, 4);
  assert.equal(listState.pageRows[0]?.id, rows[4]?.id);
});

test("buildExternalToolListState 会在过滤后重新计算总数和总页数", () => {
  const listState = buildExternalToolListState({
    rows,
    searchQuery: "window",
    page: 1,
    pageSize: 3,
  });

  assert.equal(listState.totalRows, 1);
  assert.equal(listState.totalPages, 1);
  assert.equal(listState.pageRows.length, 1);
  assert.equal(listState.pageRows[0]?.id, "get_code_window");
});

test("buildExternalToolListState 会把超出范围的页码钳制到最后一页", () => {
  const listState = buildExternalToolListState({
    rows,
    searchQuery: "",
    page: 99,
    pageSize: 5,
  });

  assert.equal(listState.totalPages, Math.ceil(rows.length / 5));
  assert.equal(listState.page, listState.totalPages);
  assert.equal(listState.startIndex, (listState.totalPages - 1) * 5);
});
