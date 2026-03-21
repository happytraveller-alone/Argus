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

test("projects selectors calculate responsive project page size from container metrics", async () => {
	const selectors = await importOrFail<any>(
		"../src/pages/projects/lib/projectsPageSelectors.ts",
	);

	assert.equal(
		selectors.calculateResponsiveProjectsPageSize({
			containerHeight: 960,
			tableHeaderHeight: 48,
			paginationHeight: 64,
			rowHeight: 84,
		}),
		10,
	);
	assert.equal(
		selectors.calculateResponsiveProjectsPageSize({
			containerHeight: 620,
			tableHeaderHeight: 48,
			paginationHeight: 64,
			rowHeight: 84,
		}),
		6,
	);
	assert.equal(
		selectors.calculateResponsiveProjectsPageSize({
			containerHeight: 120,
			tableHeaderHeight: 48,
			paginationHeight: 64,
			rowHeight: 84,
		}),
		1,
	);
});

test("projects view model renders archive size and zero stats when metrics pending", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	const projects = [
		{
			id: "p1",
			name: "Pending Metrics",
			detailPath: "",
			description: "",
			source_type: "zip",
			repository_url: undefined,
			repository_type: "other",
			default_branch: "main",
			programming_languages: "ts",
			owner_id: "u1",
			is_active: true,
			created_at: "2024-01-01T00:00:00Z",
				updated_at: "2024-01-01T00:00:00Z",
				management_metrics: {
					status: "pending",
					archive_size_bytes: 4096,
				},
			},
		];

	const viewModel = builder.buildProjectsPageViewModel({
		loading: false,
		filteredProjects: projects,
		pagedProjects: projects,
		projectPage: 1,
		totalProjectPages: 1,
		projectDetailFrom: "/",
		searchTerm: "",
		searchPlaceholder: "Search",
	});

	assert.equal(viewModel.rows[0].sizeText, "4.00 Kb");
	assert.equal(viewModel.rows[0].metricsStatus, "pending");
	assert.equal(viewModel.rows[0].executionStats.completed, 0);
	assert.equal(viewModel.rows[0].executionStats.running, 0);
	assert.equal(viewModel.rows[0].vulnerabilityStats.critical, 0);
	assert.equal(viewModel.rows[0].vulnerabilityStats.low, 0);
});

test("projects view model exposes metrics when ready", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	const projects = [
		{
			id: "p-ready",
			name: "Ready Project",
			description: "",
			source_type: "zip",
			repository_url: undefined,
			repository_type: "other",
			default_branch: "main",
			programming_languages: "ts",
			owner_id: "u1",
			is_active: true,
			created_at: "2024-01-01T00:00:00Z",
			updated_at: "2024-01-01T00:00:00Z",
			management_metrics: {
				status: "ready",
				archive_size_bytes: 2_621_440,
				completed_tasks: 5,
				running_tasks: 1,
				total_tasks: 8,
				agent_tasks: 3,
				opengrep_tasks: 1,
				gitleaks_tasks: 1,
				bandit_tasks: 1,
				phpstan_tasks: 0,
				critical: 2,
				high: 3,
				medium: 4,
				low: 1,
				created_at: "2024-01-01T00:00:00Z",
				updated_at: "2024-01-01T00:00:00Z",
			},
		},
	];

	const viewModel = builder.buildProjectsPageViewModel({
		loading: false,
		filteredProjects: projects,
		pagedProjects: projects,
		projectPage: 1,
		totalProjectPages: 1,
		projectDetailFrom: "/",
		searchTerm: "",
		searchPlaceholder: "Search",
	});
	const row = viewModel.rows[0];
	assert.equal(row.sizeText, "2.50 Mb");
	assert.equal(row.executionStats.completed, 5);
	assert.equal(row.vulnerabilityStats.critical, 2);
	assert.equal(row.metricsStatus, "ready");
});

test("projects view model exposes vulnerability stats and browse guards", async () => {
	const builder = await importOrFail<any>(
		"../src/pages/projects/lib/buildProjectsPageViewModel.ts",
	);

	const projects = [
		{
			id: "p-guards",
			name: "Guarded Project",
			description: "",
			source_type: "repository",
			repository_url: "https://example.com/repo.git",
			repository_type: "other",
			default_branch: "main",
			programming_languages: "ts",
			owner_id: "u1",
			is_active: true,
			created_at: "2024-01-01T00:00:00Z",
			updated_at: "2024-01-01T00:00:00Z",
			management_metrics: {
				status: "ready",
				archive_size_bytes: 512,
				completed_tasks: 0,
				running_tasks: 0,
				total_tasks: 0,
				agent_tasks: 0,
				opengrep_tasks: 0,
				gitleaks_tasks: 0,
				bandit_tasks: 0,
				phpstan_tasks: 0,
				critical: 0,
				high: 1,
				medium: 2,
				low: 3,
				created_at: "2024-01-01T00:00:00Z",
				updated_at: "2024-01-01T00:00:00Z",
			},
		},
	];

	const viewModel = builder.buildProjectsPageViewModel({
		loading: false,
		filteredProjects: projects,
		pagedProjects: projects,
		projectPage: 1,
		totalProjectPages: 1,
		projectDetailFrom: "/projects",
		searchTerm: "",
		searchPlaceholder: "Search",
	});

	const row = viewModel.rows[0];
	assert.equal(row.vulnerabilityStats.high, 1);
	assert.equal(row.vulnerabilityStats.medium, 2);
	assert.equal(row.vulnerabilityStats.low, 3);
	assert.equal(row.actions.canBrowseCode, false);
	assert.equal(
		row.actions.browseCodeDisabledReason,
		"仅 ZIP 类型项目支持代码浏览",
	);
});
