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

test("textIncludesFilter matches case-insensitive text", async () => {
  const filterModule = await importOrFail<any>(
    "../src/components/data-table/filterFns.ts",
  );

  assert.equal(filterModule.textIncludesFilter("Critical Rule", "critical"), true);
  assert.equal(filterModule.textIncludesFilter("Critical Rule", "missing"), false);
});

test("facetFilter supports single and multi values", async () => {
  const filterModule = await importOrFail<any>(
    "../src/components/data-table/filterFns.ts",
  );

  assert.equal(filterModule.facetFilter("builtin", "builtin"), true);
  assert.equal(filterModule.facetFilter("builtin", ["builtin", "upload"]), true);
  assert.equal(filterModule.facetFilter("builtin", ["json", "upload"]), false);
});

test("numberRangeFilter respects inclusive bounds", async () => {
  const filterModule = await importOrFail<any>(
    "../src/components/data-table/filterFns.ts",
  );

  assert.equal(filterModule.numberRangeFilter(10, { min: 5, max: 10 }), true);
  assert.equal(filterModule.numberRangeFilter(11, { min: 5, max: 10 }), false);
  assert.equal(filterModule.numberRangeFilter(3, { min: 5 }), false);
});
