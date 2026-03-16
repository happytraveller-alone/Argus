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

test("TaskDetailPage 仅将事件日志滚动区切换为暗色滚动条类", () => {
	const source = readFileSync(taskDetailPagePath, "utf8");

	assert.match(source, /className="overflow-y-auto custom-scrollbar-dark"/);
	assert.match(source, /className="overflow-x-auto custom-scrollbar"/);
	assert.doesNotMatch(
		source,
		/className="overflow-x-auto custom-scrollbar-dark"/,
	);
});
