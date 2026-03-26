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
import FindingCodeWindow from "../src/pages/AgentAudit/components/FindingCodeWindow.tsx";

globalThis.React = React;

const searchEvidence: ToolEvidencePayload = {
  renderType: "search_hits",
  commandChain: ["rg"],
  displayCommand: "rg",
  entries: [
    {
      filePath: "src/auth.ts",
      matchLine: 88,
      matchText: "if (!is_admin(user)) return",
      column: 5,
      symbolName: "guard",
      matchKind: "text",
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

const analysisSummaryEvidence: ToolEvidencePayload = {
  renderType: "analysis_summary",
  commandChain: ["smart_scan"],
  displayCommand: "smart_scan",
  entries: [
    {
      title: "Smart Scan Summary",
      summary: "Scanned 6 files and found 3 potential issues.",
      severityStats: { high: 2, medium: 1 },
      hitCount: 3,
      keyFiles: ["src/auth.ts", "src/admin.ts"],
      highlights: ["sql_injection @ src/auth.ts:88"],
      nextActions: ["继续查看关键命中上下文并确认可利用性。"],
    },
  ],
};

const outlineSummaryEvidence: ToolEvidencePayload = {
  renderType: "outline_summary",
  commandChain: ["get_file_outline"],
  displayCommand: "get_file_outline",
  entries: [
    {
      filePath: "src/parser.ts",
      fileRole: "parser-entry",
      keySymbols: ["parseXml", "buildNode"],
      imports: ["fs"],
      entrypoints: ["parseRequest"],
      riskMarkers: ["xml entity expansion"],
      frameworkHints: ["express"],
    },
  ],
};

const functionSummaryEvidence: ToolEvidencePayload = {
  renderType: "function_summary",
  commandChain: ["get_function_summary"],
  displayCommand: "get_function_summary",
  entries: [
    {
      filePath: "src/parser.ts",
      resolvedFunction: "parseXml",
      signature: "function parseXml(input: string): Node",
      purpose: "Parse XML input into an AST node tree.",
      inputs: ["input"],
      outputs: ["Node"],
      keyCalls: ["decodeEntities", "buildNode"],
      riskPoints: ["untrusted XML"],
      relatedSymbols: ["buildNode"],
    },
  ],
};

const verificationSummaryEvidence: ToolEvidencePayload = {
  renderType: "verification_summary",
  commandChain: ["verify_vulnerability"],
  displayCommand: "verify_vulnerability",
  entries: [
    {
      vulnerabilityType: "sql_injection",
      target: "http://example.test/users?id=1",
      payload: "' OR 1=1 --",
      verdict: "confirmed",
      evidence: "SQL error echoed in response",
      responseStatus: 500,
      runtimeStatus: "passed",
      error: null,
    },
  ],
};

test("ToolEvidencePreview 渲染搜索命中卡片摘要", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: searchEvidence }),
  );

  assert.match(markup, /src\/auth\.ts:88-88/);
  assert.match(markup, /is_admin/);
  assert.match(markup, /data-appearance="native-explorer"/);
  assert.doesNotMatch(markup, /rg -&gt; sed/);
  assert.doesNotMatch(markup, /1 条命中/);
  assert.doesNotMatch(markup, /命中窗口/);
});

test("ToolEvidencePreview 渲染代码窗口卡片摘要", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: codeWindowEvidence }),
  );

  assert.match(markup, /src\/auth\.ts:80-92/);
  assert.match(markup, /if \(!is_admin\(user\)\) return/);
  assert.doesNotMatch(markup, /read_file -&gt; sed/);
  assert.doesNotMatch(markup, /焦点行 88/);
  assert.doesNotMatch(markup, /代码窗口/);
});

test("ToolEvidencePreview 渲染执行证据摘要卡", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: executionEvidence }),
  );

  assert.match(markup, /Harness 执行结果:1-1/);
  assert.match(markup, /payload detected/);
  assert.doesNotMatch(markup, /run_code -&gt; python3/);
  assert.doesNotMatch(markup, /执行代码/);
});

test("ToolEvidencePreview 渲染 analysis_summary 摘要卡", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: analysisSummaryEvidence }),
  );

  assert.match(markup, /Smart Scan Summary/);
  assert.match(markup, /Scanned 6 files and found 3 potential issues/);
});

test("ToolEvidencePreview 渲染 outline_summary 摘要卡", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: outlineSummaryEvidence }),
  );

  assert.match(markup, /src\/parser\.ts/);
  assert.match(markup, /role=parser-entry/);
  assert.match(markup, /parseRequest/);
  assert.match(markup, /parseXml/);
});

test("ToolEvidencePreview 渲染 function_summary 摘要卡", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: functionSummaryEvidence }),
  );

  assert.match(markup, /src\/parser\.ts/);
  assert.match(markup, /function parseXml\(input: string\): Node/);
  assert.match(markup, /Parse XML input into an AST node tree/);
  assert.match(markup, /decodeEntities/);
});

test("ToolEvidenceDetail 渲染 execution_result 详情", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidenceDetail, {
      toolName: "run_code",
      evidence: executionEvidence,
      rawOutput: { success: true, data: "执行摘要" },
    }),
  );

  assert.match(markup, /输入与目标/);
  assert.match(markup, /关键证据/);
  assert.match(markup, /结论与判断/);
  assert.match(markup, /Harness 执行结果:1-1/);
  assert.match(markup, /cd \/tmp &amp;&amp; python3 -c/);
});

test("parseToolEvidence 支持 analysis_summary 严格解析", () => {
  const parsed = parseToolEvidence({
    metadata: {
      render_type: "analysis_summary",
      display_command: "smart_scan",
      command_chain: ["smart_scan"],
      entries: [
        {
          title: "Smart Scan Summary",
          summary: "Scanned 6 files and found 3 potential issues.",
          severity_stats: { high: 2, medium: 1 },
          hit_count: 3,
          key_files: ["src/auth.ts", "src/admin.ts"],
          highlights: ["sql_injection @ src/auth.ts:88"],
          next_actions: ["继续查看关键命中上下文并确认可利用性。"],
        },
      ],
    },
  });

  assert.equal(parsed?.renderType, "analysis_summary");
  assert.ok(parsed && parsed.renderType === "analysis_summary");
  assert.equal(parsed.entries[0]?.hitCount, 3);
});

test("ToolEvidencePreview 渲染 verification_summary 摘要", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidencePreview, { evidence: verificationSummaryEvidence }),
  );

  assert.match(markup, /sql_injection/);
  assert.match(markup, /http:\/\/example\.test\/users\?id=1/);
  assert.match(markup, /SQL error echoed in response/);
});

test("FindingCodeWindow 默认使用路径优先的单色代码窗并隐藏 title/badges，同时显示 meta 标签", () => {
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

  assert.match(markup, /src\/auth\.ts:80-81/);
  assert.match(markup, /data-appearance="native-explorer"/);
  assert.match(markup, /custom-scrollbar-dark/);
  assert.match(markup, /overflow-x-auto/);
  assert.match(markup, /whitespace-pre/);
  assert.match(markup, /max-h-\[46vh\]/);
  assert.doesNotMatch(markup, /data-display-preset="project-browser"/);
  assert.doesNotMatch(markup, /max-h-none/);
  assert.doesNotMatch(markup, /代码窗口/);
  assert.doesNotMatch(markup, /focus/);
  assert.match(markup, /typescript/);
  assert.match(markup, /80-81/);
});

test("FindingCodeWindow 为代码浏览页提供 project-browser 满高预设", () => {
  const markup = renderToStaticMarkup(
    createElement(FindingCodeWindow, {
      code: "const a = 1;\nconst b = 2;",
      filePath: "src/auth.ts",
      lineStart: 80,
      lineEnd: 81,
      focusLine: 80,
      density: "detail",
      displayPreset: "project-browser",
    }),
  );

  assert.match(markup, /data-display-preset="project-browser"/);
  assert.match(markup, /flex h-full min-h-0 flex-col/);
  assert.match(markup, /min-h-0 flex-1 max-h-none overflow-auto overflow-x-auto/);
  assert.match(markup, /title="src\/auth\.ts:80-81"/);
  assert.match(markup, /text-\[15px\] leading-6/);
  assert.match(markup, /text-\[15px\] leading-7/);
  assert.match(markup, /grid-cols-\[minmax\(56px,max-content\)_minmax\(0,1fr\)\]/);
});

test("FindingCodeWindow 支持在 demo 中切换 terminal-flat 外观", () => {
  const markup = renderToStaticMarkup(
    createElement(FindingCodeWindow, {
      code: "const a = 1;",
      filePath: "src/auth.ts",
      lineStart: 1,
      lineEnd: 1,
      appearance: "terminal-flat" as any,
    }),
  );

  assert.match(markup, /data-appearance="terminal-flat"/);
});

test("ToolEvidenceDetail 对旧协议显示不可展示提示和原始 JSON 入口", () => {
  const markup = renderToStaticMarkup(
    createElement(ToolEvidenceDetail, {
      toolName: "search_code",
      evidence: null,
      rawOutput: { success: true, data: "legacy-only" },
    }),
  );

  assert.match(markup, /无法安全提炼结构化证据，已回退原始 JSON/);
  assert.match(markup, /原始数据/);
});
