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
	const staticSource = readFileSync(staticTaskPagePath, "utf8");
	const intelligentSource = readFileSync(intelligentTaskPagePath, "utf8");

	assert.doesNotMatch(staticSource, /TaskManagementSummaryCards/);
	assert.match(staticSource, /stats\.completed/);
	assert.match(staticSource, /stats\.running/);
	assert.match(staticSource, /stats\.failed/);
	assert.match(staticSource, /Badge/);

	assert.doesNotMatch(intelligentSource, /TaskManagementSummaryCards/);
	assert.match(intelligentSource, /stats\.completed/);
	assert.match(intelligentSource, /stats\.running/);
	assert.match(intelligentSource, /stats\.failed/);
	assert.match(intelligentSource, /Badge/);
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

test("static and intelligent task pages wire delete actions through task APIs", () => {
	const staticSource = readFileSync(staticTaskPagePath, "utf8");
	const intelligentSource = readFileSync(intelligentTaskPagePath, "utf8");

	assert.match(staticSource, /deleteStaticScanTask/);
	assert.match(staticSource, /const handleDeleteActivity = async/);
	assert.match(staticSource, /onDeleteActivity=\{handleDeleteActivity\}/);
	assert.match(staticSource, /deletingActivityId=\{deletingActivityId\}/);

	assert.match(intelligentSource, /deleteIntelligentTask/);
	assert.match(intelligentSource, /const handleDeleteActivity = async/);
	assert.match(intelligentSource, /onDeleteActivity=\{handleDeleteActivity\}/);
	assert.match(intelligentSource, /deletingActivityId=\{deletingActivityId\}/);
});
