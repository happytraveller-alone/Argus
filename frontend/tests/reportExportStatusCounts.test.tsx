import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EnhancedStatsPanel } from "../src/pages/AgentAudit/report-export/components.tsx";

globalThis.React = React;

function renderPanel(props: {
  task: Record<string, unknown>;
  findings?: Array<Record<string, unknown>>;
}) {
  return renderToStaticMarkup(
    createElement(EnhancedStatsPanel, {
      task: props.task,
      findings: props.findings,
    }),
  );
}

test("EnhancedStatsPanel 优先使用当前 findings 计算导出状态统计", () => {
  const markup = renderPanel({
    task: {
      verified_count: 1,
      false_positive_count: 1,
      findings_count: 2,
      security_score: 76,
      defect_summary: {
        total_count: 3,
        status_counts: {
          pending: 1,
          verified: 1,
          false_positive: 1,
        },
      },
    },
    findings: [
      {
        id: "verified-1",
        severity: "high",
        status: "verified",
        is_verified: true,
        verification_progress: "verified",
      },
      {
        id: "pending-1",
        severity: "medium",
        status: "needs_review",
        is_verified: false,
        verification_progress: "pending",
      },
      {
        id: "fp-1",
        severity: "low",
        status: "false_positive",
        is_verified: false,
        authenticity: "false_positive",
      },
    ],
  });

  assert.match(markup, /待确认/);
  assert.match(markup, /确报/);
  assert.match(markup, /误报/);
  assert.match(markup, />1<\/span>/);
});

test("EnhancedStatsPanel 在无 findings 时回退到 defect_summary.status_counts", () => {
  const markup = renderPanel({
    task: {
      verified_count: 7,
      false_positive_count: 6,
      findings_count: 5,
      security_score: 81,
      defect_summary: {
        status_counts: {
          pending: 2,
          verified: 3,
          false_positive: 1,
        },
      },
    },
    findings: [],
  });

  assert.match(markup, /待确认[\s\S]*?>2<\/span>/);
  assert.match(markup, /确报[\s\S]*?>3<\/span>/);
  assert.match(markup, /误报[\s\S]*?>1<\/span>/);
});

test("EnhancedStatsPanel 在 findings 非全量时回退到 task summary 而不是误用子集统计", () => {
  const markup = renderPanel({
    task: {
      verified_count: 7,
      false_positive_count: 6,
      findings_count: 5,
      security_score: 81,
      defect_summary: {
        total_count: 12,
        status_counts: {
          pending: 2,
          verified: 3,
          false_positive: 1,
        },
      },
    },
    findings: [
      {
        id: "verified-1",
        severity: "high",
        status: "verified",
        is_verified: true,
        verification_progress: "verified",
      },
    ],
  });

  assert.match(markup, /待确认[\s\S]*?>2<\/span>/);
  assert.match(markup, /确报[\s\S]*?>3<\/span>/);
  assert.match(markup, /误报[\s\S]*?>1<\/span>/);
});
