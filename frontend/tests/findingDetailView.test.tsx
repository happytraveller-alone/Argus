import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { AgentFinding } from "../src/shared/api/agentTasks.ts";
import type { BanditFinding } from "../src/shared/api/bandit.ts";
import type { GitleaksFinding } from "../src/shared/api/gitleaks.ts";
import type { OpengrepFinding } from "../src/shared/api/opengrep.ts";
import {
  buildAgentFindingDetailModel,
  buildBanditFindingDetailModel,
  buildGitleaksFindingDetailModel,
  buildOpengrepFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";
import FindingDetailView from "../src/pages/finding-detail/FindingDetailView.tsx";

globalThis.React = React;

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

const falsePositiveFinding: AgentFinding = {
  ...agentFinding,
  id: "agent-fp",
  status: "false_positive",
  authenticity: "false_positive",
  verification_evidence: "参数在进入 SQL 前已经过 allowlist 校验，实际不可利用。",
};

const opengrepFinding: OpengrepFinding = {
  id: "og-1",
  scan_task_id: "task-og",
  rule: {},
  rule_name: "java-sql-injection",
  cwe: ["CWE-89"],
  description: "规则命中字符串拼接式 SQL，建议检查参数化查询。",
  file_path: "src/main/java/demo/JdbcController.java",
  start_line: 69,
  code_snippet: "String sql = \"select * from t where id = \" + id;",
  severity: "ERROR",
  status: "open",
  confidence: "HIGH",
};

const gitleaksFinding: GitleaksFinding = {
  id: "gl-1",
  scan_task_id: "task-gl",
  rule_id: "generic-api-key",
  description: "提交内容中包含疑似 API Key，请立即轮换并复核泄漏范围。",
  file_path: "config/.env.production",
  start_line: 8,
  end_line: 8,
  secret: "ghp_****************",
  match: "ghp_example_secret",
  commit: "abc123",
  author: "dev",
  email: "dev@example.com",
  date: "2026-03-10",
  fingerprint: "gl:1",
  status: "open",
};

const banditFinding: BanditFinding = {
  id: "bandit-1",
  scan_task_id: "task-bandit",
  test_id: "B602",
  test_name: "subprocess_popen_with_shell_equals_true",
  issue_text: "shell=True 会导致命令注入风险，应改为参数化调用。",
  file_path: "app/tasks/run_cmd.py",
  line_number: 41,
  issue_severity: "HIGH",
  issue_confidence: "HIGH",
  code_snippet: "subprocess.Popen(command, shell=True)",
  more_info: "https://bandit.readthedocs.io/en/latest/plugins/b602_subprocess_popen_with_shell_equals_true.html",
  status: "open",
};

function renderMarkup(markupModel: Parameters<typeof FindingDetailView>[0]["model"]) {
  return renderToStaticMarkup(
    createElement(FindingDetailView, {
      model: markupModel,
      onBack: () => {},
    }),
  );
}

function getSectionMarkup(markup: string, title: string, nextTitle: string) {
  const start = markup.indexOf(title);
  const end = markup.indexOf(nextTitle);
  if (start < 0 || end < 0 || end <= start) {
    return "";
  }
  return markup.slice(start, end);
}

test("FindingDetailView 渲染 agent 漏洞详情的新信息层级", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: agentFinding,
      taskId: "task-agent",
      findingId: "finding-agent",
    }),
  );
  const overviewMarkup = getSectionMarkup(markup, "概览信息", "根因说明");

  assert.match(markup, /统一漏洞详情/);
  assert.match(markup, /sql injection/);
  assert.match(markup, /高危/);
  assert.match(markup, /高/);
  assert.match(markup, /概览信息/);
  assert.match(overviewMarkup, /状态/);
  assert.match(overviewMarkup, /已验证/);
  assert.match(overviewMarkup, /漏洞类型/);
  assert.match(markup, /漏洞危害/);
  assert.match(markup, /漏洞置信度/);
  assert.match(markup, /根因说明/);
  assert.match(markup, /追踪信息/);
  assert.match(markup, /任务 ID/);
  assert.match(markup, /漏洞 ID/);
  assert.doesNotMatch(overviewMarkup, /来源/);
  assert.doesNotMatch(overviewMarkup, /标题/);
  assert.doesNotMatch(overviewMarkup, /补充说明/);
  assert.doesNotMatch(overviewMarkup, /位置/);
  assert.doesNotMatch(overviewMarkup, /VERIFIED/);
  assert.doesNotMatch(markup, /任务ID：/);
  assert.doesNotMatch(markup, /漏洞ID：/);
  assert.ok(markup.indexOf("追踪信息") < markup.indexOf("概览信息"));
  assert.ok(markup.indexOf("概览信息") < markup.indexOf("根因说明"));
});

test("FindingDetailView 渲染 agent 误报场景并突出验证结论", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: falsePositiveFinding,
      taskId: "task-agent",
      findingId: "finding-fp",
    }),
  );

  assert.match(markup, /误报判定依据/);
  assert.match(markup, /验证结论/);
  assert.match(markup, /判定依据/);
  assert.match(markup, /误报/);
  assert.match(markup, /sql injection/);
});

test("FindingDetailView 渲染 opengrep 场景并将描述降级为扫描说明", () => {
  const markup = renderMarkup(
    buildOpengrepFindingDetailModel({
      finding: opengrepFinding,
      taskId: "task-og",
      findingId: "finding-og",
      taskName: "Opengrep Scan",
    }),
  );

  assert.match(markup, /java-sql-injection/);
  assert.match(markup, /严重/);
  assert.match(markup, /高/);
  assert.match(markup, /扫描说明/);
  assert.match(markup, /静态扫描 . Opengrep/);
});

test("FindingDetailView 渲染 gitleaks 场景并补齐未提供字段文案", () => {
  const markup = renderMarkup(
    buildGitleaksFindingDetailModel({
      finding: gitleaksFinding,
      taskId: "task-gl",
      findingId: "finding-gl",
      taskName: "Gitleaks Scan",
    }),
  );

  assert.match(markup, /generic-api-key/);
  assert.match(markup, /未分级/);
  assert.match(markup, /未提供/);
  assert.match(markup, /扫描说明/);
  assert.match(markup, /静态扫描 . Gitleaks/);
});

test("FindingDetailView 渲染 bandit 场景并保留核心漏洞信息", () => {
  const markup = renderMarkup(
    buildBanditFindingDetailModel({
      finding: banditFinding,
      taskId: "task-bandit",
      findingId: "finding-bandit",
      taskName: "Bandit Scan",
    }),
  );

  assert.match(markup, /B602/);
  assert.match(markup, /高危/);
  assert.match(markup, /高/);
  assert.match(markup, /扫描说明/);
  assert.match(markup, /静态扫描 . Bandit/);
});
