import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  parseToolEvidence,
  type ToolEvidencePayload,
} from "../src/pages/AgentAudit/toolEvidence.ts";
import ToolEvidencePreview from "../src/pages/AgentAudit/components/ToolEvidencePreview.tsx";
import ToolEvidenceDetail from "../src/pages/AgentAudit/components/ToolEvidenceDetail.tsx";

globalThis.React = React;

const searchEvidenceOutput = {
  success: true,
  data: "搜索摘要",
  metadata: {
    render_type: "search_hits",
    command_chain: ["rg", "sed"],
    display_command: "rg -> sed",
    entries: [
      {
        file_path: "src/auth.ts",
        match_line: 88,
        match_text: "if (!is_admin(user)) return",
        window_start_line: 87,
        window_end_line: 89,
        language: "typescript",
        lines: [
          { line_number: 87, text: "function guard(user) {", kind: "context" },
          { line_number: 88, text: "if (!is_admin(user)) return", kind: "match" },
          { line_number: 89, text: "}", kind: "context" },
        ],
      },
    ],
  },
};

const codeWindowOutput = {
  success: true,
  data: "读取摘要",
  metadata: {
    render_type: "code_window",
    command_chain: ["read_file", "sed"],
    display_command: "read_file -> sed",
    entries: [
      {
        file_path: "src/auth.ts",
        start_line: 80,
        end_line: 92,
        focus_line: 88,
        language: "typescript",
        lines: [
          { line_number: 87, text: "function guard(user) {", kind: "context" },
          { line_number: 88, text: "if (!is_admin(user)) return", kind: "focus" },
          { line_number: 89, text: "}", kind: "context" },
        ],
      },
    ],
  },
};

test("parseToolEvidence 识别 search_code 结构化协议", () => {
  const parsed = parseToolEvidence(searchEvidenceOutput);

  assert.ok(parsed);
  assert.equal(parsed?.renderType, "search_hits");
  assert.deepEqual(parsed?.commandChain, ["rg", "sed"]);
  assert.equal(parsed?.entries[0]?.filePath, "src/auth.ts");
});

test("ToolEvidencePreview 渲染搜索命中卡片摘要", () => {
  const parsed = parseToolEvidence(searchEvidenceOutput) as ToolEvidencePayload;
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: parsed }),
  );

  assert.match(markup, /rg -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:88/);
  assert.match(markup, /1 条命中/);
  assert.match(markup, /is_admin/);
});

test("ToolEvidencePreview 渲染代码窗口卡片摘要", () => {
  const parsed = parseToolEvidence(codeWindowOutput) as ToolEvidencePayload;
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: parsed }),
  );

  assert.match(markup, /read_file -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:80-92/);
  assert.match(markup, /焦点行 88/);
});

test("ToolEvidenceDetail 对旧协议显示不可展示提示和原始 JSON 入口", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidenceDetail, {
      toolName: "search_code",
      evidence: null,
      rawOutput: { success: true, data: "legacy-only" },
    }),
  );

  assert.match(markup, /旧版工具结果协议，无法在新版证据视图中展示/);
  assert.match(markup, /查看原始 JSON/);
});
