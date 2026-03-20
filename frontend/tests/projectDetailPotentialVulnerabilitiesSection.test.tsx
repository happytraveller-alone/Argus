import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import {
	ProjectPotentialVulnerabilitiesSection,
} from "../src/pages/project-detail/components/ProjectPotentialVulnerabilitiesSection.tsx";

globalThis.React = React;

const sampleFindings = Array.from({ length: 12 }, (_, index) => ({
	id: `finding-${index + 1}`,
	title: `漏洞 ${index + 1}`,
	cweLabel: `CWE-${index + 1}`,
	cweTooltip: `说明 ${index + 1}`,
	severity: index === 0 ? "CRITICAL" : index < 5 ? "HIGH" : "MEDIUM",
	confidence: index % 2 === 0 ? "HIGH" : "MEDIUM",
	taskId: index % 2 === 0 ? "agent-task" : "static-task",
	taskCategory: index % 2 === 0 ? "intelligent" : "static",
	taskLabel: index % 2 === 0 ? "智能扫描" : "静态扫描",
	taskName: index % 2 === 0 ? "智能扫描任务" : "静态扫描任务",
	taskCreatedAt: "2026-03-19T08:00:00Z",
	route: `/findings/${index + 1}`,
	source: index % 2 === 0 ? "agent" : "static",
})) as any;

test("ProjectPotentialVulnerabilitiesSection 渲染表格并默认分页显示首批漏洞", () => {
	const markup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "ready",
				findings: sampleFindings,
				totalFindings: sampleFindings.length,
				currentRoute: "/projects/project-1",
				pageSize: 10,
			}),
		),
	);

	assert.match(markup, /潜在漏洞/);
	assert.match(markup, /仅显示中\/高置信度且中危及以上漏洞/);
	assert.match(markup, /漏洞ID/);
	assert.match(markup, /#finding-1/);
	assert.match(markup, /CWE-1/);
	assert.match(markup, /智能扫描/);
	assert.match(markup, /returnTo=%2Fprojects%2Fproject-1/);
	assert.match(markup, /第 1 \/ 2 页/);
	assert.match(markup, /placeholder="搜索漏洞 ID、类型或任务"/);
	assert.match(markup, /cyber-input h-10 pl-11 pr-4/);
	assert.doesNotMatch(markup, /aria-label="筛选严重度"/);
	assert.doesNotMatch(markup, /aria-label="筛选置信度"/);
	assert.doesNotMatch(markup, />密度</);
	assert.doesNotMatch(markup, />重置</);
	assert.doesNotMatch(markup, /漏洞 12/);
});

test("ProjectPotentialVulnerabilitiesSection 调整列宽并让漏洞列内容左对齐", () => {
	const markup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "ready",
				findings: sampleFindings.slice(0, 1),
				totalFindings: 1,
				currentRoute: "/projects/project-1",
				pageSize: 10,
			}),
		),
	);

	assert.match(markup, /class="[^"]*w-\[24%\][^"]*text-center[^"]*">漏洞ID/);
	assert.match(markup, /class="[^"]*w-\[22%\][^"]*text-center[^"]*">漏洞</);
	assert.match(markup, /class="[^"]*w-\[16%\][^"]*text-center[^"]*">操作/);
	assert.match(markup, /class="[^"]*border-r border-border\/30 text-left[^"]*"/);
	assert.match(markup, /<div class="space-y-1 text-left"/);
});

test("ProjectPotentialVulnerabilitiesSection 显示分页按钮并在第一页禁用上一页", () => {
	const markup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "ready",
				findings: sampleFindings.slice(0, 5),
				totalFindings: 5,
				currentRoute: "/projects/project-1",
				pageSize: 10,
			}),
		),
	);

	assert.match(markup, /第 1 \/ 1 页/);
	assert.match(markup, /上一页/);
	assert.match(markup, /下一页/);
	assert.match(markup, /disabled/);
});

test("ProjectPotentialVulnerabilitiesSection 在非 ready 状态显示反馈文案", () => {
	const loadingMarkup = renderToStaticMarkup(
		createElement(
			MemoryRouter,
			{},
			createElement(ProjectPotentialVulnerabilitiesSection, {
				status: "loading",
				findings: [],
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
				findings: [],
				totalFindings: 0,
				currentRoute: "/projects/project-1",
			}),
		),
	);
	assert.match(emptyMarkup, /暂无潜在漏洞/);
});
