import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("ProjectDetail 最近任务工具栏只保留搜索并隐藏筛选重置密度", () => {
	const source = readFileSync(
		"/home/xyf/AuditTool/frontend/src/pages/ProjectDetail.tsx",
		"utf8",
	);

	assert.match(source, /searchPlaceholder:\s*"搜索任务 ID、类型或创建时间"/);
	assert.match(source, /showColumnVisibility:\s*false/);
	assert.match(source, /showDensityToggle:\s*false/);
	assert.match(source, /showReset:\s*false/);
	assert.doesNotMatch(
		source,
		/toolbar:\s*\{[\s\S]*filters:\s*\[[\s\S]*columnId:\s*"status"/,
	);
});

test("ProjectDetail 最近任务表格在最左侧增加连续序号列", () => {
	const source = readFileSync(
		"/home/xyf/AuditTool/frontend/src/pages/ProjectDetail.tsx",
		"utf8",
	);

	assert.match(source, /id:\s*"sequence"/);
	assert.match(source, /header:\s*"序号"/);
	assert.match(source, /pageIndex \* pagination\.pageSize \+ pageRowIndex \+ 1/);
});
