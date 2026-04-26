import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const frontendDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const taskActivitiesListTablePath = path.join(
  frontendDir,
  "src/features/tasks/components/TaskActivitiesListTable.tsx",
);

test("TaskActivitiesListTable disables the empty DataTable toolbar above headers", () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(source, /toolbar=\{false\}/);
  assert.doesNotMatch(source, /showGlobalSearch:\s*false[\s\S]{0,220}filters:\s*\[\]/);
});

test("TaskActivitiesListTable aligns all header font sizes with the row-number header", () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(
    source,
    /const TASK_ACTIVITIES_TABLE_HEADER_CONTENT_CLASSNAME = "text-sm"/,
  );
  assert.equal(
    source.match(/meta: createTaskActivitiesTableMeta/g)?.length,
    7,
  );
});

test("TaskActivitiesListTable uses compact table width and column minimums", () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(source, /tableClassName="min-w-\[760px\]"/);
  assert.match(source, /fillContainerWidth/);
  assert.match(source, /width: 64/);
  assert.match(source, /minWidth: 132/);
  assert.match(source, /maxWidth: 156/);
  assert.match(source, /width: 132/);
  assert.doesNotMatch(source, /tableClassName="min-w-\[880px\]"/);
});

test("TaskActivitiesListTable renders severity summaries for agent tasks and keeps static summaries", async () => {
  const tableModule = await import(
    "../src/features/tasks/components/TaskActivitiesListTable.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(tableModule.default, {
        activities: [
          {
            id: "agent-1",
            projectName: "Demo Intelligent",
            kind: "intelligent_audit",
            sourceMode: "intelligent",
            status: "completed",
            agentFindingStats: {
              critical: 1,
              high: 1,
              medium: 1,
              low: 1,
              total: 4,
            },
            createdAt: "2026-03-13T10:00:00.000Z",
            startedAt: "2026-03-13T10:01:00.000Z",
            completedAt: "2026-03-13T10:05:00.000Z",
            route: "/agent-audit/agent-1",
          },
          {
            id: "static-1",
            projectName: "Demo Static",
            kind: "rule_scan",
            sourceMode: "static",
            status: "completed",
            staticFindingStats: {
              critical: 0,
              high: 2,
              medium: 3,
              low: 5,
            },
            createdAt: "2026-03-13T11:00:00.000Z",
            startedAt: "2026-03-13T11:01:00.000Z",
            completedAt: "2026-03-13T11:05:00.000Z",
            route: "/static-analysis/static-1",
          },
          {
            id: "agent-2",
            projectName: "Demo Agent",
            kind: "intelligent_audit",
            sourceMode: "intelligent",
            status: "running",
            createdAt: "2026-03-13T12:00:00.000Z",
            startedAt: "2026-03-13T12:01:00.000Z",
            completedAt: null,
            route: "/agent-audit/agent-2",
          },
        ],
        loading: false,
        nowMs: Date.parse("2026-03-13T12:05:00.000Z"),
      }),
    ),
  );

  assert.match(markup, /严重 1 \/ 高危 1 \/ 中危 1 \/ 低危 1/);
  assert.match(markup, /严重 0 \/ 高危 2 \/ 中危 3 \/ 低危 5/);
  assert.match(markup, /style="width:100%;min-width:\d+px"/);
  assert.match(markup, /style="width:156px;min-width:156px"/);
  assert.match(markup, /style="width:132px;min-width:132px"/);
  assert.match(markup, /class="block truncate text-base text-muted-foreground"/);
  assert.match(markup, /Demo Agent[\s\S]*?">-<\/td>/);
});

test("TaskActivitiesListTable merges running progress into the status column", async () => {
  const tableModule = await import(
    "../src/features/tasks/components/TaskActivitiesListTable.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(tableModule.default, {
        activities: [
          {
            id: "agent-running",
            projectName: "Demo Running",
            kind: "intelligent_audit",
            sourceMode: "intelligent",
            status: "running",
            createdAt: "2026-03-13T12:00:00.000Z",
            startedAt: "2026-03-13T12:01:00.000Z",
            completedAt: null,
            route: "/agent-audit/agent-running",
          },
          {
            id: "static-completed",
            projectName: "Demo Completed",
            kind: "rule_scan",
            sourceMode: "static",
            status: "completed",
            createdAt: "2026-03-13T11:00:00.000Z",
            startedAt: "2026-03-13T11:01:00.000Z",
            completedAt: "2026-03-13T11:05:00.000Z",
            route: "/static-analysis/static-completed",
          },
        ],
        loading: false,
        nowMs: Date.parse("2026-03-13T12:05:00.000Z"),
      }),
    ),
  );

  assert.doesNotMatch(markup, /<span>进度<\/span>/);
  assert.match(markup, /<span class="whitespace-nowrap">状态<\/span>/);
  assert.match(
    markup,
    /Demo Running[\s\S]*?<span data-slot="badge"[\s\S]*?<span>任务运行中<\/span>[\s\S]*?<span class="rounded-\[2px\][\s\S]*?>51%<\/span>/,
  );
  assert.doesNotMatch(markup, /Demo Completed[\s\S]*?任务完成[\s\S]*?100%/);
});
