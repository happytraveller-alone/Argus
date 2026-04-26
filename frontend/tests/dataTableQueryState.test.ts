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

test("createDefaultDataTableState returns normalized defaults", async () => {
  const queryStateModule = await importOrFail<any>(
    "../src/components/data-table/queryState.ts",
  );

  const state = queryStateModule.createDefaultDataTableState();

  assert.equal(state.globalFilter, "");
  assert.deepEqual(state.columnFilters, []);
  assert.deepEqual(state.sorting, []);
  assert.deepEqual(state.columnVisibility, {});
  assert.deepEqual(state.columnSizing, {});
  assert.deepEqual(state.rowSelection, {});
  assert.equal(state.pagination.pageIndex, 0);
  assert.equal(state.pagination.pageSize, 10);
  assert.equal(state.density, "comfortable");
});

test("setSingleColumnSorting keeps only the latest sort column", async () => {
  const queryStateModule = await importOrFail<any>(
    "../src/components/data-table/queryState.ts",
  );

  const state = queryStateModule.createDefaultDataTableState();
  const next = queryStateModule.setSingleColumnSorting(state, "severity", true);
  const finalState = queryStateModule.setSingleColumnSorting(
    next,
    "createdAt",
    false,
  );

  assert.deepEqual(next.sorting, [{ id: "severity", desc: true }]);
  assert.deepEqual(finalState.sorting, [{ id: "createdAt", desc: false }]);
});

test("resetDataTableFilters clears filters, selection and resets page index", async () => {
  const queryStateModule = await importOrFail<any>(
    "../src/components/data-table/queryState.ts",
  );

  const state = {
    ...queryStateModule.createDefaultDataTableState(),
    globalFilter: "bandit",
    columnFilters: [{ id: "source", value: "builtin" }],
    rowSelection: { "row-1": true },
    pagination: { pageIndex: 3, pageSize: 20 },
  };

  const next = queryStateModule.resetDataTableFilters(state);

  assert.equal(next.globalFilter, "");
  assert.deepEqual(next.columnFilters, []);
  assert.deepEqual(next.rowSelection, {});
  assert.equal(next.pagination.pageIndex, 0);
  assert.equal(next.pagination.pageSize, 20);
});

test("resetDataTableFilters restores reset baseline while preserving page size and density", async () => {
  const queryStateModule = await importOrFail<any>(
    "../src/components/data-table/queryState.ts",
  );

  const state = queryStateModule.createDefaultDataTableState({
    globalFilter: "bandit",
    columnFilters: [{ id: "status", value: "false" }],
    sorting: [{ id: "updatedAt", desc: true }],
    rowSelection: { "row-1": true },
    pagination: { pageIndex: 3, pageSize: 50 },
    density: "compact",
  });

  const next = queryStateModule.resetDataTableFilters(
    state,
    queryStateModule.createDefaultDataTableState({
      columnFilters: [{ id: "deletedStatus", value: "false" }],
      sorting: [{ id: "createdAt", desc: false }],
      pagination: { pageIndex: 0, pageSize: 10 },
    }),
  );

  assert.equal(next.globalFilter, "");
  assert.deepEqual(next.columnFilters, [{ id: "deletedStatus", value: "false" }]);
  assert.deepEqual(next.sorting, [{ id: "createdAt", desc: false }]);
  assert.deepEqual(next.rowSelection, {});
  assert.equal(next.pagination.pageIndex, 0);
  assert.equal(next.pagination.pageSize, 50);
  assert.equal(next.density, "compact");
});

test("areDataTableQueryStatesEqual detects matching and changed table state", async () => {
  const queryStateModule = await importOrFail<any>(
    "../src/components/data-table/queryState.ts",
  );

  const left = queryStateModule.createDefaultDataTableState({
    globalFilter: "critical",
    columnFilters: [{ id: "status", value: "open" }],
    sorting: [{ id: "severity", desc: true }],
    pagination: { pageIndex: 2, pageSize: 50 },
  });
  const same = queryStateModule.createDefaultDataTableState({
    globalFilter: "critical",
    columnFilters: [{ id: "status", value: "open" }],
    sorting: [{ id: "severity", desc: true }],
    pagination: { pageIndex: 2, pageSize: 50 },
  });
  const changed = queryStateModule.createDefaultDataTableState({
    globalFilter: "critical",
    columnFilters: [{ id: "status", value: "verified" }],
    sorting: [{ id: "severity", desc: true }],
    pagination: { pageIndex: 2, pageSize: 50 },
  });

  assert.equal(queryStateModule.areDataTableQueryStatesEqual(left, same), true);
  assert.equal(queryStateModule.areDataTableQueryStatesEqual(left, changed), false);
});
