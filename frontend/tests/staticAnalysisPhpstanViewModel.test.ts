import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildStaticAnalysisListState } from "../src/pages/static-analysis/viewModel.ts";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("phpstan finding row mapping stays retired from the unified static-analysis view model", () => {
  const source = fs.readFileSync(
    path.join(frontendDir, "src/pages/static-analysis/viewModel.ts"),
    "utf8",
  );

  assert.doesNotMatch(source, /MinimalPhpstanFinding/);
  assert.doesNotMatch(source, /phpstanFindings:/);
});

test("phpstan rows participate in engine filtering", () => {
  const state = buildStaticAnalysisListState({
    rows: [
      {
        key: "phpstan:1",
        id: "1",
        taskId: "task-ps",
        engine: "phpstan",
        rule: "phpstan.rule",
        filePath: "src/File.php",
        line: 5,
        severity: "LOW",
        severityScore: 1,
        confidence: "MEDIUM",
        confidenceScore: 2,
        status: "open",
      },
      {
        key: "bandit:1",
        id: "2",
        taskId: "task-ba",
        engine: "bandit",
        rule: "B101",
        filePath: "src/main.py",
        line: 8,
        severity: "MEDIUM",
        severityScore: 2,
        confidence: "HIGH",
        confidenceScore: 3,
        status: "open",
      },
    ],
    engineFilter: "phpstan",
    statusFilter: "all",
    severityFilter: "all",
    confidenceFilter: "all",
    page: 1,
  });

  assert.deepEqual(state.pagedRows.map((row) => row.engine), ["phpstan"]);
});
