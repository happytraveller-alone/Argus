import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const taskManagementSource = readFileSync(
  new URL("../src/pages/TaskManagementIntelligent.tsx", import.meta.url),
  "utf8",
);
const taskDetailSource = readFileSync(
  new URL("../src/pages/AgentAudit/TaskDetailPage.tsx", import.meta.url),
  "utf8",
);

test("intelligent task creation copy is AgentFlow-only", () => {
  assert.match(taskManagementSource, /新建智能审计任务/);
  assert.match(taskManagementSource, /initialMode="agent"/);
  assert.match(taskManagementSource, /lockMode/);
  assert.doesNotMatch(taskManagementSource, /新建扫描任务/);
});

test("agent audit detail no longer fetches static bootstrap findings", () => {
  assert.match(taskDetailSource, /AgentFlow 节点 DAG/);
  assert.match(taskDetailSource, /运行诊断/);
  assert.match(taskDetailSource, /getAgentCheckpoints/);
  assert.doesNotMatch(taskDetailSource, /getOpengrepScanFindings/);
  assert.doesNotMatch(taskDetailSource, /bootstrap_task_id/);
  assert.doesNotMatch(taskDetailSource, /加载静态输入失败/);
});
