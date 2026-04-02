import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const dialogPath = path.join(
	frontendDir,
	"src/pages/project-detail/components/ProjectTaskFindingsDialog.tsx",
);

test("ProjectTaskFindingsDialog 对智能和混合任务请求全部非误报漏洞并展示总数文案", () => {
	const source = readFileSync(dialogPath, "utf8");

	assert.match(
		source,
		/getAgentFindings\(taskId,\s*\{\s*include_false_positive:\s*false,\s*\}\)/,
	);
	assert.match(source, /漏洞共 \{allRows\.length\.toLocaleString\(\)\} 条/);
	assert.match(
		source,
		/title:\s*allRows\.length === 0\s*\?\s*"暂无漏洞"\s*:\s*"暂无符合条件的漏洞"/,
	);
	assert.match(source, /route: isFalsePositiveAgentFinding\(finding\)\s*\?\s*null\s*:/);
	assert.match(source, /row\.original\.route \?/);
});
