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

test("normalizeProjectFileContentResponse normalizes variant payloads to a stable shape", async () => {
	const database = await importOrFail<any>("../src/shared/api/database.ts");

	const normalized = database.normalizeProjectFileContentResponse(
		{
			filePath: "src/main.ts",
			text: "export const answer = 42;",
			file_size: "25",
			charset: "utf-8",
			isText: true,
		},
		{ requestedFilePath: "src/ignored.ts" },
	);

	assert.deepEqual(normalized, {
		file_path: "src/main.ts",
		content: "export const answer = 42;",
		size: 25,
		encoding: "utf-8",
		is_text: true,
	});
});

test("normalizeProjectFileContentResponse returns null when is_text is missing or invalid", async () => {
	const database = await importOrFail<any>("../src/shared/api/database.ts");

	const missingIsText = database.normalizeProjectFileContentResponse({
		file_path: "src/main.ts",
		content: "const x = 1;",
		size: 13,
		encoding: "utf-8",
	});
	const invalidIsText = database.normalizeProjectFileContentResponse({
		file_path: "src/main.ts",
		content: "const x = 1;",
		size: 13,
		encoding: "utf-8",
		is_text: "yes",
	});

	assert.equal(missingIsText, null);
	assert.equal(invalidIsText, null);
});

test("normalizeProjectFileContentResponse treats binary-like payloads as non-highlightable without is_text", async () => {
	const database = await importOrFail<any>("../src/shared/api/database.ts");

	const missingIsTextBinary = database.normalizeProjectFileContentResponse({
		file_path: "assets/logo.png",
		content: "AAECAwQ=",
		size: 8,
		encoding: "base64",
	});
	const explicitBinary = database.normalizeProjectFileContentResponse({
		file_path: "assets/logo.png",
		content: "AAECAwQ=",
		size: 8,
		encoding: "base64",
		is_text: false,
	});

	assert.equal(missingIsTextBinary, null);
	assert.deepEqual(explicitBinary, {
		file_path: "assets/logo.png",
		content: "AAECAwQ=",
		size: 8,
		encoding: "base64",
		is_text: false,
	});
});

