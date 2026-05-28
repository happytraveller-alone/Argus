/**
 * Phase G frontend tests — G-F1 through G-F10
 * Covers ACs 6, 7, 8, 9, 10, 11
 *
 * Uses Node built-in test runner (same pattern as viewModelCanonical.test.ts).
 * Run via: npm run test:node from frontend/
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";
import type { AgentFinding } from "../src/shared/api/agentTasks.ts";

// ---------------------------------------------------------------------------
// Minimal base finding — mandatory fields for AgentFinding
// code_snippet is non-empty so the primary code module exists and evidence/hop
// modules are appended after it by buildAgentFindingCodeViews.
// ---------------------------------------------------------------------------

const baseFinding: AgentFinding = {
  id: "f1",
  task_id: "t1",
  code_snippet: "// base",
};

// Helper to extract the narrative section body (content goes into
// finding.description_markdown when non-empty, or body when empty).
function sectionText(section: { body?: string | null; finding?: { description_markdown?: string | null } | null } | undefined): string {
  return section?.finding?.description_markdown ?? section?.body ?? "";
}

// ---------------------------------------------------------------------------
// G-F1: evidence snippet module title when file+lineRange present  (AC6)
// ---------------------------------------------------------------------------

test("G-F1: evidence snippet module title contains file:lineRange", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidenceCodeSnippets: [
      { file: "src/a.rs", lineStart: 10, lineEnd: 15, code: "fn foo(){}" },
    ],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const evidenceModules = model.codeSections.filter((s) =>
    s.title.startsWith("漏洞证据"),
  );
  assert.ok(evidenceModules.length >= 1, "expected at least one 漏洞证据 module");
  assert.match(evidenceModules[0]!.title, /漏洞证据 · src\/a\.rs:10-15/);
});

// ---------------------------------------------------------------------------
// G-F2: evidence snippet module falls back to #N when file is null  (AC6)
// ---------------------------------------------------------------------------

test("G-F2: evidence snippet module fallback title 漏洞证据 #N when file null", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidenceCodeSnippets: [
      { file: null, lineStart: null, lineEnd: null, code: "raw" },
    ],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const evidenceModules = model.codeSections.filter((s) =>
    s.title.startsWith("漏洞证据"),
  );
  assert.ok(evidenceModules.length >= 1);
  assert.match(evidenceModules[0]!.title, /漏洞证据 #1/);
});

// ---------------------------------------------------------------------------
// G-F3: chain hop module full title  (AC7)
// ---------------------------------------------------------------------------

test("G-F3: chain hop module full title 可达性 hop {i+1} · {fn} @ {file}:{line}", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    reachabilityChain: [
      { file: "src/x.rs", line: 42, function: "handler", snippet: "..." },
    ],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const hopModules = model.codeSections.filter((s) =>
    s.title.startsWith("可达性 hop"),
  );
  assert.equal(hopModules.length, 1);
  assert.match(hopModules[0]!.title, /可达性 hop 1 · handler @ src\/x\.rs:42/);
});

// ---------------------------------------------------------------------------
// G-F4: chain hop with no snippet → code is empty string  (AC7)
// ---------------------------------------------------------------------------

test("G-F4: chain hop missing snippet → code is empty string", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    reachabilityChain: [
      { file: "src/x.rs", line: 42, function: "handler" },
    ],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const hopModules = model.codeSections.filter((s) =>
    s.title.startsWith("可达性 hop"),
  );
  assert.ok(hopModules.length >= 1);
  assert.equal(hopModules[0]!.code, "");
});

// ---------------------------------------------------------------------------
// G-F5: chain modules appended AFTER evidence modules  (AC6+AC7)
// baseFinding has code_snippet so the primary module exists and both groups
// are appended after it.
// ---------------------------------------------------------------------------

test("G-F5: chain modules appended AFTER evidence modules in codeSections", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidenceCodeSnippets: [
      { file: null, lineStart: null, lineEnd: null, code: "a" },
    ],
    reachabilityChain: [
      { file: null, line: null, function: "x", snippet: null },
    ],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const titles = model.codeSections.map((s) => s.title);
  const evidenceIdx = titles.findIndex((t) => t.startsWith("漏洞证据"));
  const hopIdx = titles.findIndex((t) => t.startsWith("可达性 hop"));
  assert.ok(evidenceIdx >= 0, "evidence module must exist");
  assert.ok(hopIdx >= 0, "hop module must exist");
  assert.ok(evidenceIdx < hopIdx, "evidence must precede hop in codeSections");
});

// ---------------------------------------------------------------------------
// G-F6: 根因说明 body has no triple-backtick fences AND no path tokens  (AC8)
// ---------------------------------------------------------------------------

test("G-F6: 根因说明 body strips fences and path tokens", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidenceProse:
      "正常描述。代码中 src/x.rs:42 触发漏洞。```rust\nfn boom(){}\n```",
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const rootCauseSection = model.narrativeSections.find(
    (s) => s.title === "根因说明",
  );
  const body = sectionText(rootCauseSection);
  assert.doesNotMatch(body, /```/);
  assert.doesNotMatch(body, /\b[\w./-]+(?:\.\w{1,8}):\d+\b/);
});

// ---------------------------------------------------------------------------
// G-F7: path-sentence stripped; clean sentence retained  (AC10)
// ---------------------------------------------------------------------------

test("G-F7: path-sentence stripped, clean sentence retained in 根因说明", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidenceProse:
      "代码 src/auth.rs:42 中存在 SQL 注入。漏洞由于未做参数化处理。",
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const rootCauseSection = model.narrativeSections.find(
    (s) => s.title === "根因说明",
  );
  const body = sectionText(rootCauseSection);
  assert.match(body, /漏洞由于未做参数化处理/);
  assert.doesNotMatch(body, /src\/auth\.rs:42/);
});

// ---------------------------------------------------------------------------
// G-F8: 验证结论 chain-pointer paragraph present when chain non-empty  (AC9)
// ---------------------------------------------------------------------------

test("G-F8: 验证结论 chain-pointer paragraph present when chain non-empty", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    reachabilityChain: [
      { file: "src/x.rs", line: 42, function: "handler", snippet: "..." },
      { file: "src/y.rs", line: 99, function: "query", snippet: null },
    ],
    reachabilityEntryPoint: "POST /api/upload",
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const conclusionSection = model.narrativeSections.find(
    (s) => s.title === "验证结论" || s.title.includes("验证"),
  );
  const body = sectionText(conclusionSection);
  assert.match(body, /调用链证据已列于关联代码面板/);
  assert.match(body, /共 2 hops/);
  assert.match(body, /入口：POST \/api\/upload/);
});

// ---------------------------------------------------------------------------
// G-F9: 验证结论 chain-pointer absent when chain empty  (AC9)
// ---------------------------------------------------------------------------

test("G-F9: 验证结论 chain-pointer absent when chain empty", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    reachabilityChain: [],
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const conclusionSection = model.narrativeSections.find(
    (s) => s.title === "验证结论" || s.title.includes("验证"),
  );
  const body = sectionText(conclusionSection);
  assert.doesNotMatch(body, /调用链证据已列于关联代码面板/);
});

// ---------------------------------------------------------------------------
// G-F10: legacy evidence only — no crash, 根因说明 renders legacy string  (AC11)
// ---------------------------------------------------------------------------

test("G-F10: legacy evidence only — no crash, 根因说明 renders legacy string", () => {
  const finding: AgentFinding = {
    ...baseFinding,
    evidence: "Legacy narrative without code fences",
    // no evidenceProse, no evidenceCodeSnippets, no reachabilityChain
  };
  const model = buildAgentFindingDetailModel({
    finding,
    taskId: "t1",
    findingId: "f1",
  });
  const rootCauseSection = model.narrativeSections.find(
    (s) => s.title === "根因说明",
  );
  const body = sectionText(rootCauseSection);
  assert.match(body, /Legacy narrative without code fences/);
});
