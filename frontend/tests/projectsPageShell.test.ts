import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const projectsPagePath = path.join(
	frontendDir,
	"src/pages/projects/ProjectsPage.tsx",
);

test("ProjectsPage 的项目浏览外层容器不再渲染 cyber-card 外框", () => {
	const source = readFileSync(projectsPagePath, "utf8");

	assert.match(source, /id="project-browser"/);
	assert.doesNotMatch(
		source,
		/id="project-browser"[\s\S]*className="cyber-card p-4 relative z-10 flex flex-col flex-1 min-h-\[65vh\]"/,
	);
});

test("ProjectsPage 使用响应式分页容量而不是固定项目数量", () => {
	const source = readFileSync(projectsPagePath, "utf8");

	assert.match(source, /ResizeObserver/);
	assert.match(source, /calculateResponsiveProjectsPageSize/);
	assert.match(source, /resolveAnchoredProjectsPage/);
	assert.match(source, /resolveProjectsFirstVisibleIndex/);
	assert.doesNotMatch(
		source,
		/paginateItems\(filteredProjects,\s*browser\.projectPage,\s*PROJECT_PAGE_SIZE\)/,
	);
});

test("ProjectsTable 为项目页传入专用表格容器样式以移除内层滑框", () => {
	const projectsTablePath = path.join(
		frontendDir,
		"src/pages/projects/components/ProjectsTable.tsx",
	);
	const source = readFileSync(projectsTablePath, "utf8");

	assert.match(source, /containerClassName="overflow-visible"/);
	assert.match(source, /tableContainerClassName="overflow-visible border-0 rounded-none"/);
	assert.doesNotMatch(source, /tableClassName="min-w-\[1360px\]"/);
});

test("ProjectsPage wires delete-project action with confirm copy and refresh flow", () => {
	const source = readFileSync(projectsPagePath, "utf8");

	assert.match(source, /async function handleDeleteProject\(projectId: string, projectName: string\)/);
	assert.match(source, /window\.confirm\(/);
	assert.match(source, /与该项目相关的扫描任务也会一并删除/);
	assert.match(source, /await data\.deleteProject\(projectId\)/);
	assert.match(source, /onDeleteProject=\{handleDeleteProject\}/);
	assert.match(source, /deletingProjectId=\{deletingProjectId\}/);
});

test("ProjectsTable source includes delete-project action button", () => {
	const projectsTablePath = path.join(
		frontendDir,
		"src/pages/projects/components/ProjectsTable.tsx",
	);
	const source = readFileSync(projectsTablePath, "utf8");

	assert.match(source, /onDeleteProject: \(projectId: string, projectName: string\) => void;/);
	assert.match(source, /删除项目/);
	assert.match(source, /删除中\.\.\./);
});
