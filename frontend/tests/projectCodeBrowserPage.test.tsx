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
			selectedFileState: {
				status: "ready",
				filePath: "src/main.ts",
				content: "export const answer = 42;",
				size: 25,
				encoding: "utf-8",
			},
			onBack: () => {},
			onToggleFolder: () => {},
			onSelectFile: () => {},
		}),
	);

	assert.match(markup, /Audit Demo/);
	assert.match(markup, /2 个文件/);
	assert.match(markup, /src\/main\.ts/);
	assert.match(markup, /export const answer = 42;/);
	assert.match(markup, /custom-scrollbar-dark/);
	assert.match(markup, /data-appearance="native-explorer"/);
	assert.match(markup, /data-display-preset="project-browser"/);
	assert.match(markup, /h-\[100dvh\] max-h-\[100dvh\]/);
	assert.match(markup, /flex min-h-0 flex-1 flex-col p-3/);
	assert.match(markup, /flex-1 min-h-0 overflow-hidden/);
	assert.match(markup, /max-h-none/);
	assert.doesNotMatch(markup, /(?:text|bg|border)-(?:sky|cyan|amber|rose|emerald)/);
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
