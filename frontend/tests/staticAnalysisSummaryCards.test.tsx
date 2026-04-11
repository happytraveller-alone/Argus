import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

test("StaticAnalysisSummaryCards keeps the initial zero-progress state pending while tasks are still loading", async () => {
  const summaryCardsModule = await import(
    "../src/pages/static-analysis/StaticAnalysisSummaryCards.tsx"
  );

  const markup = renderToStaticMarkup(
    createElement(summaryCardsModule.StaticAnalysisSummaryCards, {
      opengrepTask: null,
      gitleaksTask: null,
      banditTask: null,
      phpstanTask: null,
      pmdTask: null,
      enabledEngines: ["opengrep"],
      loadingInitial: true,
    }),
  );

  assert.match(markup, /0%/);
  assert.match(markup, /任务待处理/);
  assert.doesNotMatch(markup, /任务失败/);
  assert.doesNotMatch(markup, /存在失败引擎/);
});

test("StaticAnalysisSummaryCards keeps all enabled engines pending while multi-engine bootstrap is still in progress", async () => {
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
        error_count: 1,
        warning_count: 2,
        scan_duration_ms: 1200,
        files_scanned: 12,
        lines_scanned: 340,
        created_at: "2026-03-23T10:00:00.000Z",
        updated_at: "2026-03-23T10:01:00.000Z",
      },
      gitleaksTask: null,
      banditTask: null,
      phpstanTask: null,
      pmdTask: null,
      enabledEngines: ["opengrep", "gitleaks"],
      loadingInitial: true,
    }),
  );

  assert.match(markup, /0%/);
  assert.match(markup, /任务待处理/);
  assert.match(markup, /Opengrep · 任务待处理/);
  assert.match(markup, /Gitleaks · 任务待处理/);
  assert.doesNotMatch(markup, /Opengrep · 任务完成/);
});
