import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AuditDetailContent } from "../src/pages/AgentAudit/components/AuditDetailDialog.tsx";
import type { LogItem } from "../src/pages/AgentAudit/types.ts";

globalThis.React = React;

function createBaseLogItem(): LogItem {
  return {
    id: "tool-log-1",
    time: "00:00:01",
    type: "tool",
    title: "已完成：search_code",
    tool: {
      name: "search_code",
      status: "completed",
      duration: 120,
    },
    detail: {
      tool_output: {
        success: true,
      },
    },
  };
}

test("AuditDetailContent 渲染 search_code 结构化证据详情", () => {
  const logItem: LogItem = {
    ...createBaseLogItem(),
    toolEvidence: {
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
    },
  };

  const markup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem,
    }),
  );

  assert.match(markup, /结构化证据/);
  assert.match(markup, /rg -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:87-89/);
  assert.match(markup, /概览/);
  assert.doesNotMatch(markup, /已完成：search_code/);
  assert.doesNotMatch(markup, /命中窗口/);
  assert.doesNotMatch(markup, /<summary[^>]*>原始事件元数据<\/summary>/);
});

test("AuditDetailContent 渲染 read_file 结构化代码窗口详情", () => {
  const logItem: LogItem = {
    ...createBaseLogItem(),
    title: "已完成：read_file",
    tool: {
      name: "read_file",
      status: "completed",
      duration: 80,
    },
    toolEvidence: {
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
    },
  };

  const markup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem,
    }),
  );

  assert.match(markup, /结构化证据/);
  assert.match(markup, /read_file -&gt; sed/);
  assert.match(markup, /src\/auth\.ts:80-92/);
  assert.match(markup, /工具状态/);
  assert.doesNotMatch(markup, /代码窗口/);
});

test("AuditDetailContent 渲染 extract_function 与 run_code / sandbox_exec 结构化证据详情", () => {
  const extractFunctionLog: LogItem = {
    ...createBaseLogItem(),
    title: "已完成：extract_function",
    tool: {
      name: "extract_function",
      status: "completed",
      duration: 45,
    },
    toolEvidence: {
      renderType: "code_window",
      commandChain: ["extract_function"],
      displayCommand: "extract_function",
      entries: [
        {
          filePath: "src/auth.ts",
          startLine: 12,
          endLine: 18,
          focusLine: 12,
          language: "typescript",
          title: "函数提取",
          symbolName: "guard",
          symbolKind: "function",
          lines: [
            { lineNumber: 12, text: "function guard(user) {", kind: "focus" },
            { lineNumber: 13, text: "  if (!user) return false", kind: "context" },
            { lineNumber: 14, text: "  return isAdmin(user)", kind: "context" },
          ],
        },
      ],
    },
  };
  const runCodeLog: LogItem = {
    ...createBaseLogItem(),
    title: "已完成：run_code",
    tool: {
      name: "run_code",
      status: "completed",
      duration: 210,
    },
    toolEvidence: {
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
    },
  };
  const sandboxExecLog: LogItem = {
    ...createBaseLogItem(),
    title: "失败：sandbox_exec",
    tool: {
      name: "sandbox_exec",
      status: "failed",
      duration: 90,
    },
    toolEvidence: {
      renderType: "execution_result",
      commandChain: ["sandbox_exec", "bash"],
      displayCommand: "sandbox_exec -> bash",
      entries: [
        {
          exitCode: 7,
          status: "failed",
          title: "沙箱命令执行",
          executionCommand: "bash -lc 'id'",
          runtimeImage: "vulhunter/sandbox:latest",
          stdoutPreview: "uid=1000",
          stderrPreview: "permission denied",
          artifacts: [
            { label: "stderr", value: "permission denied" },
          ],
        },
      ],
    },
  };

  const extractMarkup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem: extractFunctionLog,
    }),
  );
  const runCodeMarkup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem: runCodeLog,
    }),
  );
  const sandboxExecMarkup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem: sandboxExecLog,
    }),
  );

  assert.match(extractMarkup, /extract_function/);
  assert.match(extractMarkup, /guard/);
  assert.match(runCodeMarkup, /run_code -&gt; python3/);
  assert.match(runCodeMarkup, /验证命令注入 harness/);
  assert.match(sandboxExecMarkup, /sandbox_exec -&gt; bash/);
  assert.match(sandboxExecMarkup, /permission denied/);
});

test("AuditDetailContent 将原始事件元数据默认折叠", () => {
  const logItem: LogItem = {
    ...createBaseLogItem(),
    content: "legacy",
    detail: {
      tool_output: { success: true },
      metadata: { hello: "world" },
    },
    toolEvidence: {
      renderType: "code_window",
      commandChain: ["read_file", "sed"],
      displayCommand: "read_file -> sed",
      entries: [
        {
          filePath: "src/auth.ts",
          startLine: 1,
          endLine: 2,
          focusLine: 1,
          language: "typescript",
          lines: [
            { lineNumber: 1, text: "const a = 1", kind: "focus" },
            { lineNumber: 2, text: "const b = 2", kind: "context" },
          ],
        },
      ],
    },
  };

  const markup = renderToStaticMarkup(
    createElement(AuditDetailContent, {
      detailType: "log",
      logItem,
    }),
  );

  assert.match(markup, /原始事件元数据/);
  assert.match(markup, /查看原始事件元数据/);
  assert.doesNotMatch(markup, /<details[^>]*open/);
});
