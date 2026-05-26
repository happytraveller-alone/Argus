import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
  getStaticAnalysisConfidenceSourceLabel,
  getStaticAnalysisDismissalCategoryBadgeClass,
  getStaticAnalysisDismissalCategoryLabel,
  parseDismissalEvidence,
  resolveCodegraphDegradedInfo,
} from "../src/pages/static-analysis/viewModel.ts";

test("parseDismissalEvidence accepts camelCase backend payload", () => {
  const parsed = parseDismissalEvidence({
    category: "sanitized",
    confidenceSource: "rule_matched",
    pathPattern: "tests/",
    sanitizerSymbols: ["psycopg2.sql.SQL", "html.escape"],
    rationale: "Path matches tests/ prefix",
  });
  assert.ok(parsed);
  assert.equal(parsed.category, "sanitized");
  assert.equal(parsed.confidenceSource, "rule_matched");
  assert.equal(parsed.pathPattern, "tests/");
  assert.deepEqual(parsed.sanitizerSymbols, [
    "psycopg2.sql.SQL",
    "html.escape",
  ]);
  assert.equal(parsed.rationale, "Path matches tests/ prefix");
});

test("parseDismissalEvidence also accepts snake_case payload", () => {
  const parsed = parseDismissalEvidence({
    category: "test",
    confidence_source: "path_pattern",
    path_pattern: "vendor/",
    sanitizer_symbols: ["foo"],
  });
  assert.ok(parsed);
  assert.equal(parsed.category, "test");
  assert.equal(parsed.confidenceSource, "path_pattern");
  assert.equal(parsed.pathPattern, "vendor/");
  assert.deepEqual(parsed.sanitizerSymbols, ["foo"]);
  assert.equal(parsed.rationale, null);
});

test("parseDismissalEvidence returns null for malformed payload", () => {
  assert.equal(parseDismissalEvidence(null), null);
  assert.equal(parseDismissalEvidence(undefined), null);
  assert.equal(parseDismissalEvidence("not-an-object"), null);
  assert.equal(
    parseDismissalEvidence({ category: "unknown", confidenceSource: "rule_matched" }),
    null,
  );
  assert.equal(
    parseDismissalEvidence({ category: "real", confidenceSource: "bogus" }),
    null,
  );
});

test("buildUnifiedFindingRows surfaces dismissalEvidence on each row", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [
      {
        id: "og-1",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "HIGH",
        file_path: "src/app.py",
        start_line: 1,
        status: "open",
        rule_name: "py-sqli",
        dismissalEvidence: {
          category: "real",
          confidenceSource: "rule_matched",
          sanitizerSymbols: [],
        },
      },
      {
        id: "og-legacy",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "HIGH",
        file_path: "src/legacy.py",
        start_line: 2,
        status: "open",
        rule_name: "py-sqli",
        // No dismissalEvidence → legacy / unprocessed finding.
      },
    ],
    opengrepTaskId: "task-og",
  });

  const realRow = rows.find((row) => row.id === "og-1");
  const legacyRow = rows.find((row) => row.id === "og-legacy");
  assert.ok(realRow);
  assert.ok(legacyRow);
  assert.equal(realRow.dismissalCategory, "real");
  assert.equal(realRow.dismissalEvidence?.confidenceSource, "rule_matched");
  assert.equal(legacyRow.dismissalCategory, null);
  assert.equal(legacyRow.dismissalEvidence, null);
});

test("dismissal category filter narrows rows to only the selected bucket", () => {
  const rows = buildUnifiedFindingRows({
    opengrepFindings: [
      {
        id: "og-real",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "HIGH",
        file_path: "src/app.py",
        start_line: 1,
        status: "open",
        rule_name: "py-sqli",
        dismissalEvidence: {
          category: "real",
          confidenceSource: "rule_matched",
        },
      },
      {
        id: "og-sanitized",
        scan_task_id: "task-og",
        severity: "HIGH",
        confidence: "HIGH",
        file_path: "src/safe.py",
        start_line: 2,
        status: "open",
        rule_name: "py-sqli",
        dismissalEvidence: {
          category: "sanitized",
          confidenceSource: "rule_matched",
        },
      },
    ],
    opengrepTaskId: "task-og",
  });

  const sanitizedOnly = buildStaticAnalysisListState({
    rows,
    engineFilter: "all",
    statusFilter: "all",
    severityFilter: "all",
    confidenceFilter: "all",
    dismissalCategoryFilter: "sanitized",
    page: 1,
  });
  assert.equal(sanitizedOnly.totalRows, 1);
  assert.equal(sanitizedOnly.filteredRows[0]?.id, "og-sanitized");

  const realOnly = buildStaticAnalysisListState({
    rows,
    engineFilter: "all",
    statusFilter: "all",
    severityFilter: "all",
    confidenceFilter: "all",
    dismissalCategoryFilter: "real",
    page: 1,
  });
  assert.equal(realOnly.totalRows, 1);
  assert.equal(realOnly.filteredRows[0]?.id, "og-real");

  const noFilter = buildStaticAnalysisListState({
    rows,
    engineFilter: "all",
    statusFilter: "all",
    severityFilter: "all",
    confidenceFilter: "all",
    page: 1,
  });
  assert.equal(noFilter.totalRows, 2);
});

test("category labels and badge classes are stable per bucket", () => {
  assert.equal(getStaticAnalysisDismissalCategoryLabel("real"), "真实");
  assert.equal(getStaticAnalysisDismissalCategoryLabel("sanitized"), "已净化");
  assert.equal(getStaticAnalysisDismissalCategoryLabel("test"), "测试代码");
  assert.equal(getStaticAnalysisDismissalCategoryLabel("vendor"), "第三方依赖");
  assert.match(
    getStaticAnalysisDismissalCategoryBadgeClass("real"),
    /rose/,
  );
  assert.match(
    getStaticAnalysisDismissalCategoryBadgeClass("sanitized"),
    /emerald/,
  );
  assert.equal(
    getStaticAnalysisConfidenceSourceLabel("rule_matched"),
    "规则命中",
  );
  assert.equal(
    getStaticAnalysisConfidenceSourceLabel("llm_inferred"),
    "LLM 推断",
  );
});

test("resolveCodegraphDegradedInfo flags tasks that report unavailable=true", () => {
  const degraded = resolveCodegraphDegradedInfo({
    opengrepTask: {
      id: "t1",
      project_id: "p1",
      status: "completed",
      created_at: "2026-01-01T00:00:00Z",
      extra: {
        codegraph_unavailable: true,
        codegraph_unavailable_reason: "timeout_30s",
      },
    },
    codeqlTask: null,
    joernTask: null,
  });
  assert.equal(degraded.unavailable, true);
  assert.equal(degraded.reason, "timeout_30s");

  const healthy = resolveCodegraphDegradedInfo({
    opengrepTask: {
      id: "t2",
      project_id: "p2",
      status: "completed",
      created_at: "2026-01-01T00:00:00Z",
    },
    codeqlTask: null,
    joernTask: null,
  });
  assert.equal(healthy.unavailable, false);
  assert.equal(healthy.reason, null);

  const empty = resolveCodegraphDegradedInfo({});
  assert.equal(empty.unavailable, false);
});
