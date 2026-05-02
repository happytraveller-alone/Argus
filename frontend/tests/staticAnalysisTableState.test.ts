import test from "node:test";
import assert from "node:assert/strict";

async function importOrFail<TModule = Record<string, unknown>>(
  relativePath: string,
): Promise<TModule> {
  try {
    return (await import(relativePath)) as TModule;
  } catch (error) {
    assert.fail(
      `expected helper module ${relativePath} to exist: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
}

test("createStaticAnalysisInitialTableState applies default sorting, pagination, and hidden columns", async () => {
  const tableStateModule = await importOrFail<any>(
    "../src/pages/static-analysis/tableState.ts",
  );

  const state = tableStateModule.createStaticAnalysisInitialTableState({
    globalFilter: "",
    columnFilters: [],
    sorting: [],
    pagination: { pageIndex: 2, pageSize: 0 },
    columnVisibility: {
      engine: true,
    },
    rowSelection: {},
    density: "comfortable",
  });

  assert.deepEqual(state.sorting, [{ id: "severity", desc: true }]);
  assert.equal(state.pagination.pageIndex, 2);
  assert.equal(state.pagination.pageSize, 15);
  assert.equal(state.columnVisibility.location, false);
  assert.equal(state.columnVisibility.engine, true);
});

test("createStaticAnalysisInitialTableState can build CodeQL detail defaults without URL state", async () => {
  const tableStateModule = await importOrFail<any>(
    "../src/pages/static-analysis/tableState.ts",
  );

  const state = tableStateModule.createStaticAnalysisInitialTableState();

  assert.deepEqual(state.sorting, [{ id: "severity", desc: true }]);
  assert.equal(state.pagination.pageIndex, 0);
  assert.equal(state.pagination.pageSize, 15);
  assert.equal(state.columnVisibility.location, false);
});

test("createStaticAnalysisInitialTableState keeps explicit sorting and page size", async () => {
  const tableStateModule = await importOrFail<any>(
    "../src/pages/static-analysis/tableState.ts",
  );

  const state = tableStateModule.createStaticAnalysisInitialTableState({
    globalFilter: "",
    columnFilters: [],
    sorting: [{ id: "confidence", desc: false }],
    pagination: { pageIndex: 1, pageSize: 50 },
    columnVisibility: {},
    rowSelection: {},
    density: "comfortable",
  });

  assert.deepEqual(state.sorting, [{ id: "confidence", desc: false }]);
  assert.equal(state.pagination.pageIndex, 1);
  assert.equal(state.pagination.pageSize, 50);
});

test("resolveStaticAnalysisTableState keeps the default hidden location column when URL state omits visibility", async () => {
  const tableStateModule = await importOrFail<any>(
    "../src/pages/static-analysis/tableState.ts",
  );

  const state = tableStateModule.resolveStaticAnalysisTableState({
    globalFilter: "",
    columnFilters: [],
    sorting: [],
    pagination: { pageIndex: 0, pageSize: 0 },
    columnVisibility: {},
    rowSelection: {},
    density: "comfortable",
  });

  assert.deepEqual(state.sorting, [{ id: "severity", desc: true }]);
  assert.equal(state.pagination.pageSize, 15);
  assert.equal(state.columnVisibility.location, false);
});
