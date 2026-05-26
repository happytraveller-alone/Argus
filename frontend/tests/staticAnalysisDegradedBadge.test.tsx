import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

test("StaticAnalysisSummaryCards renders codegraph degraded badge when extra.codegraph_unavailable=true", async () => {
  const summaryCardsModule = await import(
    "../src/pages/static-analysis/StaticAnalysisSummaryCards.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(summaryCardsModule.StaticAnalysisSummaryCards, {
      opengrepTask: {
        id: "og-1",
        project_id: "project-1",
        name: "OpenGrep scan",
        status: "completed",
        target_path: "/repo",
        total_findings: 3,
        error_count: 0,
        warning_count: 0,
        scan_duration_ms: 1200,
        files_scanned: 12,
        lines_scanned: 340,
        created_at: "2026-03-23T10:00:00.000Z",
        updated_at: "2026-03-23T10:01:00.000Z",
        extra: {
          codegraph_unavailable: true,
          codegraph_unavailable_reason: "timeout_30s",
        },
      },
      codeqlTask: null,
      joernTask: null,
      enabledEngines: ["opengrep"],
      loadingInitial: false,
    }),
  );

  assert.match(markup, /data-testid="codegraph-degraded-banner"/);
  assert.match(markup, /降级/);
  assert.match(markup, /codegraph 不可用/);
  assert.match(markup, /timeout_30s/);
});

test("StaticAnalysisSummaryCards omits degraded badge when codegraph extra is missing", async () => {
  const summaryCardsModule = await import(
    "../src/pages/static-analysis/StaticAnalysisSummaryCards.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(summaryCardsModule.StaticAnalysisSummaryCards, {
      opengrepTask: {
        id: "og-1",
        project_id: "project-1",
        name: "OpenGrep scan",
        status: "completed",
        target_path: "/repo",
        total_findings: 3,
        error_count: 0,
        warning_count: 0,
        scan_duration_ms: 1200,
        files_scanned: 12,
        lines_scanned: 340,
        created_at: "2026-03-23T10:00:00.000Z",
        updated_at: "2026-03-23T10:01:00.000Z",
      },
      codeqlTask: null,
      joernTask: null,
      enabledEngines: ["opengrep"],
      loadingInitial: false,
    }),
  );

  assert.doesNotMatch(markup, /data-testid="codegraph-degraded-banner"/);
});
