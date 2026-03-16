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
