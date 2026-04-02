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

test("TaskDetailPage 重进页面时保留 false_positive 漏洞用于管理视图展示", () => {
	const source = readFileSync(taskDetailPagePath, "utf8");

	assert.match(source, /const visibleManagedFindings = useMemo\(/);
	assert.match(source, /items=\{visibleManagedFindings\}/);
	assert.match(source, /displayFindings: visibleManagedFindings/);
	assert.match(
		source,
		/getAgentFindings\(taskId,\s*\{\s*include_false_positive:\s*true,\s*\}\)/,
	);
	assert.match(source, /if\s*\(\s*falsePositive\s*\)\s*return;/);
	assert.match(source, /!isFalsePositiveFinding\(item\)\s*&&\s*item\.id === detailId/);
	assert.doesNotMatch(source, /hasAnyVerifiedFinding/);
	assert.doesNotMatch(source, /shouldAutoApplyVerifiedFilter/);
	assert.doesNotMatch(source, /verification: "all"/);
});
