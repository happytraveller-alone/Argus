import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { ToolEvidencePayload } from "../src/pages/AgentAudit/toolEvidence.ts";
import ToolEvidencePreview from "../src/pages/AgentAudit/components/ToolEvidencePreview.tsx";
import ToolEvidenceDetail from "../src/pages/AgentAudit/components/ToolEvidenceDetail.tsx";
import FindingCodeWindow from "../src/pages/AgentAudit/components/FindingCodeWindow.tsx";

globalThis.React = React;

const searchEvidence: ToolEvidencePayload = {
  renderType: "search_hits",
  commandChain: ["rg", "sed"],
  displayCommand: "rg -> sed",
  entries: [
    {
      filePath: "src/auth.ts",
      matchLine: 88,
      matchText: "if (!is_admin(user)) return",
      windowStartLine: 87,
      windowEndLine: 89,
      language: "typescript",
      lines: [
        { lineNumber: 87, text: "function guard(user) {", kind: "context" },
        { lineNumber: 88, text: "if (!is_admin(user)) return", kind: "match" },
        { lineNumber: 89, text: "}", kind: "context" },
      ],
    },
  ],
};

const codeWindowEvidence: ToolEvidencePayload = {
  renderType: "code_window",
  commandChain: ["read_file", "sed"],
  displayCommand: "read_file -> sed",
  entries: [
    {
      filePath: "src/auth.ts",
      startLine: 80,
      endLine: 92,
      focusLine: 88,
      language: "typescript",
      lines: [
        { lineNumber: 87, text: "function guard(user) {", kind: "context" },
        { lineNumber: 88, text: "if (!is_admin(user)) return", kind: "focus" },
        { lineNumber: 89, text: "}", kind: "context" },
      ],
    },
  ],
};

const executionEvidence: ToolEvidencePayload = {
  renderType: "execution_result",
  commandChain: ["run_code", "python3"],
  displayCommand: "run_code -> python3",
  entries: [
    {
      language: "python",
      exitCode: 0,
      status: "passed",
      title: "Harness 执行结果",
      description: "验证命令注入 harness",
      runtimeImage: "vulhunter/sandbox:latest",
      executionCommand: "cd /tmp && python3 -c 'print(1)'",
      stdoutPreview: "payload detected",
      stderrPreview: "",
      artifacts: [
        { label: "镜像", value: "vulhunter/sandbox:latest" },
        { label: "退出码", value: "0" },
      ],
      code: {
        language: "python",
        lines: [
          { lineNumber: 1, text: "print('payload detected')", kind: "focus" },
        ],
      },
    },
  ],
};

test("ToolEvidencePreview 渲染搜索命中卡片摘要", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: searchEvidence }),
  );

  assert.match(markup, /rg -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:88/);
  assert.match(markup, /1 条命中/);
  assert.match(markup, /is_admin/);
  assert.match(markup, /命中/);
  assert.doesNotMatch(markup, /rounded-lg border border-cyan-500/);
});

test("ToolEvidencePreview 渲染代码窗口卡片摘要", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: codeWindowEvidence }),
  );

  assert.match(markup, /read_file -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:80-92/);
  assert.match(markup, /焦点行 88/);
  assert.match(markup, /代码窗口/);
  assert.doesNotMatch(markup, /rounded-lg border border-amber-500/);
});

test("ToolEvidencePreview 渲染执行证据摘要卡", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: executionEvidence }),
  );

  assert.match(markup, /run_code -&gt; python3/);
  assert.match(markup, /验证命令注入 harness/);
  assert.match(markup, /退出码 0/);
  assert.match(markup, /payload detected/);
  assert.match(markup, /执行代码/);
});

test("ToolEvidenceDetail 渲染 execution_result 详情", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidenceDetail, {
      toolName: "run_code",
      evidence: executionEvidence,
      rawOutput: { success: true, data: "执行摘要" },
    }),
  );

  assert.match(markup, /执行摘要/);
  assert.match(markup, /执行代码/);
  assert.match(markup, /vulhunter\/sandbox:latest/);
  assert.match(markup, /cd \/tmp &amp;&amp; python3 -c/);
});

test("FindingCodeWindow 使用紧凑 IDE 风格代码窗", () => {
  const markup = renderToStaticMarkup(
    createElement(FindingCodeWindow, {
      code: "const a = 1;\nconst b = 2;",
      filePath: "src/auth.ts",
      lineStart: 80,
      lineEnd: 81,
      focusLine: 80,
      title: "代码窗口",
      density: "compact",
      badges: ["focus"],
      meta: ["typescript", "80-81"],
    }),
  );

  assert.match(markup, /代码窗口/);
  assert.match(markup, /src\/auth\.ts:80-81/);
  assert.match(markup, /focus/);
  assert.match(markup, /overflow-x-auto/);
  assert.match(markup, /whitespace-pre/);
  assert.doesNotMatch(markup, /border-b border-border\/30/);
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
