import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

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

test("ProjectsTable renders rows and disabled project actions", async () => {
	const tableModule = await importOrFail<any>(
		"../src/pages/projects/components/ProjectsTable.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(MemoryRouter, {}, createElement(tableModule.default, {
			rows: [
				{
					id: "p1",
					rowNumber: 1,
					name: "Demo Project",
					detailPath: "/projects/p1",
					detailState: { from: "/projects" },
					sizeText: "10 文件 / 200 行",
					statusLabel: "启用",
					statusClassName: "cyber-badge-success",
					statusToggle: {
						action: "disable",
						label: "禁用",
						requiresConfirmation: true,
						disabled: false,
					},
					isActive: true,
					totalIssues: 5,
					executionStats: { completed: 2, running: 1 },
					actions: {
						canCreateScan: true,
						canBrowseCode: true,
						browseCodePath: "/projects/p1/code-browser",
						browseCodeState: { from: "/projects#project-browser" },
						browseCodeDisabledReason: null,
					},
				},
				{
					id: "p2",
					rowNumber: 2,
					name: "Disabled Project",
					detailPath: "/projects/p2",
					detailState: { from: "/projects" },
					sizeText: "-",
					statusLabel: "禁用",
					statusClassName: "cyber-badge-warning",
					statusToggle: {
						action: "enable",
						label: "启用",
						requiresConfirmation: false,
						disabled: false,
					},
					isActive: false,
					totalIssues: 0,
					executionStats: { completed: 0, running: 0 },
					actions: {
						canCreateScan: false,
						canBrowseCode: false,
						browseCodePath: "/projects/p2/code-browser",
						browseCodeState: { from: "/projects#project-browser" },
						browseCodeDisabledReason: "仅 ZIP 类型项目支持代码浏览",
					},
				},
			],
			selectedProjectIds: new Set(["p1"]),
			isAllCurrentPageSelected: false,
			isSomeCurrentPageSelected: true,
			onToggleProjectSelection: () => {},
			onToggleSelectCurrentPage: () => {},
			onCreateScan: () => {},
			onToggleProjectStatus: () => {},
		})),
	);

	assert.match(markup, /Demo Project/);
	assert.match(markup, /Disabled Project/);
	assert.match(markup, /查看详情/);
	assert.match(markup, /代码浏览/);
	assert.match(markup, /创建扫描/);
	assert.match(markup, /禁用/);
	assert.match(markup, /启用/);
	assert.match(markup, /仅 ZIP 类型项目支持代码浏览/);
	assert.ok(markup.indexOf("查看详情") < markup.indexOf("代码浏览"));
	assert.ok(markup.indexOf("代码浏览") < markup.indexOf("创建扫描"));
	assert.ok(markup.indexOf("创建扫描") < markup.indexOf("禁用"));
	assert.equal((markup.match(/切换项目状态/g) || []).length, 2);
	assert.match(markup, /disabled/);
});
