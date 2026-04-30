import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const summaryCardsPath = path.join(
	frontendDir,
	"src/features/tasks/components/TaskManagementSummaryCards.tsx",
);
const staticTaskPagePath = path.join(
	frontendDir,
	"src/pages/TaskManagementStatic.tsx",
);
const intelligentTaskPagePath = path.join(
	frontendDir,
	"src/pages/TaskManagementIntelligent.tsx",
);

test("task management summary cards follow the dashboard compact card contract", () => {
	const source = readFileSync(summaryCardsPath, "utf8");

	assert.match(source, /rounded-sm border border-border bg-card/);
	assert.match(
		source,
		/text-sm uppercase tracking-\[0\.12em\] text-muted-foreground/,
	);
	assert.match(
		source,
		/text-right text-xl font-semibold tabular-nums text-foreground/,
	);
	assert.match(source, /grid shrink-0 grid-cols-1 gap-3 sm:grid-cols-3/);
	assert.doesNotMatch(source, /cyber-card/);
	assert.doesNotMatch(source, /fontSize/);
	assert.doesNotMatch(source, /text-\[clamp/);
});

test("static and intelligent task pages use inline status badges instead of summary cards", () => {
	for (const taskPagePath of [staticTaskPagePath, intelligentTaskPagePath]) {
		const source = readFileSync(taskPagePath, "utf8");

		assert.doesNotMatch(source, /TaskManagementSummaryCards/);
		assert.match(source, /stats\.completed/);
		assert.match(source, /stats\.running/);
		assert.match(source, /stats\.failed/);
		assert.match(source, /Badge/);
	}
});

test("static task management search input filters the visible task table", () => {
	const source = readFileSync(staticTaskPagePath, "utf8");

	assert.match(
		source,
		/const filteredStaticActivities = useMemo\(\s*\(\) => filterActivitiesByKind\(activities, "rule_scan", keyword\),/,
	);
	assert.match(source, /activities=\{filteredStaticActivities\}/);
	assert.doesNotMatch(source, /activities=\{staticActivities\}/);
});
