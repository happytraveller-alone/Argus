import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

async function renderSidebar(collapsed: boolean) {
	const [{ default: Sidebar }, { LanguageProvider }] = await Promise.all([
		import("../src/components/layout/Sidebar"),
		import("../src/shared/i18n"),
	]);

	return renderToStaticMarkup(
		createElement(LanguageProvider, {
			children: createElement(
				SsrRouter,
				{},
				createElement(Sidebar, {
					collapsed,
					setCollapsed: () => {},
				}),
			),
		}),
	);
}

test("Sidebar 默认宽版会展开全部分组子菜单", async () => {
	const markup = await renderSidebar(false);

	assert.match(markup, /静态扫描/);
	assert.match(markup, /智能扫描/);
	assert.match(markup, /混合扫描/);
	assert.match(markup, /扫描引擎/);
	assert.match(markup, /智能引擎/);
	assert.match(markup, /外部工具/);
	assert.match(markup, /Agent 测试/);
	assert.doesNotMatch(markup, />\s*EN\s*</);
});

test("Sidebar 分组父项不是可点击链接", async () => {
	const expandedMarkup = await renderSidebar(false);

	assert.match(expandedMarkup, /data-sidebar-group-header="task"/);
	assert.match(expandedMarkup, /data-sidebar-group-header="scanConfig"/);
	assert.match(expandedMarkup, /data-sidebar-group-header="devTest"/);
	assert.doesNotMatch(
		expandedMarkup,
		/<a[^>]*href="\/tasks\/static"[^>]*>[\s\S]*?<span[^>]*>任务管理<\/span><\/a>/,
	);
	assert.doesNotMatch(
		expandedMarkup,
		/<a[^>]*href="\/scan-config\/engines"[^>]*>[\s\S]*?<span[^>]*>扫描配置<\/span><\/a>/,
	);
	assert.doesNotMatch(
		expandedMarkup,
		/<a[^>]*href="\/agent-test"[^>]*>[\s\S]*?<span[^>]*>开发测试<\/span><\/a>/,
	);

	const collapsedMarkup = await renderSidebar(true);

	assert.doesNotMatch(collapsedMarkup, /href="\/tasks\/static"/);
	assert.doesNotMatch(collapsedMarkup, /href="\/scan-config\/engines"/);
	assert.doesNotMatch(collapsedMarkup, /href="\/agent-test"/);
});

test("Sidebar 折叠态仍隐藏分组子菜单但保留一级导航", async () => {
	const markup = await renderSidebar(true);

	assert.doesNotMatch(markup, /静态扫描/);
	assert.doesNotMatch(markup, /智能扫描/);
	assert.doesNotMatch(markup, /混合扫描/);
	assert.doesNotMatch(markup, /扫描引擎/);
	assert.doesNotMatch(markup, /智能引擎/);
	assert.doesNotMatch(markup, /外部工具/);
	assert.doesNotMatch(markup, /Agent 测试/);
	assert.match(markup, /首页/);
	assert.match(markup, /仪表盘/);
});
