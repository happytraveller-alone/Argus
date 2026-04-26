import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const dashboardCommandCenterPath = path.join(
	frontendDir,
	"src/features/dashboard/components/DashboardCommandCenter.tsx",
);

test("DashboardCommandCenter uses shared card tokens and avoids gradient dashboard surfaces", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/const DASHBOARD_PANEL_CLASSNAME =\s*"rounded-sm border border-border bg-card text-card-foreground shadow-sm"/,
	);
	assert.match(
		source,
		/className="px-1 pb-1 text-foreground xl:flex xl:h-full xl:min-h-0 xl:flex-col xl:overflow-hidden"/,
	);
	assert.doesNotMatch(source, /bg-\[radial-gradient/);
	assert.doesNotMatch(source, /bg-\[linear-gradient/);
	assert.doesNotMatch(source, /bg-gradient-to-r/);
	assert.doesNotMatch(source, /<linearGradient/);
});

test("DashboardCommandCenter chart sidebar labels use bold weight", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(source, /<span className="font-bold tracking-\[0\.02em\]">/);
});

test("DashboardCommandCenter summary card descriptions use enlarged label text", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/const DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME =\s*"text-sm uppercase tracking-\[0\.12em\] text-muted-foreground"/,
	);
	assert.match(
		source,
		/<div className=\{DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME\}>/,
	);
	assert.match(
		source,
		/className=\{`\$\{DASHBOARD_PANEL_CLASSNAME\} flex items-center justify-between gap-3 px-3 py-3`\}/,
	);
	assert.match(
		source,
		/className="text-right text-xl font-semibold tabular-nums text-foreground"/,
	);
});

test("DashboardCommandCenter places task status between summary cards and charts", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");
	const previewIndex = source.indexOf("<PreviewHeader snapshot={snapshot} />");
	const statusIndex = source.indexOf("<TaskStatusPanel snapshot={snapshot} />");
	const gridIndex = source.indexOf(
		"<div className={DASHBOARD_MAIN_GRID_CLASSNAME}>",
	);

	assert.ok(previewIndex >= 0);
	assert.ok(statusIndex > previewIndex);
	assert.ok(gridIndex > statusIndex);
	assert.doesNotMatch(
		source,
		/lg:col-start-2[\s\S]*<TaskStatusPanel snapshot=\{snapshot\} \/>/,
	);
});

test("DashboardCommandCenter task status uses four compact statistic cards", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/const TASK_STATUS_CARD_GRID_CLASSNAME =\s*"mt-3 grid grid-cols-4 gap-3 overflow-x-auto"/,
	);
	assert.match(
		source,
		/const TASK_STATUS_CARD_CLASSNAME =\s*"min-w-\[8\.5rem\] rounded-sm border border-border\/70 bg-background\/70 px-4 py-3 text-left transition/,
	);
	assert.match(source, /label: "已完成任务"/);
	assert.match(source, /label: "进行中任务"/);
	assert.match(source, /label: "报错任务"/);
	assert.match(source, /label: "中断任务"/);
	assert.match(source, /buildTaskStatusCards\(snapshot\)/);
	assert.doesNotMatch(
		source,
		/className="h-3 rounded-full bg-muted\/70"/,
	);
	assert.doesNotMatch(source, /暂无任务状态数据/);
});

test("DashboardCommandCenter recent tasks render three full-card links in one row", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/const RECENT_TASK_CARD_GRID_CLASSNAME =\s*"mt-4 grid grid-cols-3 gap-3 overflow-x-auto"/,
	);
	assert.match(
		source,
		/const RECENT_TASK_CARD_CLASSNAME =\s*"min-w-\[16rem\] rounded-sm border border-border bg-card px-4 py-4 text-card-foreground shadow-sm transition/,
	);
	assert.match(source, /const recentTasks = getRecentTaskCards\(snapshot\.recent_tasks\);/);
	assert.match(source, /<a[\s\S]*className=\{RECENT_TASK_CARD_CLASSNAME\}/);
	assert.match(source, /<Badge className="cyber-badge cyber-badge-muted min-w-0 max-w-full flex-1 truncate normal-case tracking-normal">/);
	assert.match(source, /<Badge className=\{`cyber-badge shrink-0 \$\{typeBadgeClassName\}`\}>/);
	assert.match(source, /<Badge className=\{`cyber-badge shrink-0 \$\{progressBadgeClassName\}`\}>/);
	assert.match(source, /getRecentTaskTypeBadgeClassName\(task\.task_type\)/);
	assert.match(source, /getRecentTaskProgressBadgeClassName\(task\.status\)/);
	assert.match(source, /<ChevronRight className="mt-0\.5 h-4 w-4 shrink-0 text-muted-foreground" \/>/);
	assert.doesNotMatch(
		source,
		/href=\{task\.detail_path \|\| "\/tasks\/static"\}[\s\S]*<Eye/,
	);
	assert.doesNotMatch(source, /getEstimatedTaskProgressPercent/);
	assert.doesNotMatch(source, /h-2 rounded-full bg-muted\/70/);
});

test("DashboardCommandCenter recent tasks section adds top spacing away from task status", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/<div className="mt-8 flex items-start justify-between gap-6">[\s\S]*<h2 className=\{DASHBOARD_PANEL_TITLE_CLASSNAME\}>最近任务<\/h2>/,
	);
});

test("DashboardCommandCenter recent tasks remove divider and pagination controls", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.doesNotMatch(
		source,
		/<div className="mt-1 border-t border-border\/70 pt-5/,
	);
	assert.doesNotMatch(
		source,
		/<div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border\/70 pt-4">/,
	);
	assert.doesNotMatch(source, /上一页/);
	assert.doesNotMatch(source, /下一页/);
	assert.doesNotMatch(source, /paginateRecentTasks/);
});
