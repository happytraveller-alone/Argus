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

test("TaskDetailPage 以 visibleVerifiedFindings 作为 verified-only 页面级数据源", () => {
	const source = readFileSync(taskDetailPagePath, "utf8");

	assert.match(source, /const visibleVerifiedFindings = useMemo\(/);
	assert.match(source, /items=\{visibleVerifiedFindings\}/);
	assert.match(source, /displayFindings: visibleVerifiedFindings/);
	assert.match(
		source,
		/getAgentFindings\(taskId,\s*\{\s*is_verified:\s*true,\s*include_false_positive:\s*false,\s*\}\)/,
	);
	assert.doesNotMatch(source, /hasAnyVerifiedFinding/);
	assert.doesNotMatch(source, /shouldAutoApplyVerifiedFilter/);
	assert.doesNotMatch(source, /verification: "all"/);
});
