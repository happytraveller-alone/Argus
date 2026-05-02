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

test("serializeDataTableUrlState omits empty values and keeps single-column sort", async () => {
  const urlStateModule = await importOrFail<any>(
    "../src/components/data-table/urlState.ts",
  );

  const params = urlStateModule.serializeDataTableUrlState({
    globalFilter: "critical",
    columnFilters: [{ id: "status", value: "open" }],
    sorting: [{ id: "severity", desc: true }],
    pagination: { pageIndex: 2, pageSize: 50 },
  });

  assert.equal(params.get("q"), "critical");
  assert.equal(params.get("sort"), "severity");
  assert.equal(params.get("order"), "desc");
  assert.equal(params.get("page"), "3");
  assert.equal(params.get("pageSize"), "50");
  assert.equal(params.get("filters"), '{"status":"open"}');
});

test("parseDataTableUrlState restores query state from search params", async () => {
  const urlStateModule = await importOrFail<any>(
    "../src/components/data-table/urlState.ts",
  );

  const state = urlStateModule.parseDataTableUrlState(
    new URLSearchParams(
      "q=critical&sort=createdAt&order=asc&page=4&pageSize=20&filters=%7B%22source%22%3A%22builtin%22%7D",
    ),
  );

  assert.equal(state.globalFilter, "critical");
  assert.deepEqual(state.sorting, [{ id: "createdAt", desc: false }]);
  assert.equal(state.pagination.pageIndex, 3);
  assert.equal(state.pagination.pageSize, 20);
  assert.deepEqual(state.columnFilters, [{ id: "source", value: "builtin" }]);
});
