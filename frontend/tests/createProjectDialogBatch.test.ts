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

test("appendZipBatchFiles generates deduplicated names and rejects invalid files", async () => {
	const batchModule = await importOrFail<any>(
		"../src/pages/projects/lib/createProjectDialogBatch.ts",
	);

	const result = batchModule.appendZipBatchFiles({
		existingItems: [
			{
				id: "existing-1",
				file: { name: "existing.zip", size: 1 } as File,
				fileName: "existing.zip",
				size: 1,
				derivedName: "demo",
				editableName: "demo",
				status: "idle",
				errorMessage: undefined,
			},
		],
		files: [
			{ name: "demo.zip", size: 100 } as File,
			{ name: "demo.tar.gz", size: 120 } as File,
			{ name: "notes.txt", size: 50 } as File,
		],
		validateFile: (file: File) => {
			if (file.name.endsWith(".txt")) {
				return { valid: false, error: "bad format" };
			}
			return { valid: true };
		},
	});

	assert.deepEqual(
		result.items.map((item: { editableName: string }) => item.editableName),
		["demo", "demo (2)", "demo (3)"],
	);
	assert.deepEqual(result.rejections, [
		{
			fileName: "notes.txt",
			message: "bad format",
		},
	]);
});

test("validateZipBatchItems flags blank names and keeps non-blank names valid", async () => {
	const batchModule = await importOrFail<any>(
		"../src/pages/projects/lib/createProjectDialogBatch.ts",
	);

	const validation = batchModule.validateZipBatchItems([
		{
			id: "item-1",
			file: { name: "alpha.zip", size: 100 } as File,
			fileName: "alpha.zip",
			size: 100,
			derivedName: "alpha",
			editableName: "  ",
			status: "idle",
			errorMessage: undefined,
		},
		{
			id: "item-2",
			file: { name: "beta.zip", size: 100 } as File,
			fileName: "beta.zip",
			size: 100,
			derivedName: "beta",
			editableName: "Beta",
			status: "idle",
			errorMessage: undefined,
		},
	]);

	assert.equal(validation.valid, false);
	assert.deepEqual(validation.invalidItemIds, ["item-1"]);
});
