import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const taskDetailPagePath = path.join(
  frontendDir,
  "src/pages/AgentAudit/TaskDetailPage.tsx",
);

test("TaskDetailPage 手工更新漏洞状态后会同步 task counters 并后台回补任务快照", () => {
  const source = readFileSync(taskDetailPagePath, "utf8");

  assert.match(source, /buildAgentAuditTaskFindingCountersPatch/);
  assert.match(source, /const findingsRef = useRef\(findings\);/);
  assert.match(source, /const taskSnapshotRef = useRef\(task\);/);
  assert.match(source, /const currentFindings = findingsRef\.current;/);
  assert.match(source, /const currentTask = taskSnapshotRef\.current;/);
  assert.match(
    source,
    /setTask\(\{\s*\.\.\.currentTask,\s*\.\.\.buildAgentAuditTaskFindingCountersPatch\(\{\s*task:\s*currentTask,\s*findings:\s*nextFindings,/s,
  );
  assert.match(
    source,
    /void getAgentTask\(taskId\)\s*\.then\(\(snapshot\)\s*=>\s*\{\s*setTask\(snapshot\);/s,
  );
  assert.match(source, /const FINDINGS_PAGE_SIZE = 200;/);
  assert.match(
    source,
    /getAgentFindings\(taskId,\s*\{\s*include_false_positive:\s*true,\s*skip,\s*limit:\s*FINDINGS_PAGE_SIZE,/s,
  );
  assert.match(
    source,
    /failed to refresh task counters after manual status update/,
  );
});
