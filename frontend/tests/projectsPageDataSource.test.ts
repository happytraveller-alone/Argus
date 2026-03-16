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

test("api projects data source loads paginated projects and task pools", async () => {
	const apiFactory = await importOrFail<any>(
		"../src/pages/projects/data/createApiProjectsPageDataSource.ts",
	);

	const source = apiFactory.createApiProjectsPageDataSource({
		projectFetchBatchSize: 2,
		api: {
			getProjects: async ({ skip = 0 }: { skip?: number }) => {
				const all = [
					{ id: "p1", created_at: "2024-01-01T00:00:00Z" },
					{ id: "p2", created_at: "2024-01-02T00:00:00Z" },
					{ id: "p3", created_at: "2024-01-03T00:00:00Z" },
				];
				return all.slice(skip, skip + 2);
			},
			getAuditTasks: async () => [{ id: "a1", status: "completed" }],
			createProject: async () => ({ id: "new-project" }),
			updateProject: async () => ({ id: "updated-project" }),
			deleteProject: async () => {},
			restoreProject: async () => {},
		},
		getAgentTasks: async () => [{ id: "agt-1", status: "running" }],
		getOpengrepScanTasks: async () => [{ id: "o1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:00Z" }],
		getGitleaksScanTasks: async () => [{ id: "g1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:01Z" }],
		getBanditScanTasks: async () => [{ id: "b1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:02Z" }],
		getPhpstanScanTasks: async () => [{ id: "p1", project_id: "p1", status: "completed", created_at: "2024-01-01T00:00:03Z" }],
		getProjectInfo: async () => ({
			status: "ready",
			language_info: {
				total: 200,
				total_files: 10,
				languages: {
					typescript: { proportion: 0.7, loc_number: 140, files_count: 5 },
				},
			},
		}),
		uploadZipFile: async () => ({ success: true }),
	});

	const projects = await source.listProjects({ includeDeleted: true });
	const taskPool = await source.getProjectTaskPool("p1");
	const languageStats = await source.getProjectLanguageStats("p1");

	assert.deepEqual(projects.map((project: any) => project.id), ["p3", "p2", "p1"]);
	assert.equal(taskPool.auditTasks.length, 1);
	assert.equal(taskPool.agentTasks.length, 1);
	assert.equal(taskPool.opengrepTasks.length, 1);
	assert.equal(taskPool.gitleaksTasks.length, 1);
	assert.equal(taskPool.banditTasks.length, 1);
	assert.equal(taskPool.phpstanTasks.length, 1);
	assert.equal(languageStats.status, "ready");
	assert.equal(languageStats.totalFiles, 10);
});

test("mock projects data source exposes the same data source surface", async () => {
	const mockFactory = await importOrFail<any>(
		"../src/pages/projects/data/createMockProjectsPageDataSource.ts",
	);

	const source = mockFactory.createMockProjectsPageDataSource();
	const projects = await source.listProjects({ includeDeleted: true });
	const taskPool = await source.getProjectTaskPool(projects[0].id);
	const stats = await source.getProjectLanguageStats(projects[0].id);

	assert.equal(typeof source.createProject, "function");
	assert.equal(Array.isArray(projects), true);
	assert.equal(Array.isArray(taskPool.auditTasks), true);
	assert.match(stats.status, /loading|pending|ready|failed|unsupported|empty/);
});

test("legacy projects data source toggles project status via delete and restore endpoints", async () => {
	const legacyFactory = await importOrFail<any>(
		"../src/pages/projects/datasource/createApiProjectsPageDataSource.ts",
	);
	const databaseModule = await importOrFail<any>(
		"../src/shared/api/database.ts",
	);

	const originalApi = {
		updateProject: databaseModule.api.updateProject,
		deleteProject: databaseModule.api.deleteProject,
		restoreProject: databaseModule.api.restoreProject,
	};
	const calls = {
		updateProject: 0,
		deleteProject: 0,
		restoreProject: 0,
	};

	databaseModule.api.updateProject = async () => {
		calls.updateProject += 1;
		return { id: "updated-project" };
	};
	databaseModule.api.deleteProject = async () => {
		calls.deleteProject += 1;
	};
	databaseModule.api.restoreProject = async () => {
		calls.restoreProject += 1;
	};

	try {
		const source = legacyFactory.createApiProjectsPageDataSource();

		await source.disableProject("project-1");
		await source.enableProject("project-1");

		assert.equal(calls.updateProject, 0);
		assert.equal(calls.deleteProject, 1);
		assert.equal(calls.restoreProject, 1);
	} finally {
		databaseModule.api.updateProject = originalApi.updateProject;
		databaseModule.api.deleteProject = originalApi.deleteProject;
		databaseModule.api.restoreProject = originalApi.restoreProject;
	}
});
