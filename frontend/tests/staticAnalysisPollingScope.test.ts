import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const hookPath = path.resolve(
  process.cwd(),
  "src/pages/static-analysis/useStaticAnalysisData.ts",
);

test("static analysis 运行中轮询只刷新 task/status，不重复拉取 findings", () => {
  const source = fs.readFileSync(hookPath, "utf8");

  assert.doesNotMatch(source, /await loadOpengrepFindings\(true\);/);
  assert.doesNotMatch(source, /await loadGitleaksFindings\(true\);/);
  assert.doesNotMatch(source, /await loadBanditFindings\(true\);/);
  assert.doesNotMatch(source, /await loadPhpstanFindings\(true\);/);
  assert.doesNotMatch(source, /await loadPmdFindings\(true\);/);
});
