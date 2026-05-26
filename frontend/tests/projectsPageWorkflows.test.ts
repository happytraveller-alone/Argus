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

test("createZipProjectWorkflow uses atomic zip project creation", async () => {
	const workflows = await importOrFail<any>(
		"../src/pages/projects/data/projectsPageWorkflows.ts",
	);

	const calls: string[] = [];
	const createdProject = { id: "project-1", name: "demo" };
	const file = { name: "demo.zip" } as File;

	const result = await workflows.createZipProjectWorkflow({
		input: { name: "demo", programming_languages: [] },
		file,
		createProjectWithZip: async () => {
			calls.push("create-with-zip");
			return createdProject;
		},
	});

	assert.equal(result.id, "project-1");
	assert.deepEqual(calls, ["create-with-zip"]);
});

test("createZipProjectWorkflow surfaces atomic create failures", async () => {
	const workflows = await importOrFail<any>(
		"../src/pages/projects/data/projectsPageWorkflows.ts",
	);

	const calls: string[] = [];
	const file = { name: "demo.zip" } as File;

	await assert.rejects(async () => {
		await workflows.createZipProjectWorkflow({
			input: { name: "demo", programming_languages: [] },
			file,
			createProjectWithZip: async () => {
				calls.push("create-with-zip");
				throw new Error("zip failed");
			},
		});
	}, /zip failed/);

	assert.deepEqual(calls, ["create-with-zip"]);
});

test("updateProjectWorkflow updates project and only uploads zip when provided", async () => {
	const workflows = await importOrFail<any>(
		"../src/pages/projects/data/projectsPageWorkflows.ts",
	);

	const calls: string[] = [];

	const updated = await workflows.updateProjectWorkflow({
		projectId: "project-1",
		input: { name: "next" },
		zipFile: null,
		updateProject: async () => {
			calls.push("update");
			return { id: "project-1", name: "next" };
		},
		uploadZipFile: async () => {
			calls.push("upload");
			return { success: true };
		},
	});

	assert.equal(updated.name, "next");
	assert.deepEqual(calls, ["update"]);
});

test("createZipProjectsWorkflow processes files sequentially and returns summary", async () => {
	const workflows = await importOrFail<any>(
		"../src/pages/projects/data/projectsPageWorkflows.ts",
	);

	const calls: string[] = [];
	const progress: Array<Record<string, unknown>> = [];
	const files = [
		{ name: "alpha.zip" } as File,
		{ name: "beta.zip" } as File,
	];

	const result = await workflows.createZipProjectsWorkflow({
		items: [
			{ file: files[0], projectName: "Alpha" },
			{ file: files[1], projectName: "Beta" },
		],
		sharedInput: {
			description: "",
			programming_languages: ["TypeScript"],
		},
		createZipProject: async (input: Record<string, unknown>, file: File) => {
			calls.push(`${String(input.name)}:${file.name}`);
			return {
				id: `${String(input.name).toLowerCase()}-project`,
				name: input.name,
			};
		},
		onProgress: (event: Record<string, unknown>) => {
			progress.push(event);
		},
	});

	assert.deepEqual(calls, ["Alpha:alpha.zip", "Beta:beta.zip"]);
	assert.equal(result.total, 2);
	assert.equal(result.successCount, 2);
	assert.equal(result.failureCount, 0);
	assert.deepEqual(
		result.successes.map((project: { name: string }) => project.name),
		["Alpha", "Beta"],
	);
	assert.deepEqual(result.failures, []);
	assert.deepEqual(
		progress.map((event) => `${event.status}:${event.projectName}`),
		[
			"importing:Alpha",
			"indexing:Alpha",
			"success:Alpha",
			"importing:Beta",
			"indexing:Beta",
			"success:Beta",
		],
	);
	assert.deepEqual(
		progress.map((event) => event.completedSteps),
		[0, 1, 2, 2, 3, 4],
	);
});

test("createZipProjectsWorkflow continues after item failure and records failure details", async () => {
	const workflows = await importOrFail<any>(
		"../src/pages/projects/data/projectsPageWorkflows.ts",
	);

	const calls: string[] = [];
	const progress: Array<Record<string, unknown>> = [];
	const files = [
		{ name: "alpha.zip" } as File,
		{ name: "broken.zip" } as File,
		{ name: "gamma.zip" } as File,
	];

	const result = await workflows.createZipProjectsWorkflow({
		items: [
			{ file: files[0], projectName: "Alpha" },
			{ file: files[1], projectName: "Broken" },
			{ file: files[2], projectName: "Gamma" },
		],
		sharedInput: {
			description: "",
			programming_languages: [],
		},
		createZipProject: async (input: Record<string, unknown>, file: File) => {
			calls.push(`${String(input.name)}:${file.name}`);
			if (file.name === "broken.zip") {
				throw new Error("zip failed");
			}
			return {
				id: `${String(input.name).toLowerCase()}-project`,
				name: input.name,
			};
		},
		onProgress: (event: Record<string, unknown>) => {
			progress.push(event);
		},
	});

	assert.deepEqual(calls, ["Alpha:alpha.zip", "Broken:broken.zip", "Gamma:gamma.zip"]);
	assert.equal(result.total, 3);
	assert.equal(result.successCount, 2);
	assert.equal(result.failureCount, 1);
	assert.deepEqual(
		result.successes.map((project: { name: string }) => project.name),
		["Alpha", "Gamma"],
	);
	assert.deepEqual(result.failures, [
		{
			fileName: "broken.zip",
			projectName: "Broken",
			message: "zip failed",
		},
	]);
	assert.deepEqual(
		progress.map((event) => `${event.status}:${event.projectName}`),
		[
			"importing:Alpha",
			"indexing:Alpha",
			"success:Alpha",
			"importing:Broken",
			"indexing:Broken",
			"failed:Broken",
			"importing:Gamma",
			"indexing:Gamma",
			"success:Gamma",
		],
	);
});
