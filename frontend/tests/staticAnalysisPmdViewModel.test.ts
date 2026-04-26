import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("pmd finding row mapping stays retired from the unified static-analysis view model", () => {
  const source = fs.readFileSync(
    path.join(frontendDir, "src/pages/static-analysis/viewModel.ts"),
    "utf8",
  );

  assert.doesNotMatch(source, /MinimalPmdFinding/);
  assert.doesNotMatch(source, /pmdFindings:/);
});
