import test from "node:test";
import assert from "node:assert/strict";

import { buildUnifiedFindingRows } from "../src/pages/static-analysis/viewModel.ts";

test("buildUnifiedFindingRows normalizes pmd rows", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [],
    gitleaksFindings: [],
    banditFindings: [],
    phpstanFindings: [],
    pmdFindings: [
      {
        id: "pmd-1",
        scan_task_id: "task-pmd",
        file_path: "/scan/project/src/main/java/App.java",
        begin_line: 15,
        end_line: 15,
        rule: "HardCodedCryptoKey",
        ruleset: "Security",
        priority: 2,
        message: "Hard coded key detected.",
        status: "open",
      },
    ],
    opengrepTaskId: "",
    gitleaksTaskId: "",
    banditTaskId: "",
    phpstanTaskId: "",
    pmdTaskId: "task-pmd",
  });

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.engine, "pmd");
  assert.equal(rows[0]?.filePath, "src/main/java/App.java");
  assert.equal(rows[0]?.severity, "HIGH");
  assert.equal(rows[0]?.confidence, "MEDIUM");
  assert.equal(rows[0]?.rule, "HardCodedCryptoKey · Security");
});
