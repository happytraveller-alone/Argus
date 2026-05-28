/**
 * Phase G tests — canonical.* test IDs
 * Covers AC1, AC2, AC3, AC4, AC5, AC6
 *
 * Uses Node built-in test runner (same pattern as agentAuditDetail.test.tsx).
 * No vitest, no @testing-library — pure unit tests against buildCanonicalDisplay.
 *
 * NOTE: buildCanonicalDisplay calls resolveCweDisplay which reads
 * cweCatalog.generated.json at import time.  That import works fine in Node
 * because tsconfig has "resolveJsonModule": true and we run via tsx.
 */
import assert from "node:assert/strict";
import test from "node:test";

// Path alias "@/" is resolved via tsconfig paths.  tsx respects tsconfig so
// this import works when tests run through `node scripts/run-node-tests.mjs`.
import {
  buildCanonicalDisplay,
  type CanonicalDisplayInput,
} from "../src/pages/finding-detail/viewModel.ts";

// ---------------------------------------------------------------------------
// Helpers — minimal finding literals
// ---------------------------------------------------------------------------

/** Minimal OpengrepFinding shape expected by buildCanonicalDisplay.
 *
 * OpengrepFinding has start_line but no end_line — so locationLabel will be
 * "src/auth.rs:42" (single line).  Use resolved_line_start for the canonical
 * line number (preferred by buildCanonicalDisplay over start_line).
 */
function makeOpengrep(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "f-001",
    scan_task_id: "t-001",
    cwe: ["CWE-79"],
    file_path: "src/auth.rs",
    start_line: 42,
    resolved_file_path: "src/auth.rs",
    resolved_line_start: 42,
    severity: "high",
    status: "open",
    ...overrides,
  };
}

/** Minimal IntelligentTaskFinding shape (camelCase as serialised by backend) */
function makeIntelligent(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    cweId: "CWE-89",
    scopeType: "file",
    resolvedFilePath: "src/db.rs",
    lineStart: 10,
    lineEnd: 15,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// canonical.opengrep.basic  (AC1)
// ---------------------------------------------------------------------------

test("canonical.opengrep.basic — all four fields are canonical for Opengrep", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeOpengrep() as never,
    projectName: "argus",
    auditType: "静态审计",
    engineLabel: "Opengrep",
  };
  const out = buildCanonicalDisplay(input);

  // typeLabel: CWE-79 → catalog hit → "CWE-79 跨站脚本"
  assert.equal(out.typeLabel, "CWE-79 跨站脚本", "typeLabel must use catalog name");

  // sourceLabel: "<project>-<auditType>-<engine>"
  assert.equal(out.sourceLabel, "argus-静态审计-Opengrep");

  // locationLabel: resolved path + single line (OpengrepFinding has no end_line field)
  assert.equal(out.locationLabel, "src/auth.rs:42");

  // name: "<project>项目<file>文件存在<typeLabel>漏洞"
  assert.equal(out.name, "argus项目src/auth.rs文件存在CWE-79 跨站脚本漏洞");
});

// ---------------------------------------------------------------------------
// canonical.opengrep.multiCwe  (AC2)
// ---------------------------------------------------------------------------

test("canonical.opengrep.multiCwe — only first CWE (CWE-79) is used; CWE-80 absent", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeOpengrep({ cwe: ["CWE-79", "CWE-80"] }) as never,
    projectName: "argus",
    auditType: "静态审计",
    engineLabel: "Opengrep",
  };
  const out = buildCanonicalDisplay(input);

  assert.equal(out.typeLabel, "CWE-79 跨站脚本", "typeLabel must use first CWE only");

  // CWE-80 must not appear anywhere in the output
  const allValues = [out.name, out.typeLabel, out.sourceLabel, out.locationLabel].join("|");
  assert.ok(!allValues.includes("CWE-80"), `CWE-80 must not appear; got: ${allValues}`);
});

// ---------------------------------------------------------------------------
// canonical.codeql.casing  (AC3)
// ---------------------------------------------------------------------------

test("canonical.codeql.casing — engine=CodeQL source contains -CodeQL (not -Codeql)", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeOpengrep() as never,
    projectName: "argus",
    auditType: "静态审计",
    engineLabel: "CodeQL",
  };
  const out = buildCanonicalDisplay(input);

  assert.ok(out.sourceLabel.includes("-CodeQL"), `sourceLabel must contain -CodeQL; got: ${out.sourceLabel}`);
  assert.ok(!out.sourceLabel.includes("-Codeql"), `sourceLabel must not contain -Codeql; got: ${out.sourceLabel}`);
});

// ---------------------------------------------------------------------------
// canonical.joern.casing  (AC3)
// ---------------------------------------------------------------------------

test("canonical.joern.casing — engine=Joern source contains -Joern (not -joern)", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeOpengrep() as never,
    projectName: "argus",
    auditType: "静态审计",
    engineLabel: "Joern",
  };
  const out = buildCanonicalDisplay(input);

  assert.ok(out.sourceLabel.includes("-Joern"), `sourceLabel must contain -Joern; got: ${out.sourceLabel}`);
  assert.ok(!out.sourceLabel.includes("-joern"), `sourceLabel must not contain -joern; got: ${out.sourceLabel}`);
});

// ---------------------------------------------------------------------------
// canonical.intelligent.file  (AC4)
// ---------------------------------------------------------------------------

test("canonical.intelligent.file — intelligent finding with file scope renders canonical fields", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeIntelligent() as never,
    projectName: "argus",
    auditType: "智能审计",
    engineLabel: "claude-3-5-sonnet",
    scopeType: "file",
  };
  const out = buildCanonicalDisplay(input);

  // CWE-89 → catalog hit → "CWE-89 SQL注入"
  assert.equal(out.typeLabel, "CWE-89 SQL注入");
  assert.equal(out.sourceLabel, "argus-智能审计-claude-3-5-sonnet");
  assert.equal(out.locationLabel, "src/db.rs:10-15");
  assert.equal(out.name, "argus项目src/db.rs文件存在CWE-89 SQL注入漏洞");
});

// ---------------------------------------------------------------------------
// canonical.intelligent.module  (AC5)
// ---------------------------------------------------------------------------

test("canonical.intelligent.module — scopeType=module uses module name not file path", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeIntelligent({ resolvedFilePath: null, lineStart: null, lineEnd: null }) as never,
    projectName: "argus",
    auditType: "智能审计",
    engineLabel: "claude-3-5-sonnet",
    scopeType: "module",
    module: "auth_service",
  };
  const out = buildCanonicalDisplay(input);

  // name must contain "auth_service模块" not "文件"
  assert.ok(out.name.includes("auth_service模块"), `name must contain auth_service模块; got: ${out.name}`);
  assert.ok(!out.name.includes("文件"), `name must not contain 文件 for module scope; got: ${out.name}`);

  // locationLabel = module name (no line range)
  assert.equal(out.locationLabel, "auth_service");
});

// ---------------------------------------------------------------------------
// canonical.intelligent.missingCwe  (AC6)
// ---------------------------------------------------------------------------

test("canonical.intelligent.missingCwe — cweId=null yields CWE未识别 fallback", () => {
  const input: CanonicalDisplayInput = {
    rawFinding: makeIntelligent({ cweId: null }) as never,
    projectName: "argus",
    auditType: "智能审计",
    engineLabel: "claude-3-5-sonnet",
    scopeType: "file",
  };
  const out = buildCanonicalDisplay(input);

  assert.equal(out.typeLabel, "CWE 未识别");
  assert.ok(out.name.includes("CWE 未识别"), `name must contain CWE 未识别; got: ${out.name}`);

  // vuln_class must NOT be substituted into typeLabel
  const finding = makeIntelligent({ cweId: null, vuln_class: "xss" }) as never;
  const out2 = buildCanonicalDisplay({ ...input, rawFinding: finding });
  assert.equal(out2.typeLabel, "CWE 未识别", "vuln_class must not substitute into typeLabel");
});
