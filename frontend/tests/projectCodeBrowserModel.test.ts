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

test("buildProjectCodeBrowserTree sorts directories first and nests children", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const tree = model.buildProjectCodeBrowserTree([
		{ path: "src/main.ts", size: 120 },
		{ path: "src/lib/a.ts", size: 80 },
		{ path: "README.md", size: 40 },
	]);

	assert.equal(tree.length, 2);
	assert.deepEqual(
		tree.map((node: any) => ({ name: node.name, kind: node.kind })),
		[
			{ name: "src", kind: "directory" },
			{ name: "README.md", kind: "file" },
		],
	);
	assert.deepEqual(
		tree[0].children.map((node: any) => ({ name: node.name, kind: node.kind })),
		[
			{ name: "lib", kind: "directory" },
			{ name: "main.ts", kind: "file" },
		],
	);
	assert.equal(tree[0].children[0].children[0].path, "src/lib/a.ts");
});

test("buildProjectCodeBrowserTree strips a shared project root directory", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const tree = model.buildProjectCodeBrowserTree([
		{ path: "demo/src/main.ts", size: 120 },
		{ path: "demo/src/lib/a.ts", size: 80 },
		{ path: "demo/README.md", size: 40 },
	]);

	assert.deepEqual(
		tree.map((node: any) => ({ name: node.name, kind: node.kind })),
		[
			{ name: "src", kind: "directory" },
			{ name: "README.md", kind: "file" },
		],
	);
	assert.equal(tree[0].path, "src");
	assert.equal(tree[0].children[1].sourcePath, "demo/src/main.ts");
	assert.equal(tree[0].children[0].children[0].path, "src/lib/a.ts");
	assert.equal(tree[0].children[0].children[0].sourcePath, "demo/src/lib/a.ts");
});

test("toggleProjectCodeBrowserFolder returns a new set and toggles folder membership", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const initial = new Set<string>();
	const expanded = model.toggleProjectCodeBrowserFolder(initial, "src");
	const collapsed = model.toggleProjectCodeBrowserFolder(expanded, "src");

	assert.equal(initial.has("src"), false);
	assert.equal(expanded.has("src"), true);
	assert.equal(collapsed.has("src"), false);
	assert.notEqual(initial, expanded);
	assert.notEqual(expanded, collapsed);
});

test("resolveProjectCodeBrowserBackTarget prefers history and falls back to projects browser", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	assert.equal(
		model.resolveProjectCodeBrowserBackTarget({
			from: "/projects#project-browser",
			hasHistory: true,
		}),
		-1,
	);
	assert.equal(
		model.resolveProjectCodeBrowserBackTarget({
			from: "/projects?page=2#project-browser",
			hasHistory: false,
		}),
		"/projects?page=2#project-browser",
	);
	assert.equal(
		model.resolveProjectCodeBrowserBackTarget({
			from: "",
			hasHistory: false,
		}),
		"/projects#project-browser",
	);
});

test("resolveProjectCodeBrowserFileSuccess maps text and non-text payloads", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const ready = model.resolveProjectCodeBrowserFileSuccess({
		file_path: "src/main.ts",
		content: "export const answer = 42;",
		size: 25,
		encoding: "utf-8",
		is_text: true,
	});
	const unavailable = model.resolveProjectCodeBrowserFileSuccess({
		file_path: "assets/logo.png",
		content: "",
		size: 1024,
		encoding: "base64",
		is_text: false,
	});

	assert.equal(ready.status, "ready");
	assert.equal(ready.filePath, "src/main.ts");
	assert.equal(ready.content, "export const answer = 42;");
	assert.equal(unavailable.status, "unavailable");
	assert.equal(unavailable.message, "当前文件不是文本文件，暂不支持预览");
});

test("resolveProjectCodeBrowserFileFailure returns the fixed fallback message", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const failed = model.resolveProjectCodeBrowserFileFailure(
		new Error("network timeout"),
	);

	assert.deepEqual(failed, {
		status: "failed",
		message: "读取文件失败，请稍后重试",
	});
});

test("buildProjectCodeBrowserFileSearchResults returns highlighted file matches", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const results = model.buildProjectCodeBrowserFileSearchResults(
		[
			{ path: "src/components/SearchPanel.tsx", size: 100 },
			{ path: "src/main.ts", size: 80 },
		],
		"search",
	);

	assert.equal(results.length, 1);
	assert.equal(results[0].kind, "file");
	assert.equal(results[0].filePath, "src/components/SearchPanel.tsx");
	assert.equal(results[0].fileName, "SearchPanel.tsx");
	assert.equal(
		results[0].fileNameParts.some((part: any) => part.matched && /Search/i.test(part.text)),
		true,
	);
	assert.equal(
		results[0].pathParts.some((part: any) => part.matched && /Search/i.test(part.text)),
		true,
	);
});

test("buildProjectCodeBrowserContentSearchResults returns line matches with highlighted excerpt", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const results = model.buildProjectCodeBrowserContentSearchResults(
		"src/main.ts",
		[
			"export const answer = 42;",
			"const searchToken = 'needle';",
			"console.log(searchToken);",
		].join("\n"),
		"needle",
		{ maxMatchesPerFile: 2 },
	);

	assert.equal(results.length, 1);
	assert.equal(results[0].kind, "content");
	assert.equal(results[0].lineNumber, 2);
	assert.match(results[0].excerpt, /needle/);
	assert.equal(
		results[0].excerptParts.some((part: any) => part.matched && /needle/i.test(part.text)),
		true,
	);
});

test("mergeProjectCodeBrowserSearchResults keeps file hits before content hits and enforces the cap", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const fileResults = model.buildProjectCodeBrowserFileSearchResults(
		[
			{ path: "src/search.ts", size: 100 },
			{ path: "src/search-panel.tsx", size: 100 },
		],
		"search",
	);
	const contentResults = model.buildProjectCodeBrowserContentSearchResults(
		"src/main.ts",
		["const first = search();", "const second = search();"].join("\n"),
		"search",
		{ maxMatchesPerFile: 3 },
	);

	const merged = model.mergeProjectCodeBrowserSearchResults(
		fileResults,
		contentResults,
		{ maxResults: 2 },
	);

	assert.equal(merged.length, 2);
	assert.deepEqual(
		merged.map((result: any) => result.kind),
		["file", "file"],
	);
});

test("shouldProjectCodeBrowserSearchContent uses the >=2 character threshold", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	assert.equal(model.shouldProjectCodeBrowserSearchContent(""), false);
	assert.equal(model.shouldProjectCodeBrowserSearchContent("a"), false);
	assert.equal(model.shouldProjectCodeBrowserSearchContent("ab"), true);
});

test("resolveProjectCodeBrowserPreviewDecorationForSearchResult maps content hits to focus and highlight lines", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const [result] = model.buildProjectCodeBrowserContentSearchResults(
		"src/main.ts",
		["alpha", "needle", "omega"].join("\n"),
		"needle",
		{ maxMatchesPerFile: 3 },
	);

	assert.deepEqual(
		model.resolveProjectCodeBrowserPreviewDecorationForSearchResult(result),
		{
			"src/main.ts": {
				focusLine: 2,
				highlightStartLine: 2,
				highlightEndLine: 2,
			},
		},
	);
});

test("filterProjectCodeBrowserFilesByPath applies include and exclude fragments", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const files = [
		{ path: "src/components/SearchPanel.tsx", size: 100 },
		{ path: "src/api/search.ts", size: 80 },
		{ path: "docs/search-notes.md", size: 40 },
	];

	const filtered = model.filterProjectCodeBrowserFilesByPath(files, {
		include: "src/, api",
		exclude: "components",
	});

	assert.deepEqual(filtered, [{ path: "src/api/search.ts", size: 80 }]);
});

test("parseProjectCodeBrowserFileFilterTokens ignores blanks and supports comma plus newline", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	assert.deepEqual(
		model.parseProjectCodeBrowserFileFilterTokens("src/, \napi\n，docs"),
		["src/", "api", "docs"],
	);
});

test("filterProjectCodeBrowserTreeByQuery keeps matching ancestors and ignores case", async () => {
	const model = await importOrFail<any>(
		"../src/pages/project-code-browser/model.ts",
	);

	const tree = model.buildProjectCodeBrowserTree([
		{ path: "src/auth/LoginController.java", size: 120 },
		{ path: "src/auth/AuthService.java", size: 80 },
		{ path: "src/user/ProfileController.java", size: 60 },
	]);

	const filtered = model.filterProjectCodeBrowserTreeByQuery(tree, " login ");

	assert.equal(filtered.length, 1);
	assert.equal(filtered[0].path, "auth");
	assert.equal(filtered[0].children.length, 1);
	assert.equal(
		filtered[0].children[0].path,
		"auth/LoginController.java",
	);
});
