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

test("resolveCodeLanguageFromPath resolves special filenames before extensions", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	assert.deepEqual(highlight.resolveCodeLanguageFromPath("nginx.conf"), {
		languageKey: "nginx",
		languageLabel: "Nginx",
	});
	assert.deepEqual(highlight.resolveCodeLanguageFromPath("Dockerfile"), {
		languageKey: "dockerfile",
		languageLabel: "Dockerfile",
	});
});

test("resolveCodeLanguageFromPath keeps .env and .env.* as plain text", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	assert.equal(highlight.resolveCodeLanguageFromPath(".env"), null);
	assert.equal(highlight.resolveCodeLanguageFromPath(".env.local"), null);
});

test("resolveCodeLanguageFromPath resolves TSX and JSONC mappings", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	assert.deepEqual(highlight.resolveCodeLanguageFromPath("src/App.tsx"), {
		languageKey: "tsx",
		languageLabel: "TSX",
	});
	assert.deepEqual(highlight.resolveCodeLanguageFromPath("tsconfig.jsonc"), {
		languageKey: "json",
		languageLabel: "JSONC",
	});
});

test("buildCodeHighlightResult returns path-not-supported for unknown extensions", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const result = await highlight.buildCodeHighlightResult({
		filePath: "docs/notes.abcxyz",
		content: "hello world",
	});

	assert.equal(result.status, "plain-text");
	assert.equal(result.fallbackReason, "path-not-supported");
	assert.equal(result.languageKey, null);
	assert.equal(result.languageLabel, null);
	assert.equal(result.lines.length, 1);
	assert.equal(result.lines[0].content, "hello world");
});

test("buildCodeHighlightResult applies content-too-large fallback at 200_001 chars", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const result = await highlight.buildCodeHighlightResult({
		filePath: "src/main.ts",
		content: "x".repeat(200_001),
	});

	assert.equal(result.status, "plain-text");
	assert.equal(result.fallbackReason, "content-too-large");
});

test("buildCodeHighlightResult applies line-count-too-large fallback at 5_001 lines", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const result = await highlight.buildCodeHighlightResult({
		filePath: "src/main.ts",
		content: `${"line\n".repeat(5_000)}line`,
	});

	assert.equal(result.status, "plain-text");
	assert.equal(result.fallbackReason, "line-count-too-large");
	assert.equal(result.lines.length, 5_001);
});

test("buildCodeHighlightResult token segmentation preserves total line count", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const content = ["const alpha = 1;", "const beta = 2;", "return alpha + beta;"].join("\n");
	const result = await highlight.buildCodeHighlightResult({
		filePath: "src/math.ts",
		content,
	});

	assert.equal(result.status, "highlighted");
	assert.equal(result.lines.length, 3);
	assert.equal(
		result.lines.every((line: any) => typeof line.content === "string"),
		true,
	);
});

test("buildCodeHighlightResult token segmentation preserves empty lines", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const content = ["const first = 1;", "", "const second = 2;"].join("\n");
	const result = await highlight.buildCodeHighlightResult({
		filePath: "src/empty-lines.ts",
		content,
	});

	assert.equal(result.status, "highlighted");
	assert.equal(result.lines.length, 3);
	assert.equal(result.lines[1].content, "");
});

test("buildCodeHighlightResult token segmentation preserves trailing newline behavior", async () => {
	const highlight = await importOrFail<any>(
		"../src/shared/code-highlighting/index.ts",
	);

	const content = "const done = true;\n";
	const result = await highlight.buildCodeHighlightResult({
		filePath: "src/trailing.ts",
		content,
	});

	assert.equal(result.status, "highlighted");
	assert.equal(result.lines.length, 2);
	assert.equal(result.lines[1].content, "");
});

