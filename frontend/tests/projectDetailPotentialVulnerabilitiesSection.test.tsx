import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import {
	ProjectPotentialVulnerabilitiesSection,
} from "../src/pages/project-detail/components/ProjectPotentialVulnerabilitiesSection.tsx";

globalThis.React = React;

const tree = [
	{
		type: "task",
		nodeKey: "task:intelligent:agent-1",
		taskId: "agent-1",
		taskCategory: "intelligent",
		taskLabel: "智能扫描",
		taskName: "智能审计任务",
		createdAt: "2026-03-19T08:00:00Z",
		count: 1,
		children: [
			{
				type: "file",
				nodeKey: "task:intelligent:agent-1:file:src/auth.ts",
				name: "auth.ts",
				path: "src/auth.ts",
				count: 1,
				children: [
					{
						type: "finding",
						nodeKey: "task:intelligent:agent-1:finding:finding-1",
						id: "finding-1",
						title: "SQL 注入",
						cweLabel: "CWE-89 SQL注入",
						cweTooltip: "tooltip",
						severity: "HIGH",
						confidence: "HIGH",
						location: "src/auth.ts:18",
						route: "/findings/agent-1/finding-1",
						taskCategory: "intelligent",
						source: "agent",
					},
				],
			},
		],
	},
] as any;

test("ProjectPotentialVulnerabilitiesSection 默认展开任务层并显示规则说明", () => {
	const markup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "ready",
				tree,
				totalFindings: 1,
				currentRoute: "/projects/project-1",
				initialExpandedKeys: ["task:intelligent:agent-1"],
				formatDate: () => "2026年3月19日 08:00",
			}),
		),
	);

	assert.match(markup, /潜在漏洞/);
	assert.match(markup, /仅显示中\/高置信度且中危及以上漏洞/);
	assert.match(markup, /智能扫描/);
	assert.match(markup, /2026年3月19日 08:00/);
	assert.match(markup, /auth\.ts/);
	assert.doesNotMatch(markup, /SQL 注入/);
});

test("ProjectPotentialVulnerabilitiesSection 展开文件层后显示漏洞叶子和详情回跳", () => {
	const markup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "ready",
				tree,
				totalFindings: 1,
				currentRoute: "/projects/project-1",
				initialExpandedKeys: [
					"task:intelligent:agent-1",
					"task:intelligent:agent-1:file:src/auth.ts",
				],
				formatDate: () => "2026年3月19日 08:00",
			}),
		),
	);

	assert.match(markup, /SQL 注入/);
	assert.match(markup, /CWE-89 SQL注入/);
	assert.match(markup, /src\/auth\.ts:18/);
	assert.match(markup, /详情/);
	assert.match(markup, /returnTo=%2Fprojects%2Fproject-1/);
});

test("ProjectPotentialVulnerabilitiesSection 在非 ready 状态显示反馈文案", () => {
	const loadingMarkup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "loading",
				tree: [],
				totalFindings: 0,
				currentRoute: "/projects/project-1",
			}),
		),
	);
	assert.match(loadingMarkup, /加载中/);

	const emptyMarkup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "empty",
				tree: [],
				totalFindings: 0,
				currentRoute: "/projects/project-1",
			}),
		),
	);
	assert.match(emptyMarkup, /暂无潜在漏洞/);
});
