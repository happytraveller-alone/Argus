import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("StaticAnalysisFindingsTable renders tri-state status copy and truthiness actions", async () => {
  const tableModule = await import(
    "../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(tableModule.default, {
        currentRoute: "/static-analysis/task-1",
        loadingInitial: false,
        rows: [
          {
            key: "og-1",
            id: "finding-1",
            taskId: "task-1",
            engine: "opengrep",
            rule: "python-sqli",
            filePath: "src/app.py",
            line: 12,
            severity: "HIGH",
            severityScore: 3,
            confidence: "HIGH",
            confidenceScore: 3,
            status: "open",
          },
        ],
        state: {
          globalFilter: "",
          columnFilters: [],
          sorting: [],
          pagination: {
            pageIndex: 0,
            pageSize: 10,
          },
          columnVisibility: {},
          rowSelection: {},
          density: "comfortable",
        },
        onStateChange: () => {},
        updatingKey: null,
        onToggleStatus: () => {},
      }),
    ),
  );

  assert.match(markup, /漏洞状态/);
  assert.match(markup, /待验证/);
  assert.match(markup, /判真/);
  assert.match(markup, /判假/);
  assert.match(markup, /详情/);
  assert.doesNotMatch(markup, /处理状态/);
  assert.doesNotMatch(markup, /修复/);
  assert.doesNotMatch(markup, />验证</);
});

test("StaticAnalysisFindingsTable only disables status actions for the updating row", async () => {
  const tableModule = await import(
    "../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(tableModule.default, {
        currentRoute: "/static-analysis/task-1",
        loadingInitial: false,
        rows: [
          {
            key: "og-1",
            id: "finding-1",
            taskId: "task-1",
            engine: "opengrep",
            rule: "python-sqli",
            filePath: "src/app.py",
            line: 12,
            severity: "HIGH",
            severityScore: 3,
            confidence: "HIGH",
            confidenceScore: 3,
            status: "open",
          },
          {
            key: "gl-1",
            id: "finding-2",
            taskId: "task-2",
            engine: "gitleaks",
            rule: "hardcoded-secret",
            filePath: ".env",
            line: 1,
            severity: "HIGH",
            severityScore: 3,
            confidence: "HIGH",
            confidenceScore: 3,
            status: "verified",
          },
        ],
        state: {
          globalFilter: "",
          columnFilters: [],
          sorting: [],
          pagination: {
            pageIndex: 0,
            pageSize: 10,
          },
          columnVisibility: {},
          rowSelection: {},
          density: "comfortable",
        },
        onStateChange: () => {},
        updatingKey: "opengrep:finding-1:verified",
        onToggleStatus: () => {},
      }),
    ),
  );

  assert.equal(
    (
      markup.match(
        /<button(?=[^>]*aria-pressed="(?:true|false)")(?=[^>]*disabled="")[^>]*>/g,
      ) ?? []
    ).length,
    2,
  );
});

test("StaticAnalysisFindingsTable keeps severity and confidence columns non-hideable", async () => {
  const tableModule = await import(
    "../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx"
  );

  const columns = tableModule.getColumns({
    currentRoute: "/static-analysis/task-1",
    updatingKey: null,
    onToggleStatus: () => {},
  });

  const severityColumn = columns.find((column: { id: string }) => column.id === "severity");
  const confidenceColumn = columns.find((column: { id: string }) => column.id === "confidence");

  assert.equal(severityColumn?.enableHiding, false);
  assert.equal(confidenceColumn?.enableHiding, false);
});
