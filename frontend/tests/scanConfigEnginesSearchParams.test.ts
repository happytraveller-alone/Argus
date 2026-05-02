import assert from "node:assert/strict";
import test from "node:test";

import { buildScanConfigEngineSearchParams } from "../src/pages/ScanConfigEngines.tsx";
import { SCAN_ENGINE_SELECTOR_OPTIONS } from "../src/shared/constants/scanEngines.ts";

test("buildScanConfigEngineSearchParams clears data-table state when switching engine tabs", () => {
  const currentParams = new URLSearchParams({
    tab: "opengrep",
    page: "3",
    pageSize: "50",
    q: "crypto",
    sort: "ruleName",
    order: "desc",
    filters: '{"source":"builtin"}',
  });

  const nextParams = buildScanConfigEngineSearchParams(currentParams, "codeql");

  assert.equal(nextParams.get("tab"), "opengrep");
  assert.equal(nextParams.get("page"), null);
  assert.equal(nextParams.get("pageSize"), null);
  assert.equal(nextParams.get("q"), null);
  assert.equal(nextParams.get("sort"), null);
  assert.equal(nextParams.get("order"), null);
  assert.equal(nextParams.get("filters"), null);
});

test("buildScanConfigEngineSearchParams preserves unrelated params", () => {
  const currentParams = new URLSearchParams({
    tab: "opengrep",
    foo: "bar",
    page: "2",
  });

  const nextParams = buildScanConfigEngineSearchParams(currentParams, "codeql");

  assert.equal(nextParams.get("tab"), "opengrep");
  assert.equal(nextParams.get("foo"), "bar");
  assert.equal(nextParams.get("page"), null);
});

test("scan engine selector options expose opengrep and codeql", () => {
  assert.deepEqual(SCAN_ENGINE_SELECTOR_OPTIONS, [
    {
      label: "opengrep",
      value: "opengrep",
    },
    {
      label: "CodeQL",
      value: "codeql",
    },
  ]);
});
