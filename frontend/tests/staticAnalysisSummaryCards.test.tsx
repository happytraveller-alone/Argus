import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

test("StaticAnalysisSummaryCards keeps the initial progress label pending while tasks are still loading", async () => {
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

  assert.match(markup, /进度比例/);
  assert.match(markup, /时间/);
  assert.match(markup, /发现漏洞/);
  assert.match(markup, /任务待处理/);
  assert.doesNotMatch(markup, /0%/);
  assert.doesNotMatch(markup, /任务状态/);
  assert.doesNotMatch(markup, /使用引擎数量/);
  assert.doesNotMatch(markup, /涉及文件/);
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

  assert.match(markup, /进度比例/);
  assert.match(markup, /任务待处理/);
  assert.doesNotMatch(markup, /0%/);
  assert.doesNotMatch(markup, /Opengrep · 任务待处理/);
  assert.doesNotMatch(markup, /Gitleaks · 任务待处理/);
  assert.doesNotMatch(markup, /Opengrep · 任务完成/);
});

test("StaticAnalysisSummaryCards source keeps summary cards trimmed and tag-only", async () => {
  const source = await readFile(
    new URL("../src/pages/static-analysis/StaticAnalysisSummaryCards.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /md:grid-cols-3/);
  assert.match(source, /SUMMARY_LABEL_BADGE_CLASSNAME/);
  assert.match(source, /SUMMARY_VALUE_BADGE_CLASSNAME/);
  assert.doesNotMatch(source, /<Progress\b/);
  assert.doesNotMatch(source, /progressPercent/);
  assert.doesNotMatch(source, /任务状态/);
  assert.doesNotMatch(source, /扫描时间/);
  assert.doesNotMatch(source, /扫描漏洞数量/);
  assert.doesNotMatch(source, /使用引擎数量/);
  assert.doesNotMatch(source, /涉及文件/);
  assert.doesNotMatch(source, /totalFilesScanned/);
});

test("StaticAnalysis detail renders header tags instead of standalone summary-card row", async () => {
  const source = await readFile(
    new URL("../src/pages/StaticAnalysis.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /aria-label="静态审计概要标签"/);
  assert.match(source, /headerSummary\.projectName/);
  assert.match(source, /`\$\{Math\.round\(headerSummary\.progressPercent\)\}%`/);
  assert.match(source, /headerSummary\.durationLabel/);
  assert.match(source, /`发现漏洞 \$\{headerSummary\.totalFindings\.toLocaleString\(\)\}`/);
  assert.doesNotMatch(source, /<StaticAnalysisSummaryCards/);
  assert.doesNotMatch(source, /项目 \$\{headerSummary\.projectName/);
  assert.doesNotMatch(source, /headerSummary\.statusLabel\} \$\{Math\.round\(headerSummary\.progressPercent\)\}%/);
  assert.doesNotMatch(source, /扫描时间 \$\{headerSummary\.durationLabel/);
});
