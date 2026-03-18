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

test("save-then-test flow saves first, then tests, and returns both results", async () => {
	const helpers = await importOrFail<any>(
		"../src/components/scan-config/intelligentEngineActionFlow.ts",
	);
	const calls: string[] = [];

	const result = await helpers.runSaveThenTestAction({
		save: async () => {
			calls.push("save");
			return { saved: true };
		},
		test: async () => {
			calls.push("test");
			return { success: true, message: "ok" };
		},
	});

	assert.deepEqual(calls, ["save", "test"]);
	assert.deepEqual(result, {
		saveResult: { saved: true },
		testResult: { success: true, message: "ok" },
	});
});

test("save-then-test flow does not test when save fails", async () => {
	const helpers = await importOrFail<any>(
		"../src/components/scan-config/intelligentEngineActionFlow.ts",
	);
	const calls: string[] = [];
	const saveError = new Error("save failed");

	await assert.rejects(
		helpers.runSaveThenTestAction({
			save: async () => {
				calls.push("save");
				throw saveError;
			},
			test: async () => {
				calls.push("test");
				return { success: true };
			},
		}),
		saveError,
	);

	assert.deepEqual(calls, ["save"]);
});
