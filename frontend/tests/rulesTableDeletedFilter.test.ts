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

test("resolveDeletedFilterValue defaults missing filters to all", async () => {
  const rulesTableStateModule = await importOrFail<any>(
    "../src/pages/rulesTableState.ts",
  );

  const value = rulesTableStateModule.resolveDeletedFilterValue({
    globalFilter: "",
    columnFilters: [],
    sorting: [],
    pagination: { pageIndex: 0, pageSize: 10 },
    columnVisibility: {},
    rowSelection: {},
    density: "comfortable",
  });

  assert.equal(value, "all");
});

test("resolveDeletedFilterValue preserves explicit deleted filter choices", async () => {
  const rulesTableStateModule = await importOrFail<any>(
    "../src/pages/rulesTableState.ts",
  );

  const value = rulesTableStateModule.resolveDeletedFilterValue({
    globalFilter: "",
    columnFilters: [{ id: "deletedStatus", value: "false" }],
    sorting: [],
    pagination: { pageIndex: 0, pageSize: 10 },
    columnVisibility: {},
    rowSelection: {},
    density: "comfortable",
  });

  assert.equal(value, "false");
});
