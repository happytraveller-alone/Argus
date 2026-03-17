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
			createProjectWithZip: async () => ({ id: "new-zip-project" }),
			updateProject: async () => ({ id: "updated-project" }),
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
		getZipFileInfo: async () => ({
			has_file: true,
			file_size: 2_621_440,
			original_filename: "p1.zip",
		}),
		uploadZipFile: async () => ({ success: true }),
	});

	const projects = await source.listProjects();
	const taskPool = await source.getProjectTaskPool("p1");
	const zipMeta = await source.getProjectZipMeta("p1");

	assert.deepEqual(projects.map((project: any) => project.id), ["p3", "p2", "p1"]);
	assert.equal(taskPool.auditTasks.length, 1);
	assert.equal(taskPool.agentTasks.length, 1);
	assert.equal(taskPool.opengrepTasks.length, 1);
	assert.equal(taskPool.gitleaksTasks.length, 1);
	assert.equal(taskPool.banditTasks.length, 1);
	assert.equal(taskPool.phpstanTasks.length, 1);
	assert.equal(zipMeta.has_file, true);
	assert.equal(zipMeta.file_size, 2_621_440);
});

test("mock projects data source exposes the same data source surface", async () => {
	const mockFactory = await importOrFail<any>(
		"../src/pages/projects/data/createMockProjectsPageDataSource.ts",
	);

	const source = mockFactory.createMockProjectsPageDataSource();
	const projects = await source.listProjects();
	const taskPool = await source.getProjectTaskPool(projects[0].id);
	const zipMeta = await source.getProjectZipMeta(projects[0].id);

	assert.equal(typeof source.createProject, "function");
	assert.equal(Array.isArray(projects), true);
	assert.equal(Array.isArray(taskPool.auditTasks), true);
	assert.equal(typeof zipMeta.has_file, "boolean");
});

test("legacy projects data source creates zip projects via atomic api", async () => {
	const legacyFactory = await importOrFail<any>(
		"../src/pages/projects/datasource/createApiProjectsPageDataSource.ts",
	);
	const databaseModule = await importOrFail<any>(
		"../src/shared/api/database.ts",
	);

	const originalApi = {
		createProjectWithZip: databaseModule.api.createProjectWithZip,
	};
	const calls = {
		createProjectWithZip: 0,
	};

	databaseModule.api.createProjectWithZip = async () => {
		calls.createProjectWithZip += 1;
		return { id: "zip-project" };
	};

	try {
		const source = legacyFactory.createApiProjectsPageDataSource();

		await source.createZipProject(
			{ name: "project-1", programming_languages: [] },
			{ name: "project-1.zip" } as File,
		);

		assert.equal(calls.createProjectWithZip, 1);
	} finally {
		databaseModule.api.createProjectWithZip = originalApi.createProjectWithZip;
	}
});
