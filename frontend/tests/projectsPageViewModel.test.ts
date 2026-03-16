import test from "node:test";
import assert from "node:assert/strict";

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected helper module ${relativePath} to exist: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
}

test("projects selectors filter by name and description only", async () => {
	const selectors = await importOrFail<any>(
		"../src/pages/projects/lib/projectsPageSelectors.ts",
	);

	const projects = [
		{
			id: "1",
			name: "Alpha Repo",
			description: "Handles login",
			repository_url: "https://example.com/alpha.git",
		},
		{
			id: "2",
			name: "Beta Service",
			description: "Contains payment flow",
			repository_url: "https://example.com/beta.git",
		},
	];

	assert.deepEqual(
		selectors.filterProjects(projects, "payment").map((project: any) => project.id),
		["2"],
	);
	assert.deepEqual(
		selectors.filterProjects(projects, "alpha.git").map((project: any) => project.id),
		[],
	);
	assert.equal(selectors.filterProjects(projects, "").length, 2);
});

test("projects selectors build compact pagination items with ellipsis", async () => {
	const selectors = await importOrFail<any>(
		"../src/pages/projects/lib/projectsPageSelectors.ts",
	);

	assert.deepEqual(selectors.buildPaginationItems(3, 5), [1, 2, 3, 4, 5]);
	assert.deepEqual(selectors.buildPaginationItems(5, 10), [1, "ellipsis", 4, 5, 6, "ellipsis", 10]);
});

test("projects selectors expose current-page selection summary", async () => {
	const selectors = await importOrFail<any>(
		"../src/pages/projects/lib/projectsPageSelectors.ts",
	);

	const summary = selectors.getCurrentPageSelectionState({
		currentPageProjectIds: ["a", "b", "c"],
		selectedProjectIds: new Set(["a", "c"]),
	});

	assert.equal(summary.isAllSelected, false);
	assert.equal(summary.isSomeSelected, true);
	assert.equal(summary.selectedCount, 2);
});

test("projects view model utilities build project size text and execution stats", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	assert.equal(
		builder.getProjectSizeText({
			status: "ready",
			total: 12345,
			totalFiles: 88,
			slices: [],
		}),
		"88 文件 / 12,345 行",
	);
	assert.equal(
		builder.getProjectSizeText({
			status: "pending",
			total: 0,
			totalFiles: 0,
			slices: [],
		}),
		"统计中...",
	);

	const stats = builder.getProjectExecutionStats({
		auditTasks: [{ status: "completed" }, { status: "running" }],
		agentTasks: [{ status: "pending" }, { status: "completed" }],
		opengrepTasks: [
			{ id: "o1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:00Z" },
		],
		gitleaksTasks: [
			{ id: "g1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:01Z" },
		],
	});

	assert.deepEqual(stats, { completed: 3, running: 2 });
});

test("projects view model derives status toggle metadata from project active state", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	const makeProject = (overrides: Record<string, unknown>) => ({
		id: "project-id",
		name: "Project Name",
		description: "Project Description",
		source_type: "zip",
		repository_url: undefined,
		repository_type: "other",
		default_branch: "main",
		programming_languages: "TypeScript",
		owner_id: "user-1",
		is_active: true,
		created_at: "2024-01-01T00:00:00Z",
		updated_at: "2024-01-01T00:00:00Z",
		...overrides,
	});

	const viewModel = builder.buildProjectsPageViewModel({
		loading: false,
		filteredProjects: [
			makeProject({ id: "p1", name: "Enabled Project", is_active: true }),
			makeProject({
				id: "p2",
				name: "Disabled Project",
				is_active: false,
				source_type: "repository",
			}),
		],
		pagedProjects: [
			makeProject({ id: "p1", name: "Enabled Project", is_active: true }),
			makeProject({
				id: "p2",
				name: "Disabled Project",
				is_active: false,
				source_type: "repository",
			}),
		],
		projectPage: 1,
		totalProjectPages: 1,
		selectedProjectIds: new Set(),
		projectTaskPoolsMap: {},
		projectLanguageStatsMap: {},
		projectDetailFrom: "/projects",
		searchTerm: "",
		searchPlaceholder: "搜索项目",
	});

	assert.deepEqual(
		viewModel.rows.map((row: any) => ({
			id: row.id,
			statusLabel: row.statusLabel,
			statusToggleLabel: row.statusToggle.label,
			statusToggleAction: row.statusToggle.action,
			canCreateScan: row.actions.canCreateScan,
			canBrowseCode: row.actions.canBrowseCode,
			browseCodePath: row.actions.browseCodePath,
			browseCodeDisabledReason: row.actions.browseCodeDisabledReason,
		})),
		[
			{
				id: "p1",
				statusLabel: "启用",
				statusToggleLabel: "禁用",
				statusToggleAction: "disable",
				canCreateScan: true,
				canBrowseCode: true,
				browseCodePath: "/projects/p1/code-browser",
				browseCodeDisabledReason: null,
			},
			{
				id: "p2",
				statusLabel: "禁用",
				statusToggleLabel: "启用",
				statusToggleAction: "enable",
				canCreateScan: false,
				canBrowseCode: false,
				browseCodePath: "/projects/p2/code-browser",
				browseCodeDisabledReason: "仅 ZIP 类型项目支持代码浏览",
			},
		],
	);
});
