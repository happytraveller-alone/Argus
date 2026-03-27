import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import LogEntry from "../src/pages/AgentAudit/components/LogEntry.tsx";
import type { LogItem } from "../src/pages/AgentAudit/types.ts";

globalThis.React = React;

function renderLogEntry(item: LogItem): string {
  return renderToStaticMarkup(
    createElement(LogEntry, {
      item,
      anchorId: `log-item-${item.id}`,
      onOpenDetail: () => {},
    }),
  );
}

function createToolLog(overrides: Partial<LogItem> = {}): LogItem {
  return {
    id: "tool-log-1",
    time: "00:00:01",
    type: "tool",
    title: "已完成：search_code（MCP: filesystem/search_code@stdio）",
    content: "MCP 路由：filesystem/search_code@stdio",
    tool: {
      name: "search_code",
      status: "completed",
      duration: 120,
    },
    ...overrides,
  };
}

test("LogEntry 工具行展示统一命中摘要而不是代码窗口", () => {
  const markup = renderLogEntry(
    createToolLog({
      toolEvidence: {
        renderType: "search_hits",
        commandChain: ["rg", "sed"],
        displayCommand: "rg -> sed",
        entries: [
          {
            filePath: "src/auth.ts",
            matchLine: 88,
            matchText: "if (!is_admin(user)) return",
            language: "typescript",
          },
          {
            filePath: "src/admin.ts",
            matchLine: 12,
            matchText: "return true",
            language: "typescript",
          },
        ],
      },
    }),
  );

  assert.match(markup, /search_code/);
  assert.match(markup, /2 条命中/);
  assert.doesNotMatch(markup, /if \(!is_admin\(user\)\) return/);
  assert.doesNotMatch(markup, /命中窗口/);
  assert.doesNotMatch(markup, /MCP/);
});

test("LogEntry 工具行对代码窗口展示定位摘要而不展示源码", () => {
  const markup = renderLogEntry(
    createToolLog({
      title: "已完成：read_file（MCP: filesystem/read_file@stdio）",
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
    }),
  );

  assert.match(markup, /read_file/);
  assert.match(markup, /代码窗口/);
  assert.match(markup, /src\/auth\.ts:80-92/);
  assert.doesNotMatch(markup, /function guard/);
  assert.doesNotMatch(markup, /MCP/);
});

test("LogEntry 工具行对执行结果展示退出码摘要而不展示执行片段", () => {
  const markup = renderLogEntry(
    createToolLog({
      title: "失败：sandbox_exec（MCP: filesystem\/sandbox_exec@stdio）",
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
            stdoutPreview: "uid=1000",
            stderrPreview: "permission denied",
            artifacts: [],
          },
        ],
      },
    }),
  );

  assert.match(markup, /sandbox_exec/);
  assert.match(markup, /退出码 7/);
  assert.doesNotMatch(markup, /bash -lc/);
  assert.doesNotMatch(markup, /permission denied/);
  assert.doesNotMatch(markup, /执行代码/);
});

test("LogEntry 工具行在缺少结构化证据时显示兜底摘要", () => {
  const markup = renderLogEntry(
    createToolLog({
      title: "失败：search_code（MCP: filesystem/search_code@stdio）",
      tool: {
        name: "search_code",
        status: "failed",
        duration: 120,
      },
      toolEvidence: null,
    }),
  );

  assert.match(markup, /search_code/);
  assert.match(markup, /执行失败，详情可查看原始结果/);
  assert.doesNotMatch(markup, /MCP/);
});

test("LogEntry 工具行对历史任务缺失结构化证据显示重跑提示", () => {
  const markup = renderLogEntry(
    createToolLog({
      toolEvidence: null,
      toolEvidenceMissingState: "historical_rerun_required",
    }),
  );

  assert.match(markup, /历史任务缺少结构化证据，请重跑任务/);
});

test("LogEntry 工具行对 native_v1 缺失结构化证据显示明确终态摘要", () => {
  const failedMarkup = renderLogEntry(
    createToolLog({
      tool: {
        name: "search_code",
        status: "failed",
        duration: 120,
      },
      toolEvidence: null,
      toolEvidenceMissingState: "missing_failed",
    }),
  );
  const completedMarkup = renderLogEntry(
    createToolLog({
      toolEvidence: null,
      toolEvidenceMissingState: "missing_completed",
    }),
  );

  assert.match(failedMarkup, /执行失败，未记录结构化证据/);
  assert.match(completedMarkup, /已完成，但未记录结构化证据/);
});

test("LogEntry 以五列表格化布局展示阶段列并保留查看详情操作", () => {
  const markup = renderLogEntry(
    createToolLog({
      agentName: "验证智能体",
      phaseLabel: "分析",
    }),
  );

  assert.match(markup, /grid-template-columns:72px 84px minmax\(0,1fr\) 120px 104px/);
  assert.match(markup, /分析/);
  assert.doesNotMatch(markup, /验证智能体/);
  assert.match(markup, /查看详情/);
});
