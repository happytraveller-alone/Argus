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

test("TaskActivitiesListTable aligns project, duration and defect body text with status badges", () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(
    source,
    /const TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME = "text-sm"/,
  );
  assert.match(
    source,
    /TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME\} font-medium text-foreground/,
  );
  assert.match(
    source,
    /TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME\} font-mono text-foreground/,
  );
  assert.match(
    source,
    /block truncate \$\{TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME\} text-muted-foreground/,
  );
});

test("TaskActivitiesListTable uses compact table width and column minimums", () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(source, /tableClassName="min-w-\[820px\]"/);
  assert.match(source, /fillContainerWidth/);
  assert.match(source, /width: 64/);
  assert.match(source, /minWidth: 132/);
  assert.match(source, /width: 128/);
  assert.match(source, /maxWidth: 136/);
  assert.match(source, /minWidth: 192/);
  assert.match(source, /maxWidth: 240/);
  assert.match(source, /align: "left"/);
  assert.match(source, /width: 176/);
  assert.doesNotMatch(source, /tableClassName="min-w-\[880px\]"/);
});

test("TaskActivitiesListTable locks ten-row pagination and scrollable task table chrome", async () => {
  const source = readFileSync(taskActivitiesListTablePath, "utf8");

  assert.match(source, /pageSize = 10/);
  assert.match(source, /pageSizeOptions: \[10, 20, 50\]/);
  assert.match(source, /className="flex h-full min-h-0 flex-col"/);
  assert.match(source, /containerClassName="min-h-0 flex-1 overflow-auto"/);
  assert.match(source, /tableClassName="min-w-\[820px\]"/);

  const tableModule = await import(
    "../src/features/tasks/components/TaskActivitiesListTable.tsx"
  );
  const activities = Array.from({ length: 12 }, (_, index) => ({
    id: `task-${index + 1}`,
    projectName: `Paged Task ${index + 1}`,
    kind: "rule_scan" as const,
    sourceMode: "static" as const,
    status: "completed" as const,
    createdAt: "2026-03-13T10:00:00.000Z",
    startedAt: "2026-03-13T10:01:00.000Z",
    completedAt: "2026-03-13T10:05:00.000Z",
    route: `/static-analysis/task-${index + 1}`,
  }));

  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(tableModule.default, {
        activities,
        loading: false,
        nowMs: Date.parse("2026-03-13T12:05:00.000Z"),
      }),
    ),
  );

  assert.match(markup, /共 12 条/);
  assert.match(markup, /Paged Task 1/);
  assert.match(markup, /Paged Task 10/);
  assert.doesNotMatch(markup, /Paged Task 11/);
  assert.doesNotMatch(markup, /Paged Task 12/);
  assert.match(markup, /min-w-\[820px\]/);
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
            id: "static-zero",
            projectName: "Zero Static",
            kind: "rule_scan",
            sourceMode: "static",
            status: "completed",
            staticFindingStats: {
              critical: 0,
              high: 0,
              medium: 0,
              low: 0,
            },
            createdAt: "2026-03-13T11:30:00.000Z",
            startedAt: "2026-03-13T11:31:00.000Z",
            completedAt: "2026-03-13T11:35:00.000Z",
            route: "/static-analysis/static-zero",
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
  assert.match(markup, /高危 2 \/ 中危 3 \/ 低危 5/);
  assert.doesNotMatch(markup, /严重 0/);
  assert.doesNotMatch(markup, /高危 0/);
  assert.doesNotMatch(markup, /中危 0/);
  assert.doesNotMatch(markup, /低危 0/);
  assert.match(markup, /style="width:100%;min-width:\d+px"/);
  assert.match(markup, /style="width:136px;min-width:136px;max-width:136px"/);
  assert.match(markup, /style="width:240px;min-width:240px;max-width:240px"/);
  assert.match(markup, /style="width:176px;min-width:176px"/);
  assert.match(markup, /data-align="left"/);
  assert.match(markup, /class="text-sm font-medium text-foreground"/);
  assert.match(markup, /class="text-sm font-mono text-foreground"/);
  assert.match(markup, /class="block truncate text-sm text-muted-foreground"/);
  assert.match(markup, /Zero Static[\s\S]*?">-<\/td>/);
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


test("TaskActivitiesListTable shows row-level cancel only for cancellable tasks", async () => {
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
            projectName: "Running Agent",
            kind: "intelligent_audit",
            sourceMode: "intelligent",
            status: "running",
            createdAt: "2026-03-13T12:00:00.000Z",
            startedAt: "2026-03-13T12:01:00.000Z",
            completedAt: null,
            route: "/agent-audit/agent-running",
            cancelTarget: { mode: "intelligent", taskId: "agent-running" },
          },
          {
            id: "static-completed",
            projectName: "Completed Static",
            kind: "rule_scan",
            sourceMode: "static",
            status: "completed",
            createdAt: "2026-03-13T11:00:00.000Z",
            startedAt: "2026-03-13T11:01:00.000Z",
            completedAt: "2026-03-13T11:05:00.000Z",
            route: "/static-analysis/static-completed",
            cancelTarget: { mode: "static", engine: "opengrep", taskId: "static-completed" },
          },
        ],
        loading: false,
        nowMs: Date.parse("2026-03-13T12:05:00.000Z"),
      }),
    ),
  );

  assert.match(markup, /Running Agent[\s\S]*?详情[\s\S]*?中止/);
  assert.doesNotMatch(markup, /Completed Static[\s\S]*?中止/);

  const source = readFileSync(taskActivitiesListTablePath, "utf8");
  assert.match(source, /<AlertDialog/);
  assert.match(source, /确认中止任务/);
  assert.match(source, /onCancelActivity/);
});
