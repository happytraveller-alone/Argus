import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectDetailSource = readFileSync(
	path.join(
		path.dirname(fileURLToPath(import.meta.url)),
		"..",
		"src/pages/ProjectDetail.tsx",
	),
	"utf8",
);

test("ProjectDetail 最近任务标题行展示搜索并关闭表格内置工具栏", () => {
	assert.match(
		projectDetailSource,
		/placeholder="搜索任务 ID、类型或创建时间"/,
	);
	assert.match(
		projectDetailSource,
		/startIcon=\{<Search className="h-4 w-4" \/>\}/,
	);
	assert.match(
		projectDetailSource,
		/className="h-9 border-border\/60 bg-muted\/40 focus:bg-muted\/40"/,
	);
	assert.match(projectDetailSource, /toolbar=\{false\}/);
	assert.doesNotMatch(
		projectDetailSource,
		/toolbar:\s*\{[\s\S]*filters:\s*\[[\s\S]*columnId:\s*"status"/,
	);
	assert.doesNotMatch(projectDetailSource, /showColumnVisibility:\s*false/);
	assert.doesNotMatch(projectDetailSource, /showDensityToggle:\s*false/);
	assert.doesNotMatch(projectDetailSource, /showReset:\s*false/);
});

test("ProjectDetail 最近任务表格在最左侧增加连续序号列", () => {
	assert.match(projectDetailSource, /id:\s*"sequence"/);
	assert.match(projectDetailSource, /header:\s*"序号"/);
	assert.match(
		projectDetailSource,
		/pageIndex \* pagination\.pageSize \+ pageRowIndex \+ 1/,
	);
});

test("ProjectDetail 最近任务状态 badge 统一使用非加粗字重", () => {
	assert.match(projectDetailSource, /cyber-badge-success font-normal/);
	assert.match(projectDetailSource, /cyber-badge-info font-normal/);
	assert.match(projectDetailSource, /cyber-badge-danger font-normal/);
	assert.match(projectDetailSource, /cyber-badge-muted font-normal/);
	assert.match(projectDetailSource, /border-orange-500\/30 font-normal/);
});
