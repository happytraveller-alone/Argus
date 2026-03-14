import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { AgentFinding } from "../src/shared/api/agentTasks.ts";
import {
  buildAgentFindingDetailModel,
  buildFindingDetailCodeSections,
} from "../src/pages/finding-detail/viewModel.ts";
import { buildFindingDetailPath } from "../src/shared/utils/findingRoute.ts";

const agentFinding: AgentFinding = {
  id: "agent-1",
  task_id: "task-agent",
  vulnerability_type: "sql injection",
  severity: "high",
  title: "JdbcController.java 中存在 SQL 注入",
  display_title: "JdbcController.java 中存在 SQL 注入",
  description: "用户输入被直接拼接进 SQL 语句，攻击者可构造恶意参数读取数据。",
  description_markdown: null,
  file_path: "src/main/java/demo/JdbcController.java",
  line_start: 69,
  line_end: 83,
  code_snippet: "String sql = \"select * from t where id = \" + id;",
  code_context: [
    "public String find(String id) {",
    "  String sql = \"select * from t where id = \" + id;",
    "  return jdbcTemplate.queryForObject(sql, String.class);",
    "}",
  ].join("\n"),
  cwe_id: "CWE-89",
  cwe_name: "SQL Injection",
  context_start_line: 67,
  context_end_line: 85,
  status: "verified",
  is_verified: true,
  reachability: "reachable",
  authenticity: "true_positive",
  verification_evidence: "参数 id 未经过滤直接进入 SQL 字符串。",
  verification_todo_id: null,
  verification_fingerprint: null,
  reachability_file: null,
  reachability_function: null,
  reachability_function_start_line: null,
  reachability_function_end_line: null,
  flow_path_score: null,
  flow_call_chain: null,
  function_trigger_flow: ["Controller.find", "JdbcTemplate.queryForObject"],
  flow_control_conditions: null,
  logic_authz_evidence: null,
  has_poc: false,
  poc_code: null,
  trigger_flow: null,
  poc_trigger_chain: null,
  suggestion: null,
  fix_code: null,
  ai_explanation: null,
  ai_confidence: 0.91,
  confidence: 0.91,
  created_at: "2026-03-12T00:00:00Z",
};

test("buildFindingDetailCodeSections 裁剪命中代码并插入省略占位", () => {
  const code = Array.from({ length: 21 }, (_, index) => `line ${20 + index}`).join("\n");
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-1",
      title: "命中代码",
      filePath: "src/demo.ts",
      code,
      lineStart: 20,
      lineEnd: 40,
      highlightStartLine: 30,
      highlightEndLine: 31,
      focusLine: 30,
    },
  ]);

  assert.ok(section);
  assert.ok(section.displayLines);
  assert.equal(section.displayLines?.[0]?.lineNumber, null);
  assert.equal(section.displayLines?.[0]?.content, "// ....");
  assert.deepEqual(
    section.displayLines?.slice(1, -1).map((line) => line.lineNumber),
    [27, 28, 29, 30, 31, 32, 33, 34],
  );
  assert.equal(section.displayLines?.at(-1)?.lineNumber, null);
  assert.equal(section.displayLines?.at(-1)?.content, "// ....");
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 30)?.isHighlighted,
    true,
  );
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 30)?.isFocus,
    true,
  );
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 31)?.isHighlighted,
    true,
  );
});

test("buildFindingDetailCodeSections 对没有可靠行号的片段保持原样", () => {
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-2",
      title: "命中代码",
      filePath: "src/raw.txt",
      code: "raw one\nraw two",
      lineStart: null,
      lineEnd: null,
      highlightStartLine: null,
      highlightEndLine: null,
      focusLine: null,
    },
  ]);

  assert.ok(section);
  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, "raw one\nraw two");
});

test("buildFindingDetailCodeSections 对短片段保持原样", () => {
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-3",
      title: "命中代码",
      filePath: "src/short.ts",
      code: "a\nb\nc\nd\ne",
      lineStart: 10,
      lineEnd: 14,
      highlightStartLine: 12,
      highlightEndLine: 12,
      focusLine: 12,
    },
  ]);

  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, "a\nb\nc\nd\ne");
});

test("buildFindingDetailCodeSections 对单行命中长片段保持原样", () => {
  const code = Array.from({ length: 18 }, (_, index) => `line ${index + 1}`).join("\n");
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-4",
      title: "命中代码",
      filePath: "src/long-single.ts",
      code,
      lineStart: 1,
      lineEnd: 18,
      highlightStartLine: 9,
      highlightEndLine: 9,
      focusLine: 9,
    },
  ]);

  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, code);
});

test("buildFindingDetailPath 为 bandit 详情保留 engine 查询参数", () => {
  const route = buildFindingDetailPath({
    source: "static",
    taskId: "task-bandit",
    findingId: "finding-bandit",
    engine: "bandit",
  });

  assert.equal(
    route,
    "/finding-detail/static/task-bandit/finding-bandit?engine=bandit",
  );
});

test("buildAgentFindingDetailModel 将概览信息直接收敛为 overviewItems", () => {
  const model = buildAgentFindingDetailModel({
    finding: agentFinding,
    taskId: "task-agent",
    findingId: "finding-agent",
  });

  assert.equal(Object.hasOwn(model, "sourceLabel"), false);
  assert.equal(Object.hasOwn(model, "statusLabel"), false);
  assert.equal(Object.hasOwn(model, "heroEyebrow"), false);
  assert.equal(Object.hasOwn(model, "heroTitle"), false);
  assert.equal(Object.hasOwn(model, "heroSubtitle"), false);
  assert.equal(Object.hasOwn(model, "helperLocation"), false);
  assert.equal(model.overviewItems[0]?.label, "状态");
  assert.equal(model.overviewItems[0]?.value, "已验证");
  assert.deepEqual(
    model.overviewItems.map((item) => item.label),
    ["状态", "漏洞类型", "漏洞危害", "漏洞置信度"],
  );
});

test("buildOverviewItems 不再使用 hero 历史命名", () => {
  const source = readFileSync(
    new URL("../src/pages/finding-detail/viewModel.ts", import.meta.url),
    "utf8",
  );

  assert.match(source, /headlineLabel/);
  assert.match(source, /headlineValue/);
  assert.doesNotMatch(source, /buildOverviewItems[\s\S]*heroEyebrow/);
  assert.doesNotMatch(source, /buildOverviewItems[\s\S]*heroTitle/);
});
