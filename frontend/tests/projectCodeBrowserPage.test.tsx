import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

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

function createProject(overrides: Record<string, unknown> = {}) {
	return {
		id: "project-1",
		name: "Audit Demo",
		description: "Demo project",
		source_type: "zip",
		repository_url: undefined,
		repository_type: "other",
		default_branch: "main",
		programming_languages: "TypeScript",
		owner_id: "user-1",
		is_active: true,
		created_at: "2024-01-01T00:00:00Z",
		updated_at: "2024-01-01T00:00:00Z",
		...overrides,
	};
}

function createReadyState(overrides: Record<string, unknown> = {}) {
	return {
		status: "ready",
		requestedFilePath: "src/main.ts",
		resolvedFilePath: "src/main.ts",
		content: "export const answer = 42;",
		size: 25,
		encoding: "utf-8",
		displayLines: [
			{
				lineNumber: 1,
				content: "export const answer = 42;",
				kind: "code",
				segments: [
					{ text: "export", tokenClasses: ["keyword"] },
					{ text: " const answer = " },
					{ text: "42", tokenClasses: ["number"] },
					{ text: ";" },
				],
			},
		],
		syntaxLanguageKey: "typescript",
		syntaxLanguageLabel: "TypeScript",
		syntaxStatus: "highlighted",
		syntaxFallbackReason: null,
		...overrides,
	};
}

test("ProjectCodeBrowserContent renders repository unsupported state", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject({ source_type: "repository" }),
			loading: false,
			error: null,
			filesCount: 0,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: null,
			selectedFileState: { status: "idle" },
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /Audit Demo/);
	assert.match(markup, /仅 ZIP 类型项目支持代码浏览/);
	assert.match(markup, /返回/);
});

test("ProjectCodeBrowserContent renders selected text file in the preview pane", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 2,
			tree: [
				{
					name: "src",
					path: "src",
					kind: "directory",
					children: [
						{
							name: "main.ts",
							path: "src/main.ts",
							kind: "file",
							size: 25,
						},
					],
				},
			],
			expandedFolders: new Set<string>(["src"]),
			selectedFilePath: "src/main.ts",
			selectedFileState: createReadyState(),
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /Audit Demo/);
	assert.match(markup, /src\/main\.ts/);
	assert.match(markup, /const answer =/);
	assert.match(markup, /custom-scrollbar-dark/);
	assert.match(markup, /data-appearance="native-explorer"/);
	assert.match(markup, /data-display-preset="project-browser"/);
	assert.match(markup, /h-\[100dvh\] max-h-\[100dvh\]/);
	assert.match(markup, /flex min-h-0 flex-1 flex-col p-3/);
	assert.match(markup, /flex-1 min-h-0 overflow-hidden/);
	assert.match(markup, /max-h-none/);
	assert.match(markup, /text-sky-300/);
	assert.match(markup, /text-amber-300/);
	assert.match(markup, /TypeScript/);
});

test("ProjectCodeBrowserContent keeps plain-text fallback readable for unsupported language files", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const fallbackContent = "plain text fallback line";
	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 1,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: "notes/custom.unknown",
			selectedFileState: createReadyState({
				requestedFilePath: "notes/custom.unknown",
				resolvedFilePath: "notes/custom.unknown",
				content: fallbackContent,
				displayLines: [
					{
						lineNumber: 1,
						content: fallbackContent,
						kind: "code",
					},
				],
				syntaxLanguageKey: null,
				syntaxLanguageLabel: null,
				syntaxStatus: "plain-text",
				syntaxFallbackReason: "path-not-supported",
			}),
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /plain text fallback line/);
	assert.match(markup, /纯文本/);
	assert.doesNotMatch(markup, /纯文本回退/);
});

test("ProjectCodeBrowserContent preview header uses display path instead of source path", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 1,
			tree: [
				{
					name: "src",
					path: "src",
					kind: "directory",
					children: [
						{
							name: "main.ts",
							path: "src/main.ts",
							sourcePath: "demo/src/main.ts",
							kind: "file",
							size: 25,
						},
					],
				},
			],
			expandedFolders: new Set<string>(["src"]),
			selectedFilePath: "demo/src/main.ts",
			selectedFileState: createReadyState({
				requestedFilePath: "demo/src/main.ts",
				resolvedFilePath: "demo/src/main.ts",
			}),
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /title="src\/main\.ts:1-1"/);
	assert.doesNotMatch(markup, /title="demo\/src\/main\.ts:1-1"/);
});

test("ProjectCodeBrowserContent keeps preview pane full height for empty state", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 1,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: null,
			selectedFileState: { status: "idle" },
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /从左侧文件树选择一个文件开始浏览/);
	assert.match(markup, /h-\[100dvh\] max-h-\[100dvh\]/);
	assert.match(markup, /flex min-h-0 flex-1 flex-col p-3/);
	assert.match(markup, /flex-1 min-h-0 overflow-hidden/);
	assert.match(markup, /h-full min-h-0/);
	assert.doesNotMatch(markup, /data-display-preset="project-browser"/);
});

test("ProjectCodeBrowserContent renders the file/search mode rail and defaults to file mode", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 1,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: null,
			selectedFileState: { status: "idle" },
			browserMode: "files",
			searchQuery: "",
			searchStatus: { state: "idle", scanned: 0, total: 0 },
			searchResults: [],
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
			onSelectMode: () => {},
			onSearchQueryChange: () => {},
			onSelectSearchResult: () => {},
		}),
	);

	assert.match(markup, /xl:grid-cols-\[52px_minmax\(280px,320px\)_minmax\(0,1fr\)\]/);
	assert.match(markup, /aria-label="切换到文件浏览"/);
	assert.match(markup, /aria-label="切换到搜索"/);
	assert.match(markup, /aria-pressed="true"/);
	assert.match(markup, /打开文件/);
	assert.match(markup, /placeholder="搜索文件名 \/ 路径"/);
});

test("ProjectCodeBrowserContent renders the search panel empty state", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 2,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: null,
			selectedFileState: { status: "idle" },
			browserMode: "search",
			searchQuery: "",
			includeFileQuery: "src/",
			excludeFileQuery: "dist",
			searchStatus: { state: "idle", scanned: 0, total: 2 },
			searchResults: [],
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
			onSelectMode: () => {},
			onSearchQueryChange: () => {},
			onIncludeFileQueryChange: () => {},
			onExcludeFileQueryChange: () => {},
			onSelectSearchResult: () => {},
		}),
	);

	assert.match(markup, /内容搜索/);
	assert.match(markup, /placeholder="输入文件名或代码片段"/);
	assert.match(markup, /placeholder="例如 src\/, api"/);
	assert.match(markup, /placeholder="例如 dist, mock"/);
	assert.match(markup, /value="src\/"/);
	assert.match(markup, /value="dist"/);
	assert.match(markup, /包含文件/);
	assert.match(markup, /排除文件/);
	assert.match(markup, /输入文件名或代码片段开始搜索/);
});

test("ProjectCodeBrowserContent renders highlighted search results and preview focus decorations", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 3,
			tree: [],
			expandedFolders: new Set<string>(),
			selectedFilePath: "src/main.ts",
			selectedFileState: createReadyState({
				content: ["alpha", "const danger = true;", "omega"].join("\n"),
				size: 40,
				displayLines: [
					{ lineNumber: 1, content: "alpha", kind: "code" },
					{ lineNumber: 2, content: "const danger = true;", kind: "code" },
					{ lineNumber: 3, content: "omega", kind: "code" },
				],
			}),
			browserMode: "search",
			searchQuery: "danger",
			includeFileQuery: "src/",
			excludeFileQuery: "",
			searchStatus: { state: "done", scanned: 3, total: 3 },
			searchResults: [
				{
					id: "content:src/main.ts:2",
					kind: "content",
					filePath: "src/main.ts",
					fileName: "main.ts",
					lineNumber: 2,
					score: 100,
					pathParts: [
						{ text: "src/main.ts", matched: false },
					],
					fileNameParts: [
						{ text: "main.ts", matched: false },
					],
					excerpt: "const danger = true;",
					excerptParts: [
						{ text: "const ", matched: false },
						{ text: "danger", matched: true },
						{ text: " = true;", matched: false },
					],
				},
			],
			previewDecorations: {
				"src/main.ts": {
					focusLine: 2,
					highlightStartLine: 2,
					highlightEndLine: 2,
				},
			},
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
			onSelectMode: () => {},
			onSearchQueryChange: () => {},
			onIncludeFileQueryChange: () => {},
			onExcludeFileQueryChange: () => {},
			onSelectSearchResult: () => {},
		}),
	);

	assert.match(markup, /src\/main\.ts/);
	assert.match(markup, /第 2 行/);
	assert.match(markup, /<mark[^>]*>danger<\/mark>/);
	assert.match(markup, /data-line-number="2"/);
	assert.match(markup, /bg-white\/\[0\.08\]/);
});

test("ProjectCodeBrowserContent strengthens pane borders and code browser readability", async () => {
	const pageModule = await importOrFail<any>(
		"../src/pages/ProjectCodeBrowser.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(pageModule.ProjectCodeBrowserContent, {
			project: createProject(),
			loading: false,
			error: null,
			filesCount: 1,
			tree: [
				{
					name: "src",
					path: "src",
					kind: "directory",
					children: [
						{
							name: "main.ts",
							path: "src/main.ts",
							kind: "file",
							size: 25,
						},
					],
				},
			],
			expandedFolders: new Set<string>(["src"]),
			selectedFilePath: "src/main.ts",
			selectedFileState: createReadyState(),
			browserMode: "files",
			fileQuickOpenQuery: "main",
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
			onSelectMode: () => {},
			onFileQuickOpenQueryChange: () => {},
		}),
	);

	assert.match(
		markup,
		/border-white\/14[\s\S]*shadow-\[0_0_0_1px_rgba\(255,255,255,0\.04\)\]/,
	);
	assert.match(markup, /text-\[15px\] leading-7/);
	assert.match(markup, /bg-\[\#0a0d12\]/);
});
