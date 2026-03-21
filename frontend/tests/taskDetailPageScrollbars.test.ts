import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const taskDetailPagePath = path.join(
	frontendDir,
	"src/pages/AgentAudit/TaskDetailPage.tsx",
);
const taskDetailConstantsPath = path.join(
	frontendDir,
	"src/pages/AgentAudit/constants.tsx",
);
const logEntryPath = path.join(
	frontendDir,
	"src/pages/AgentAudit/components/LogEntry.tsx",
);

test("TaskDetailPage 仅将事件日志滚动区切换为暗色滚动条类", () => {
	const source = readFileSync(taskDetailPagePath, "utf8");

	assert.match(source, /className="overflow-y-auto custom-scrollbar-dark"/);
	assert.match(source, /className="overflow-x-auto custom-scrollbar"/);
	assert.doesNotMatch(
		source,
		/className="overflow-x-auto custom-scrollbar-dark"/,
	);
});

test("TaskDetailPage 事件日志表头和内容共用固定列模板，避免后半列错位", () => {
	const taskDetailSource = readFileSync(taskDetailPagePath, "utf8");
	const constantsSource = readFileSync(taskDetailConstantsPath, "utf8");
	const logEntrySource = readFileSync(logEntryPath, "utf8");

	assert.match(
		constantsSource,
		/export const EVENT_LOG_GRID_TEMPLATE\s*=\s*"72px 84px minmax\(0,1fr\) 120px 104px";/,
	);
	assert.match(taskDetailSource, /gridTemplateColumns: EVENT_LOG_GRID_TEMPLATE/);
	assert.match(logEntrySource, /gridTemplateColumns: EVENT_LOG_GRID_TEMPLATE/);
	assert.doesNotMatch(
		taskDetailSource,
		/<span>完成状态<\/span>/,
	);
	assert.doesNotMatch(
		logEntrySource,
		/TOOL_STATUS_LABELS/,
	);
});
