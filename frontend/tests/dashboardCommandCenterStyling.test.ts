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

test("DashboardCommandCenter places the view switcher before chart and status beside chart", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");
	const previewIndex = source.indexOf("<PreviewHeader snapshot={snapshot} />");
	const viewIndex = source.indexOf("<ViewSidebar activeView={activeView} onChange={setActiveView} />");
	const gridIndex = source.indexOf(
		"<div className={DASHBOARD_MAIN_GRID_CLASSNAME}>",
	);
	const statusIndex = source.indexOf("<TaskStatusPanel snapshot={snapshot} />");

	assert.ok(previewIndex >= 0);
	assert.ok(gridIndex > previewIndex);
	assert.ok(viewIndex > gridIndex);
	assert.ok(statusIndex > viewIndex);
	assert.match(source, /lg:grid-cols-\[minmax\(0,1fr\)_minmax\(360px,28rem\)\]/);
	assert.match(
		source,
		/const DASHBOARD_CHART_AREA_GRID_CLASSNAME =\s*"grid min-w-0 gap-4 xl:min-h-0"/,
	);
	assert.match(
		source,
		/const DASHBOARD_VIEW_RAIL_LIST_CLASSNAME =\s*"grid gap-2 sm:grid-cols-2 xl:grid-cols-5"/,
	);
	assert.doesNotMatch(source, /xl:grid-cols-\[minmax\(11rem,14rem\)_minmax\(0,1fr\)\]/);
});

test("DashboardCommandCenter task status uses two audit-type sections", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(source, /buildAuditTypeTaskStatusSections\(snapshot\)/);
	assert.match(source, /label: "智能审计"/);
	assert.match(source, /label: "静态审计"/);
	assert.match(source, /\["已完成", section\.completed\]/);
	assert.match(source, /\["进行中", section\.running\]/);
	assert.match(source, /\["异常", section\.anomaly\]/);
	assert.doesNotMatch(source, /label: "已完成任务"/);
	assert.doesNotMatch(source, /TASK_STATUS_CARD_GRID_CLASSNAME/);
});

test("DashboardCommandCenter recent tasks render three full-card links in one row", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/const RECENT_TASK_CARD_CLASSNAME =\s*"min-w-0 rounded-sm border border-border bg-card px-3 py-2\.5 text-xs text-card-foreground shadow-sm transition/,
	);
	assert.match(source, /const recentTasks = getRecentTaskCards\(section\.recentTasks\);/);
	assert.match(source, /<a[\s\S]*className=\{RECENT_TASK_CARD_CLASSNAME\}/);
	assert.match(source, /<Badge className="cyber-badge cyber-badge-muted min-w-0 max-w-full flex-1 truncate normal-case tracking-normal">/);
	assert.match(source, /<Badge className=\{`cyber-badge shrink-0 \$\{typeBadgeClassName\}`\}>/);
	assert.match(source, /<Badge className=\{`cyber-badge shrink-0 \$\{progressBadgeClassName\}`\}>/);
	assert.match(source, /getRecentTaskTypeBadgeClassName\(task\.task_type\)/);
	assert.match(source, /getRecentTaskProgressBadgeClassName\(\s*task\.status,\s*\)/s);
	assert.match(source, /<ChevronRight className="mt-0\.5 h-4 w-4 shrink-0 text-muted-foreground" \/>/);
	assert.doesNotMatch(
		source,
		/href=\{task\.detail_path \|\| "\/tasks\/static"\}[\s\S]*<Eye/,
	);
	assert.doesNotMatch(source, /getEstimatedTaskProgressPercent/);
	assert.doesNotMatch(source, /h-2 rounded-full bg-muted\/70/);
});

test("DashboardCommandCenter recent tasks live inside each audit-type section", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(source, /data-audit-type-section=\{section\.key\}/);
	assert.match(source, /const recentTasks = getRecentTaskCards\(section\.recentTasks\);/);
	assert.match(source, /href=\{section\.tasksRoute\}/);
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
