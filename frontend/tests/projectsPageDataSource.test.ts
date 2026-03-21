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

test("api projects data source fetches batches with metrics flag", async () => {
	const apiFactory = await importOrFail<any>(
		"../src/pages/projects/data/createApiProjectsPageDataSource.ts",
	);

	const calls: Array<Record<string, unknown>> = [];
	const source = apiFactory.createApiProjectsPageDataSource({
		projectFetchBatchSize: 2,
		api: {
			getProjects: async ({ skip = 0, includeMetrics = false }) => {
				calls.push({ skip, includeMetrics });
				const all = [
					{ id: "p1", created_at: "2024-01-01T00:00:00Z" },
					{ id: "p2", created_at: "2024-01-02T00:00:00Z" },
					{ id: "p3", created_at: "2024-01-03T00:00:00Z" },
				];
				return all.slice(skip, skip + 2);
			},
			createProject: async () => ({ id: "new-project" }),
			createProjectWithZip: async () => ({ id: "new-zip-project" }),
			updateProject: async () => ({ id: "updated-project" }),
		},
	});

	const projects = await source.listProjects();

	assert.deepEqual(projects.map((project: any) => project.id), ["p3", "p2", "p1"]);
	assert.equal(calls.length, 2);
	assert.equal(calls.every((call) => call.includeMetrics === true), true);
});

test("mock projects data source exposes minimal surface", async () => {
	const mockFactory = await importOrFail<any>(
		"../src/pages/projects/data/createMockProjectsPageDataSource.ts",
	);

	const source = mockFactory.createMockProjectsPageDataSource();
	const projects = await source.listProjects();
	assert.equal(typeof source.createProject, "function");
	assert.equal(Array.isArray(projects), true);
	const updated = await source.updateProject(projects[0].id, { name: "Renamed" });
	assert.equal(updated.name, "Renamed");
});

test("api projects data source keeps the trimmed projects-page surface", async () => {
	const apiFactory = await importOrFail<any>(
		"../src/pages/projects/data/createApiProjectsPageDataSource.ts",
	);

	const source = apiFactory.createApiProjectsPageDataSource({
		api: {
			getProjects: async () => [],
			createProject: async () => ({ id: "new-project" }),
			createProjectWithZip: async () => ({ id: "new-zip-project" }),
			updateProject: async () => ({ id: "updated-project" }),
		},
	});

	assert.equal("getProjectTaskPool" in source, false);
	assert.equal("getProjectLanguageStats" in source, false);
	assert.equal("getProjectZipMeta" in source, false);
});
