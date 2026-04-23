import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

test("ProjectDetail 最近任务工具栏只保留搜索并隐藏筛选重置密度", () => {
	const source = readFileSync(
		path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src/pages/ProjectDetail.tsx"),
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
		path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src/pages/ProjectDetail.tsx"),
		"utf8",
	);

	assert.match(source, /id:\s*"sequence"/);
	assert.match(source, /header:\s*"序号"/);
	assert.match(source, /pageIndex \* pagination\.pageSize \+ pageRowIndex \+ 1/);
});

test("ProjectDetail 最近任务状态 badge 统一使用非加粗字重", () => {
	const source = readFileSync(
		path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src/pages/ProjectDetail.tsx"),
		"utf8",
	);

	assert.match(source, /cyber-badge-success font-normal/);
	assert.match(source, /cyber-badge-info font-normal/);
	assert.match(source, /cyber-badge-danger font-normal/);
	assert.match(source, /cyber-badge-muted font-normal/);
	assert.match(source, /border-orange-500\/30 font-normal/);
});
