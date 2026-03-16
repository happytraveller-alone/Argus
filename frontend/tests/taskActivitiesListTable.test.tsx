import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

globalThis.React = React;

test("TaskActivitiesListTable renders agent and static defect summaries", async () => {
  const tableModule = await import(
    "../src/features/tasks/components/TaskActivitiesListTable.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(
      MemoryRouter,
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
              high: 2,
              medium: 3,
              low: 4,
              total: 10,
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
            projectName: "Demo Hybrid",
            kind: "intelligent_audit",
            sourceMode: "hybrid",
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

  assert.match(markup, /严重 1 \/ 高危 2 \/ 中危 3 \/ 低危 4/);
  assert.match(markup, /严重 0 \/ 高危 2 \/ 中危 3 \/ 低危 5/);
  assert.match(markup, /Demo Hybrid[\s\S]*?">-<\/td>/);
});
