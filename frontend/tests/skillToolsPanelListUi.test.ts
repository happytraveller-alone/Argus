import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skillToolsPanelFile = path.join(
	frontendDir,
	"src/pages/intelligent-scan/SkillToolsPanel.tsx",
);

test("SkillToolsPanel source keeps search-first headers and route-based detail entry", () => {
	const content = fs.readFileSync(skillToolsPanelFile, "utf8");

	assert.match(content, /placeholder="搜索工具名称或执行功能\.\.\."/);
	assert.match(content, /TableHead[^]*?>标签<\/TableHead>/);
	assert.match(content, /TableHead[^]*?>执行功能<\/TableHead>/);
	assert.match(
		content,
		/to=\{`\/scan-config\/external-tools\/\$\{row\.type\}\/\$\{encodeURIComponent\(row\.id\)\}`\}/,
	);
	assert.doesNotMatch(content, /Dialog/);
	assert.doesNotMatch(content, /是否加载/);
});
