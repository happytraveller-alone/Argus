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
