import test from "node:test";
import assert from "node:assert/strict";

import type { AgentFinding } from "../src/shared/api/agentTasks.ts";
import type { BanditFinding } from "../src/shared/api/bandit.ts";
import type { OpengrepFinding } from "../src/shared/api/opengrep.ts";
import {
  buildAgentFindingDetailModel,
  buildBanditFindingDetailModel,
  buildOpengrepFindingDetailModel,
} from "../src/pages/finding-detail/viewModel.ts";

const agentFinding: AgentFinding = {
  id: "agent-1",
  task_id: "task-agent",
  vulnerability_type: "sql injection",
  severity: "high",
  title: "JdbcController.java 中存在 SQL 注入",
  display_title: "JdbcController.java 中存在 SQL 注入",
  description: "desc",
  description_markdown: "### 定位与结论\n\n定位结论\n\n### 根因解释\n\n原因\n\n### 代码说明\n\n说明",
  report: "# report",
  file_path: "/tmp/archive-root/src/main/java/demo/JdbcController.java",
  line_start: 69,
  line_end: 83,
  resolved_file_path: "src/main/java/demo/JdbcController.java",
  resolved_line_start: 69,
  code_snippet: "String sql = \"select * from t where id = \" + id;",
  code_context: "line1\nline2\nline3",
  cwe_id: "CWE-89",
  cwe_name: "SQL Injection",
  context_start_line: 67,
  context_end_line: 85,
  status: "verified",
  is_verified: true,
  reachability: "reachable",
  authenticity: "true_positive",
  verification_evidence: "evidence",
  verification_todo_id: null,
  verification_fingerprint: null,
  reachability_file: null,
  reachability_function: null,
  reachability_function_start_line: null,
  reachability_function_end_line: null,
  flow_path_score: null,
  flow_call_chain: null,
  function_trigger_flow: null,
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

test("buildAgentFindingDetailModel prefers resolved code browser target for ZIP projects", () => {
  const model = buildAgentFindingDetailModel({
    finding: agentFinding,
    taskId: "task-agent",
    findingId: "finding-agent",
    projectId: "project-zip",
    projectSourceType: "zip",
    projectName: "demo",
  });

  assert.deepEqual(model.codeBrowserTarget, {
    filePath: "src/main/java/demo/JdbcController.java",
    line: 69,
  });
  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
  assert.deepEqual(model.codeSections[0]?.fullFileRequest, {
    projectId: "project-zip",
    filePath: "src/main/java/demo/JdbcController.java",
  });
});

test("buildBanditFindingDetailModel uses resolved location for code browser target and full file access", () => {
  const model = buildBanditFindingDetailModel({
    finding: banditFinding,
    taskId: "task-bandit",
    findingId: "finding-bandit",
    taskName: "Bandit Scan",
    projectId: "project-zip",
    projectSourceType: "zip",
  });

  assert.deepEqual(model.codeBrowserTarget, {
    filePath: "app/tasks/run_cmd.py",
    line: 41,
  });
  assert.equal(model.codeSections[0]?.filePath, "app/tasks/run_cmd.py");
  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
});

test("buildOpengrepFindingDetailModel uses resolved location for code browser target and full file access", () => {
  const model = buildOpengrepFindingDetailModel({
    finding: opengrepFinding,
    taskId: "task-og",
    findingId: "finding-og",
    taskName: "Opengrep Scan",
    projectId: "project-zip",
    projectSourceType: "zip",
  });

  assert.deepEqual(model.codeBrowserTarget, {
    filePath: "src/app/db.py",
    line: 23,
  });
  assert.equal(model.codeSections[0]?.filePath, "src/app/db.py");
  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
});
