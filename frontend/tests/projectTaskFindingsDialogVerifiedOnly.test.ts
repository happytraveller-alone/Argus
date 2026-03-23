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

test("ProjectTaskFindingsDialog 对智能和混合任务只请求已验证漏洞并展示已验证计数文案", () => {
	const source = readFileSync(dialogPath, "utf8");

	assert.match(
		source,
		/getAgentFindings\(taskId,\s*\{\s*is_verified:\s*true,\s*include_false_positive:\s*false,\s*\}\)/,
	);
	assert.match(source, /已验证漏洞共 \{allRows\.length\.toLocaleString\(\)\} 条/);
	assert.match(source, /title: allRows\.length === 0 \? "暂无已验证漏洞" : "暂无符合条件的漏洞"/);
});
