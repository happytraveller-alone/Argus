import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { AgentFinding } from "../src/shared/api/agentTasks.ts";
import type { BanditFinding } from "../src/shared/api/bandit.ts";
import type { OpengrepFinding } from "../src/shared/api/opengrep.ts";
import {
  buildAgentFindingDetailModel,
  buildBanditFindingDetailModel,
  buildFullFileDisplayLines,
  buildFindingDetailCodeSections,
  buildOpengrepFindingDetailModel,
  isFindingDetailFullFilePathSupported,
} from "../src/pages/finding-detail/viewModel.ts";
import { buildFindingDetailPath } from "../src/shared/utils/findingRoute.ts";

const agentFinding: AgentFinding = {
  id: "agent-1",
  task_id: "task-agent",
  vulnerability_type: "sql injection",
  severity: "high",
  title: "JdbcController.java 中存在 SQL 注入",
  display_title: "JdbcController.java 中存在 SQL 注入",
  description: "旧版 description，不应在优先展示验证证据时命中。",
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

const opengrepFinding: OpengrepFinding = {
  id: "og-1",
  scan_task_id: "task-og",
  rule: {},
  rule_name: "python-sqli",
  cwe: ["CWE-89"],
  description: "Possible SQL injection",
  file_path: "/tmp/Argus_project/archive-root/src/app/db.py",
  start_line: 23,
  resolved_file_path: "src/app/db.py",
  resolved_line_start: 23,
  code_snippet: "query = f\"SELECT * FROM users WHERE id = {user_id}\"",
  severity: "ERROR",
  status: "open",
  confidence: "HIGH",
};

const banditFinding: BanditFinding = {
  id: "bandit-1",
  scan_task_id: "task-bandit",
  test_id: "B602",
  test_name: "subprocess_popen_with_shell_equals_true",
  issue_text: "shell=True may trigger command injection",
  file_path: "/tmp/Argus_project/archive-root/app/tasks/run_cmd.py",
  line_number: 41,
  resolved_file_path: "app/tasks/run_cmd.py",
  resolved_line_start: 41,
  issue_severity: "HIGH",
  issue_confidence: "HIGH",
  code_snippet: "subprocess.Popen(command, shell=True)",
  more_info: "https://bandit.readthedocs.io/",
  status: "open",
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
    projectId: "project-zip",
    projectSourceType: "zip",
    projectName: "demo",
  });

  assert.equal("sourceLabel" in model, false);
  assert.equal("statusLabel" in model, false);
  assert.equal("heroEyebrow" in model, false);
  assert.equal("heroTitle" in model, false);
  assert.equal("heroSubtitle" in model, false);
  assert.equal("helperLocation" in model, false);
  assert.equal(model.overviewItems[0]?.label, "名称");
  assert.equal(model.overviewItems[0]?.value, "JdbcController.java 中存在 SQL 注入");
  assert.deepEqual(
    model.overviewItems.map((item) => item.label),
    ["名称", "漏洞类型", "漏洞危害", "漏洞置信度", "任务 ID", "漏洞 ID", "文件位置"],
  );
  assert.equal(model.overviewItems[1]?.value, "CWE-89 SQL注入");
  assert.deepEqual(
    model.trackingItems.map((item) => item.label),
    ["任务 ID", "漏洞 ID", "文件位置"],
  );
  assert.equal(model.codePanelTitle, "关联代码");
  assert.equal(model.emptyCodeMessage, "暂无可展示的命中代码。");
  assert.deepEqual(
    model.narrativeSections.map((section) => section.title),
    ["根因说明"],
  );
  assert.equal(
    model.narrativeSections[0]?.finding?.description_markdown,
    [
      "1. 攻击者可控的 `id` 直接拼接进 SQL 语句。",
      "2. 查询在未参数化的情况下进入数据库执行。",
    ].join("\n"),
  );
  assert.equal(model.codeSections[0]?.displayFilePath, "src/main/java/demo/JdbcController.java");
  assert.equal(model.codeSections[0]?.locationLabel, "第 69-83 行");
  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
  assert.deepEqual(model.codeSections[0]?.fullFileRequest, {
    projectId: "project-zip",
    filePath: "src/main/java/demo/JdbcController.java",
  });
  assert.ok(Array.isArray(model.codeSections[0]?.relatedLines));
  assert.equal(model.codeSections[0]?.relatedLines?.[0]?.lineNumber, 67);
});

test("buildAgentFindingDetailModel 在非 ZIP 项目下禁用全文查看", () => {
  const model = buildAgentFindingDetailModel({
    finding: agentFinding,
    taskId: "task-agent",
    findingId: "finding-agent",
    projectId: "project-repo",
    projectSourceType: "repository",
    projectName: "demo",
  });

  assert.equal(model.codeSections[0]?.fullFileAvailable, false);
  assert.equal(model.codeSections[0]?.fullFileRequest, null);
});

test("isFindingDetailFullFilePathSupported 仅接受 ZIP 内相对路径", () => {
  assert.equal(isFindingDetailFullFilePathSupported("src/main.py"), true);
  assert.equal(isFindingDetailFullFilePathSupported("./src/main.py"), true);
  assert.equal(isFindingDetailFullFilePathSupported("/tmp/Argus_project/src/main.py"), false);
  assert.equal(isFindingDetailFullFilePathSupported("/abs/path/src/main.py"), false);
  assert.equal(isFindingDetailFullFilePathSupported(""), false);
});

test("buildBanditFindingDetailModel 在 ZIP 项目下遇到旧绝对路径时禁用全文查看", () => {
  const model = buildBanditFindingDetailModel({
    finding: banditFinding,
    taskId: "task-bandit",
    findingId: "finding-bandit",
    taskName: "Bandit Scan",
    projectId: "project-zip",
    projectSourceType: "zip",
  });

  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
  assert.deepEqual(model.codeSections[0]?.fullFileRequest, {
    projectId: "project-zip",
    filePath: "app/tasks/run_cmd.py",
  });
  assert.deepEqual(model.codeBrowserTarget, {
    filePath: "app/tasks/run_cmd.py",
    line: 41,
  });
});

test("buildOpengrepFindingDetailModel 在 ZIP 项目下遇到旧绝对路径时禁用全文查看", () => {
  const model = buildOpengrepFindingDetailModel({
    finding: opengrepFinding,
    taskId: "task-og",
    findingId: "finding-og",
    taskName: "Opengrep Scan",
    projectId: "project-zip",
    projectSourceType: "zip",
  });

  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
  assert.deepEqual(model.codeSections[0]?.fullFileRequest, {
    projectId: "project-zip",
    filePath: "src/app/db.py",
  });
  assert.equal(model.overviewItems[1]?.value, "CWE-89 SQL注入");
  assert.deepEqual(model.codeBrowserTarget, {
    filePath: "src/app/db.py",
    line: 23,
  });
});

test("buildAgentFindingDetailModel 在缺少 report 时严格展示空态而不回退旧字段", () => {
  const model = buildAgentFindingDetailModel({
    finding: {
      ...agentFinding,
      report: null,
      verification_evidence: "旧验证证据，不应作为左侧主内容。",
      description_markdown: null,
      description: "旧 description，不应作为左侧主内容。",
      suggestion: "旧修复建议，不应作为左侧主内容。",
    },
    taskId: "task-agent",
    findingId: "finding-agent",
  });

  assert.equal(model.codePanelTitle, "关联代码");
  assert.equal(model.emptyCodeMessage, "暂无可展示的命中代码。");
  assert.deepEqual(
    model.narrativeSections.map((section) => section.title),
    ["根因说明"],
  );
  assert.deepEqual(
    model.narrativeSections.map((section) => section.body),
    ["未提供此部分。"],
  );
  assert.equal(model.codeSections[0]?.title, "命中代码");
});

test("buildAgentFindingDetailModel 对缺失章节分别回填严格空态", () => {
  const model = buildAgentFindingDetailModel({
    finding: {
      ...agentFinding,
      description_markdown: [
        "### 定位与结论",
        "",
        "定位结论",
        "",
        "### 代码说明",
        "",
        "改用参数化查询。",
      ].join("\n"),
    },
    taskId: "task-agent",
    findingId: "finding-agent",
  });

  assert.equal(
    model.narrativeSections[0]?.body,
    "未提供此部分。",
  );
  assert.equal(model.codeSections[0]?.title, "命中代码");
});

test("buildAgentFindingDetailModel 的误报分支保留判定依据展示", () => {
  const model = buildAgentFindingDetailModel({
    finding: {
      ...agentFinding,
      status: "false_positive",
      authenticity: "false_positive",
      verification_evidence: "验证证据优先于旧判定描述。",
      description_markdown: "旧 markdown 判定说明",
      description: "旧 description 判定说明",
    },
    taskId: "task-agent",
    findingId: "finding-agent",
  });

  assert.equal(model.narrativeSections[0]?.title, "判定依据");
  assert.equal(
    model.narrativeSections[0]?.finding?.description_markdown,
    "验证证据优先于旧判定描述。",
  );
});

test("finding detail view source uses unified pending/verified/false-positive copy", () => {
  const source = readFileSync(
    new URL("../src/pages/finding-detail/viewModel.ts", import.meta.url),
    "utf8",
  );

  assert.match(source, /return "确报"/);
  assert.match(source, /return "待确认"/);
  assert.match(source, /return "误报"/);
  assert.doesNotMatch(source, /return "已验证"/);
  assert.doesNotMatch(source, /return "待处理"/);
});

test("buildFullFileDisplayLines 生成全文视图并保持焦点与高亮区间", () => {
  const lines = buildFullFileDisplayLines({
    content: ["alpha", "beta", "gamma", "delta"].join("\n"),
    focusLine: 3,
    highlightStartLine: 2,
    highlightEndLine: 3,
    lineStart: 1,
  });

  assert.deepEqual(
    lines.map((line) => line.lineNumber),
    [1, 2, 3, 4],
  );
  assert.equal(lines[1]?.isHighlighted, true);
  assert.equal(lines[2]?.isHighlighted, true);
  assert.equal(lines[2]?.isFocus, true);
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
