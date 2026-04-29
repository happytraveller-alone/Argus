import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const taskDetailPagePath = path.resolve(
	process.cwd(),
	"src/pages/AgentAudit/TaskDetailPage.tsx",
);
const headerPath = path.resolve(
	process.cwd(),
	"src/pages/AgentAudit/components/Header.tsx",
);

test("AgentAudit 详情页首页卡片直接保留静态审计和智能审计，不再依赖重复定义后去重", () => {
	const source = fs.readFileSync(taskDetailPagePath, "utf8");
	const homeScanCardsBlock = source.match(
		/const homeScanCards: HomeScanCard\[] = useMemo\(\s*\(\) => \[(.*?)\],\s*\[\],\s*\);/s,
	)?.[1];

	assert.ok(homeScanCardsBlock);
	assert.equal(homeScanCardsBlock.match(/key:\s*"static"/g)?.length ?? 0, 1);
	assert.equal(homeScanCardsBlock.match(/key:\s*"agent"/g)?.length ?? 0, 1);
	assert.doesNotMatch(
		homeScanCardsBlock,
		/findIndex\(\(item\) => item\.key === card\.key\)/,
	);
});

test("AgentAudit 详情页概要标签放在标题侧并使用更大的标签字号", () => {
	const source = fs.readFileSync(headerPath, "utf8");
	const titleSideIndex = source.indexOf('data-agent-audit-title-row="true"');
	const metricTagsIndex = source.indexOf("metricTags.map");
	const actionClusterIndex = source.indexOf(
		'<div className="flex items-center gap-2 flex-wrap">',
	);
	const actionBlock = source.slice(actionClusterIndex);

	assert.ok(titleSideIndex >= 0);
	assert.ok(metricTagsIndex > titleSideIndex);
	assert.ok(actionClusterIndex > metricTagsIndex);
	assert.match(source, /aria-label="智能审计概要标签"/);
	assert.match(
		source,
		/className="h-9 max-w-\[260px\] truncate rounded-full border-border\/70 bg-muted\/30 px-3 text-sm font-semibold text-foreground\/85"/,
	);
	assert.doesNotMatch(actionBlock, /metricTags\.map/);
	assert.doesNotMatch(source, /h-8 max-w-\[220px\][^"]*text-xs/);
});
