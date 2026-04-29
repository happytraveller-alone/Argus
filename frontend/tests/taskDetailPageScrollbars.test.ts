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

test("TaskDetailPage removes the visible event-log module from the detail layout", () => {
	const source = readFileSync(taskDetailPagePath, "utf8");
	const renderStart = source.indexOf(
		'<div className="h-[100dvh] max-h-[100dvh] bg-background flex flex-col overflow-hidden relative">',
	);
	const renderBlock = source.slice(renderStart, source.indexOf("{/* Export dialog */", renderStart));

	assert.doesNotMatch(renderBlock, />事件日志</);
	assert.doesNotMatch(renderBlock, /handleExportLogs\("json"\)/);
	assert.doesNotMatch(renderBlock, /handleToggleAutoScroll/);
	assert.doesNotMatch(renderBlock, /custom-scrollbar-dark/);
});

test("TaskDetailPage uses header metric tags and a 50-50 findings/detail tab layout", () => {
	const taskDetailSource = readFileSync(taskDetailPagePath, "utf8");
	const constantsSource = readFileSync(taskDetailConstantsPath, "utf8");
	const logEntrySource = readFileSync(logEntryPath, "utf8");

	assert.match(taskDetailSource, /metricTags=\{headerMetricTags\}/);
	assert.match(taskDetailSource, /`词元 \$\{formatTokenValue\(statsSummary\.tokensTotal\)\}`/);
	assert.match(taskDetailSource, /`已验证漏洞 \$\{verifiedCount\.toLocaleString\(\)\}`/);
	assert.doesNotMatch(taskDetailSource, /<StatsPanel summary=/);
	assert.match(taskDetailSource, /xl:grid-cols-2/);
	assert.match(taskDetailSource, /<TabsTrigger value="nodes"/);
	assert.match(taskDetailSource, /节点展示/);
	assert.match(taskDetailSource, /<TabsTrigger value="diagnostics"/);
	assert.match(taskDetailSource, /运行诊断/);

	assert.match(
		constantsSource,
		/export const EVENT_LOG_GRID_TEMPLATE\s*=\s*"84px 96px minmax\(320px,1fr\) 112px";/,
	);
	assert.match(logEntrySource, /gridTemplateColumns: EVENT_LOG_GRID_TEMPLATE/);
	assert.doesNotMatch(taskDetailSource, /<span>阶段<\/span>/);
	assert.doesNotMatch(
		taskDetailSource,
		/<span>完成状态<\/span>/,
	);
	assert.doesNotMatch(
		logEntrySource,
		/TOOL_STATUS_LABELS/,
	);
});
