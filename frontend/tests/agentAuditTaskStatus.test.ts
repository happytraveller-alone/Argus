import test from "node:test";
import assert from "node:assert/strict";

import {
	buildAgentAuditStreamDisconnectTitle,
	isAgentAuditTerminalStatus,
	toAgentAuditStatusLabel,
} from "../src/pages/AgentAudit/taskStatus.ts";

test("isAgentAuditTerminalStatus 将 interrupted 视为终态", () => {
	assert.equal(isAgentAuditTerminalStatus("completed"), true);
	assert.equal(isAgentAuditTerminalStatus("failed"), true);
	assert.equal(isAgentAuditTerminalStatus("cancelled"), true);
	assert.equal(isAgentAuditTerminalStatus("interrupted"), true);
	assert.equal(isAgentAuditTerminalStatus("running"), false);
	assert.equal(isAgentAuditTerminalStatus("pending"), false);
});

test("toAgentAuditStatusLabel 将 interrupted 显示为中止", () => {
	assert.equal(toAgentAuditStatusLabel("interrupted"), "中止");
	assert.equal(toAgentAuditStatusLabel("cancelled"), "已取消");
});

test("buildAgentAuditStreamDisconnectTitle 使用服务恢复后自动中止的提示语义", () => {
	assert.equal(
		buildAgentAuditStreamDisconnectTitle("transport", "HTTP 502"),
		"服务异常或连接失败：HTTP 502；恢复后进行中的任务会自动标记为中止",
	);
	assert.equal(
		buildAgentAuditStreamDisconnectTitle("stream_end", "连接已关闭"),
		"事件流连接中断：连接已关闭；恢复后进行中的任务会自动标记为中止",
	);
});
