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

test("ProjectTaskFindingsDialog retires agent finding fetches and keeps static findings count copy", () => {
	const source = readFileSync(dialogPath, "utf8");

	assert.doesNotMatch(source, /getAgentFindings/);
	assert.match(source, /taskCategory === "static"/);
	assert.match(source, /漏洞共 \{allRows\.length\.toLocaleString\(\)\} 条/);
	assert.match(
		source,
		/title:\s*allRows\.length === 0\s*\?\s*"暂无漏洞"\s*:\s*"暂无符合条件的漏洞"/,
	);
	assert.match(source, /row\.original\.route \?/);
});

test("ProjectTaskFindingsDialog 漏洞详情弹窗支持滚动分页并展示完整列", () => {
	const source = readFileSync(dialogPath, "utf8");

	assert.match(source, /max-h-\[88vh\] overflow-hidden flex flex-col/);
	assert.match(source, /flex-1 min-h-0 overflow-y-auto px-6 py-4/);
	assert.match(source, /containerClassName="max-w-full overflow-x-auto"/);
	assert.match(
		source,
		/tableContainerClassName="overflow-x-auto rounded-sm border border-border"/,
	);
	assert.match(source, /tableClassName="min-w-\[1280px\]"/);
	assert.match(source, /fillContainerWidth/);
	assert.match(source, /pageSizeOptions:\s*\[10,\s*20,\s*50\]/);
});

test("ProjectTaskFindingsDialog 静态审计漏洞类型按命中规则展示", () => {
	const source = readFileSync(dialogPath, "utf8");

	assert.match(source, /getStaticAnalysisOpengrepRuleName/);
	assert.match(
		source,
		/const ruleLabel = resolveStaticFindingRuleLabel\(finding\)/,
	);
	assert.match(source, /typeLabel:\s*ruleLabel/);
	assert.match(source, /typeTooltip:\s*typeDisplay\.tooltip \|\| ruleLabel/);
	assert.match(source, /className="block max-w-full truncate text-sm"/);
	assert.match(source, /width:\s*260/);
	assert.match(source, /maxWidth:\s*320/);
});
