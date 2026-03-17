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

test("projects view model utilities build project size text and execution stats", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	assert.equal(
		builder.getProjectSizeText("zip", {
			has_file: true,
			file_size: 2_621_440,
		}),
		"2.50 Mb",
	);
	assert.equal(
		builder.getProjectSizeText("zip", {
			has_file: true,
			file_size: 512,
		}),
		"512 B",
	);
	assert.equal(
		builder.getProjectSizeText("zip", {
			has_file: true,
			file_size: 7680,
		}),
		"7.50 Kb",
	);
	assert.equal(
		builder.getProjectSizeText("zip", {
			has_file: false,
		}),
		"-",
	);
	assert.equal(
		builder.getProjectSizeText("repository", {
			has_file: true,
			file_size: 2_621_440,
		}),
		"-",
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

test("projects view model exposes constant availability status and browse guards", async () => {
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

	const projectTaskPoolsMap = {
		p1: {
			status: "ready",
			auditTasks: [],
			agentTasks: [
				{
					project_id: "p1",
					status: "completed",
					critical_count: 1,
					high_count: 2,
					medium_count: 3,
					low_count: 4,
					verified_count: 6,
					name: "[INTELLIGENT] Enabled Project",
					description: "",
				},
			],
			opengrepTasks: [
				{
					id: "op-1",
					project_id: "p1",
					status: "completed",
					created_at: "2024-01-01T00:00:00Z",
					total_findings: 9,
					error_count: 2,
					warning_count: 1,
				},
			],
			gitleaksTasks: [
				{
					id: "gl-1",
					project_id: "p1",
					status: "completed",
					created_at: "2024-01-01T00:00:01Z",
					total_findings: 5,
				},
			],
			banditTasks: [
				{
					id: "bd-1",
					project_id: "p1",
					status: "completed",
					created_at: "2024-01-01T00:00:02Z",
					high_count: 2,
					medium_count: 4,
					low_count: 6,
				},
			],
			phpstanTasks: [
				{
					id: "ps-1",
					project_id: "p1",
					status: "completed",
					created_at: "2024-01-01T00:00:03Z",
					total_findings: 7,
				},
			],
		},
		p2: {
			status: "ready",
			auditTasks: [],
			agentTasks: [],
			opengrepTasks: [],
			gitleaksTasks: [],
			banditTasks: [],
			phpstanTasks: [],
		},
	};

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
			rowNumber: row.rowNumber,
			canCreateScan: row.actions.canCreateScan,
			canBrowseCode: row.actions.canBrowseCode,
			browseCodePath: row.actions.browseCodePath,
			browseCodeDisabledReason: row.actions.browseCodeDisabledReason,
		})),
		[
			{
				id: "p1",
				statusLabel: "可用",
				rowNumber: undefined,
				canCreateScan: true,
				canBrowseCode: true,
				browseCodePath: "/projects/p1/code-browser",
				browseCodeDisabledReason: null,
			},
			{
				id: "p2",
				statusLabel: "可用",
				rowNumber: undefined,
				canCreateScan: true,
				canBrowseCode: false,
				browseCodePath: "/projects/p2/code-browser",
				browseCodeDisabledReason: "仅 ZIP 类型项目支持代码浏览",
			},
		],
	);
	assert.equal("selection" in viewModel, false);
});
