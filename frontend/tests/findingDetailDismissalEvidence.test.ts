import test from "node:test";
import assert from "node:assert/strict";

import {
  buildFindingDetailDismissalEvidence,
  buildOpengrepFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";
import { sanitizerReferenceUrl } from "../src/shared/security/sanitizerReference.ts";
import type { OpengrepFinding } from "../src/shared/api/opengrep.ts";

test("buildFindingDetailDismissalEvidence maps category and confidence labels", () => {
  const evidence = buildFindingDetailDismissalEvidence({
    category: "sanitized",
    confidenceSource: "rule_matched",
    pathPattern: "tests/",
    sanitizerSymbols: ["psycopg2.sql.SQL", "unknown.symbol"],
    rationale: "Matched SoT rule",
  });
  assert.ok(evidence);
  assert.equal(evidence.categoryLabel, "已净化");
  assert.equal(evidence.confidenceSourceLabel, "规则命中");
  assert.equal(evidence.pathPattern, "tests/");
  assert.equal(evidence.sanitizerSymbols.length, 2);
  const known = evidence.sanitizerSymbols.find(
    (chip) => chip.symbol === "psycopg2.sql.SQL",
  );
  const unknown = evidence.sanitizerSymbols.find(
    (chip) => chip.symbol === "unknown.symbol",
  );
  assert.ok(known);
  assert.match(known.url ?? "", /psycopg\.org/);
  assert.ok(unknown);
  assert.equal(unknown.url, null);
  assert.equal(evidence.rationale, "Matched SoT rule");
});

test("buildFindingDetailDismissalEvidence returns null for null/undefined input", () => {
  assert.equal(buildFindingDetailDismissalEvidence(null), null);
  assert.equal(buildFindingDetailDismissalEvidence(undefined), null);
});

test("sanitizerReferenceUrl returns mappings for well-known symbols and null otherwise", () => {
  assert.match(
    sanitizerReferenceUrl("psycopg2.sql.SQL") ?? "",
    /psycopg\.org/,
  );
  assert.match(
    sanitizerReferenceUrl("html.escape") ?? "",
    /docs\.python\.org/,
  );
  assert.match(
    sanitizerReferenceUrl("DOMPurify.sanitize") ?? "",
    /DOMPurify/,
  );
  assert.equal(sanitizerReferenceUrl("not.a.known.symbol"), null);
  assert.equal(sanitizerReferenceUrl(""), null);
});

test("buildOpengrepFindingDetailModel surfaces dismissalEvidence on the model", () => {
  const finding: OpengrepFinding = {
    id: "og-1",
    scan_task_id: "task-og",
    rule: {},
    rule_name: "py-sqli",
    file_path: "src/app.py",
    start_line: 12,
    severity: "HIGH",
    status: "open",
    confidence: "HIGH",
    dismissalEvidence: {
      category: "real",
      confidenceSource: "llm_inferred",
      pathPattern: null,
      sanitizerSymbols: ["html.escape"],
      rationale: "Hunt Pass 2 confirms reachability",
    },
  };
  const model = buildOpengrepFindingDetailModel({
    finding,
    taskId: "task-og",
    findingId: finding.id,
  });
  assert.ok(model.dismissalEvidence);
  assert.equal(model.dismissalEvidence.categoryLabel, "真实");
  assert.equal(model.dismissalEvidence.confidenceSourceLabel, "LLM 推断");
  assert.equal(model.dismissalEvidence.rationale, "Hunt Pass 2 confirms reachability");
  assert.equal(model.dismissalEvidence.sanitizerSymbols.length, 1);
});

test("buildOpengrepFindingDetailModel sets dismissalEvidence to null for legacy findings", () => {
  const finding: OpengrepFinding = {
    id: "og-2",
    scan_task_id: "task-og",
    rule: {},
    rule_name: "py-sqli",
    file_path: "src/legacy.py",
    start_line: 12,
    severity: "HIGH",
    status: "open",
    confidence: "HIGH",
  };
  const model = buildOpengrepFindingDetailModel({
    finding,
    taskId: "task-og",
    findingId: finding.id,
  });
  assert.equal(model.dismissalEvidence, null);
});
