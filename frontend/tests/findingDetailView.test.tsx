import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { AgentFinding } from "../src/shared/api/agentTasks.ts";
import type { OpengrepFinding } from "../src/shared/api/opengrep.ts";
import {
  buildAgentFindingDetailModel,
  buildOpengrepFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";
import FindingDetailView from "../src/pages/finding-detail/FindingDetailView.tsx";
import type { FindingDetailCodeBrowserAction } from "../src/pages/finding-detail/FindingDetailHeaderActions.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const agentFinding: AgentFinding = {
  id: "agent-1",
  task_id: "task-agent",
  vulnerability_type: "sql injection",
  severity: "high",
  title: "JdbcController.java 中存在 SQL 注入",
  display_title: "JdbcController.java 中存在 SQL 注入",
  description: "旧版 description，不应成为首选根因说明。",
  description_markdown: [
    "### 定位与结论",
    "",
    "定位到 `src/main/java/demo/JdbcController.java:69-83` 的 `find` 方法，对应 `CWE-89`。",
    "",
    "### 根因解释",
    "",
    "1. 攻击者可控的 `id` 直接拼接进 SQL 语句。",
    "2. 查询在未参数化的情况下进入数据库执行。",
    "",
    "### 代码说明",
    "",
    "命中语句位于控制器查询路径，字符串拼接结果直接传入 `jdbcTemplate.queryForObject`。",
  ].join("\n"),
  report: [
    "# 漏洞报告：JdbcController.java 中存在 SQL 注入",
    "",
    "## 4. 漏洞原理",
    "",
    "1. 攻击者可控的 `id` 直接拼接进 SQL 语句。",
    "2. 查询在未参数化的情况下进入数据库执行。",
    "",
    "## 5. 代码证据",
    "",
    "- 位置：`src/main/java/demo/JdbcController.java` 行 69-83",
    "```java",
    "String sql = \"select * from t where id = \" + id;",
    "return jdbcTemplate.queryForObject(sql, String.class);",
    "```",
    "",
    "## 8. 业务影响",
    "",
    "攻击者可借此读取任意用户记录，进一步造成敏感数据泄露。",
    "",
    "## 9. 修复建议",
    "",
    "改用参数化查询，并在进入数据层前校验 `id` 的格式与范围。",
  ].join("\n"),
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
  description_markdown: "旧版误报 markdown",
  description: "旧版误报 description",
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

function renderMarkup(
  markupModel: Parameters<typeof FindingDetailView>[0]["model"],
  extraProps?: Partial<{ codeBrowserAction: FindingDetailCodeBrowserAction | null }>,
) {
  return renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(FindingDetailView, {
        model: markupModel,
        onBack: () => {},
        ...extraProps,
      }),
    ),
  );
}

function getSectionMarkup(markup: string, title: string, nextTitle?: string) {
  const start = markup.indexOf(title);
  const end = nextTitle ? markup.indexOf(nextTitle) : -1;
  if (start < 0) {
    return "";
  }
  if (end < 0 || end <= start) {
    return markup.slice(start);
  }
  return markup.slice(start, end);
}

test("FindingDetailView 渲染 agent 漏洞详情的新信息层级并隐藏完整文件入口", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: agentFinding,
      taskId: "task-agent",
      findingId: "finding-agent",
      projectId: "project-zip",
      projectSourceType: "zip",
      projectName: "demo",
    }),
  );
  const overviewMarkup = getSectionMarkup(markup, "概览信息", "漏洞原理");

  assert.match(markup, /统一漏洞详情/);
  assert.match(markup, /CWE-89 SQL注入/);
  assert.match(markup, /SQL Injection/);
  assert.match(markup, /高危/);
  assert.match(markup, /高/);
  assert.match(markup, /概览信息/);
  assert.match(overviewMarkup, /名称/);
  assert.match(overviewMarkup, /JdbcController\.java 中存在 SQL 注入/);
  assert.match(overviewMarkup, /漏洞类型/);
  assert.match(markup, /漏洞危害/);
  assert.match(markup, /漏洞置信度/);
  assert.match(markup, /根因说明/);
  assert.match(markup, /关联代码/);
  assert.match(overviewMarkup, /任务 ID/);
  assert.match(overviewMarkup, /漏洞 ID/);
  assert.match(overviewMarkup, /文件位置/);
  assert.match(markup, /攻击者可控的/);
  assert.doesNotMatch(markup, /旧版 description，不应成为首选根因说明。/);
  assert.doesNotMatch(markup, /业务影响/);
  assert.doesNotMatch(markup, /修复建议/);
  assert.doesNotMatch(overviewMarkup, /来源/);
  assert.doesNotMatch(overviewMarkup, /标题/);
  assert.doesNotMatch(overviewMarkup, /补充说明/);
  assert.doesNotMatch(overviewMarkup, /VERIFIED/);
  assert.doesNotMatch(overviewMarkup, /状态/);
  assert.doesNotMatch(markup, /任务ID：/);
  assert.doesNotMatch(markup, /漏洞ID：/);
  assert.doesNotMatch(markup, /追踪信息/);
  assert.ok(markup.indexOf("概览信息") < markup.indexOf("根因说明"));
  assert.doesNotMatch(markup, /查看文件/);
  assert.doesNotMatch(markup, /查看文件全部内容/);
  assert.match(markup, /src\/main\/java\/demo\/JdbcController\.java/);
  assert.match(markup, /第 69-83 行/);
  assert.match(markup, /return jdbcTemplate\.queryForObject/);
  assert.doesNotMatch(markup, /1 个代码块/);
  assert.doesNotMatch(markup, /bg-gradient/);
});

test("FindingDetailView 在 agent finding 缺少 report 时展示严格空态", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: {
        ...agentFinding,
        description_markdown: null,
        report: null,
        verification_evidence: "旧验证证据，不应回退展示。",
        description: "旧 description，不应回退展示。",
      },
      taskId: "task-agent",
      findingId: "finding-agent",
    }),
  );

  assert.match(markup, /根因说明/);
  assert.match(markup, /未提供此部分。/);
  assert.doesNotMatch(markup, /旧验证证据，不应回退展示。/);
  assert.doesNotMatch(markup, /旧 description，不应回退展示。/);
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
  assert.match(markup, /CWE-89 SQL注入/);
  assert.match(markup, /参数在进入 SQL 前已经过 allowlist 校验，实际不可利用。/);
  assert.doesNotMatch(markup, /旧版误报 markdown/);
  assert.doesNotMatch(markup, /旧版误报 description/);
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

  assert.match(markup, /CWE-89 SQL注入/);
  assert.match(markup, /SQL Injection/);
  assert.match(markup, /严重/);
  assert.match(markup, /高/);
  assert.match(markup, /扫描说明/);
  assert.match(markup, /静态审计 . Opengrep/);
});

test("FindingDetailView 渲染可用的代码浏览按钮", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: agentFinding,
      taskId: "task-agent",
      findingId: "finding-agent",
    }),
    {
      codeBrowserAction: {
        label: "代码浏览",
        to: "/projects/p-demo/code-browser",
        state: { from: "/finding-detail/agent/task-agent/finding-agent" },
      },
    },
  );

  assert.match(markup, /代码浏览/);
  assert.match(markup, /href="\/projects\/p-demo\/code-browser"/);
});

test("FindingDetailView 在桌面端保持概要在左代码在右并放大主要字号", () => {
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: agentFinding,
      taskId: "task-agent",
      findingId: "finding-agent",
      projectId: "project-zip",
      projectSourceType: "zip",
      projectName: "demo",
    }),
  );

  assert.match(
    markup,
    /xl:grid-cols-\[minmax\(0,1\.02fr\)_minmax\(0,0\.98fr\)\]/,
  );
  assert.match(markup, /order-1 xl:order-1/);
  assert.match(markup, /order-2 xl:order-2/);
  assert.match(markup, /text-\[1\.95rem\] font-semibold/);
  assert.match(
    markup,
    /text-\[0\.9rem\] uppercase tracking-\[0\.16em\] text-muted-foreground/,
  );
});

test("FindingDetailView 提示代码浏览不可用原因", () => {
  const reason = "仅 ZIP 类型项目支持代码浏览";
  const markup = renderMarkup(
    buildAgentFindingDetailModel({
      finding: agentFinding,
      taskId: "task-agent",
      findingId: "finding-agent",
    }),
    {
      codeBrowserAction: {
        label: "代码浏览",
        disabledReason: reason,
      },
    },
  );

  assert.match(markup, new RegExp(reason));
  assert.match(markup, /代码浏览/);
  assert.match(markup, /disabled/);
});
