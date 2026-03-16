import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
} from "../src/pages/static-analysis/viewModel.ts";

test("phpstan findings are mapped into unified rows with LOW/MEDIUM defaults", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [],
    gitleaksFindings: [],
    banditFindings: [],
    phpstanFindings: [
      {
        id: "ps-1",
        scan_task_id: "task-ps",
        file_path: "/tmp/workdir/repo/src/Service.php",
        line: 17,
        identifier: "phpstan.return.type",
        message: "Method should return string",
        status: "open",
      },
    ],
    opengrepTaskId: "",
    gitleaksTaskId: "",
    banditTaskId: "",
    phpstanTaskId: "task-ps",
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.engine, "phpstan");
  assert.equal(rows[0]?.severity, "LOW");
  assert.equal(rows[0]?.confidence, "MEDIUM");
  assert.equal(rows[0]?.rule, "phpstan.return.type");
  assert.equal(rows[0]?.filePath, "repo/src/Service.php");
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
