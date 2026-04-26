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

test("DashboardCommandCenter recent task titles match progress text styling instead of bold headings", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/<p className="truncate text-xs text-muted-foreground">/,
	);
	assert.match(
		source,
		/<div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">/,
	);
	assert.doesNotMatch(
		source,
		/<p className="truncate text-sm font-semibold text-foreground">/,
	);
});

test("DashboardCommandCenter recent tasks section adds top spacing away from task status", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/<div className="mt-8 flex items-start justify-between gap-6">[\s\S]*<h2 className=\{DASHBOARD_PANEL_TITLE_CLASSNAME\}>最近任务<\/h2>/,
	);
});

test("DashboardCommandCenter recent task pagination places previous and next buttons on opposite sides", () => {
	const source = readFileSync(dashboardCommandCenterPath, "utf8");

	assert.match(
		source,
		/<div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border\/70 pt-4">[\s\S]*上一页[\s\S]*下一页[\s\S]*<\/div>/,
	);
	assert.doesNotMatch(
		source,
		/<div className="flex items-center gap-2">[\s\S]*上一页[\s\S]*下一页[\s\S]*<\/div>/,
	);
});
