import test from "node:test";
import assert from "node:assert/strict";

import { getProjectCardPotentialVulnerabilities } from "../src/features/projects/services/projectCardPreview.ts";

test("projectCardPreview 为潜在漏洞展示 编号+中文 的 CWE 文案", () => {
  const items = getProjectCardPotentialVulnerabilities({
    verifiedAgentFindings: [
      {
        id: "agent-1",
        task_id: "task-1",
        cwe_id: "CWE-89",
        severity: "high",
        ai_confidence: 0.96,
        confidence: 0.96,
        file_path: "src/api/user.ts",
        line_start: 18,
        created_at: "2026-03-15T00:00:00Z",
        title: "SQL 注入",
        display_title: "SQL 注入",
        vulnerability_type: "SQL Injection",
      },
    ] as unknown as Parameters<typeof getProjectCardPotentialVulnerabilities>[0]["verifiedAgentFindings"],
    limit: 1,
  });

  assert.equal(items.length, 1);
  assert.equal(items[0]?.cweLabel, "CWE-89 SQL注入");
});
