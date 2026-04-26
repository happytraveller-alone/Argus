import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

async function renderTopNavigation(location = "/") {
	const [{ default: TopNavigation }, { LanguageProvider }] = await Promise.all([
		import("../src/components/layout/TopNavigation"),
		import("../src/shared/i18n"),
	]);

	return renderToStaticMarkup(
		createElement(LanguageProvider, {
			children: createElement(
				SsrRouter,
				{ location },
				createElement(TopNavigation),
			),
		}),
	);
}

test("TopNavigation renders the main routes and grouped dropdown triggers", async () => {
	const markup = await renderTopNavigation();

	assert.match(markup, /aria-label="Argus"/);
	assert.match(markup, /src="\/argus\.png"/);
	assert.match(markup, /首页/);
	assert.match(markup, /仪表盘/);
	assert.match(markup, /项目管理/);
	assert.match(markup, /data-top-nav-group-trigger="task"/);
	assert.match(markup, /data-top-nav-group-trigger="scanConfig"/);
	assert.match(markup, /data-top-nav-group-trigger="devTest"/);
	assert.match(markup, /任务管理/);
	assert.match(markup, /扫描配置/);
	assert.match(markup, /开发测试/);
	assert.doesNotMatch(markup, /Agent 测试/);
	assert.doesNotMatch(markup, />\s*EN\s*</);
});

test("TopNavigation logo uses the image directly without an outer frame", async () => {
	const markup = await renderTopNavigation();
	const logoMatch = markup.match(
		/<a[^>]*aria-label="Argus"[^>]*>[\s\S]*?<\/a>/,
	);

	assert.match(markup, /<a[^>]*aria-label="Argus"[^>]*><img/);
	assert.ok(logoMatch);
	assert.doesNotMatch(logoMatch[0], /border-primary\/40/);
	assert.doesNotMatch(logoMatch[0], /bg-primary\/10/);
	assert.doesNotMatch(logoMatch[0], /rounded-lg/);
});

test("TopNavigation group triggers keep default entries internal, not parent links", async () => {
	const markup = await renderTopNavigation();

	assert.doesNotMatch(markup, /默认入口/);
	assert.doesNotMatch(
		markup,
		/<a[^>]*href="\/tasks\/static"[^>]*>[\s\S]*?任务管理[\s\S]*?<\/a>/,
	);
	assert.doesNotMatch(
		markup,
		/<a[^>]*href="\/scan-config\/engines"[^>]*>[\s\S]*?扫描配置[\s\S]*?<\/a>/,
	);
	assert.doesNotMatch(
		markup,
		/<a[^>]*href="\/data-management"[^>]*>[\s\S]*?开发测试[\s\S]*?<\/a>/,
	);
});

test("TopNavigation desktop dropdowns do not repeat parent group labels", () => {
	const topNavigationSource = fs.readFileSync(
		path.resolve(process.cwd(), "src/components/layout/TopNavigation.tsx"),
		"utf8",
	);
	const desktopDropdownMatch = topNavigationSource.match(
		/<DropdownMenuContent\s+align="start"[\s\S]*?<\/DropdownMenuContent>/,
	);

	assert.ok(desktopDropdownMatch);
	assert.doesNotMatch(desktopDropdownMatch[0], /DropdownMenuLabel/);
	assert.doesNotMatch(desktopDropdownMatch[0], /\{group\.label\}/);
});

test("TopNavigation desktop dropdown width follows its top-level trigger", () => {
	const topNavigationSource = fs.readFileSync(
		path.resolve(process.cwd(), "src/components/layout/TopNavigation.tsx"),
		"utf8",
	);
	const desktopDropdownMatch = topNavigationSource.match(
		/<DropdownMenuContent\s+align="start"[\s\S]*?<\/DropdownMenuContent>/,
	);

	assert.ok(desktopDropdownMatch);
	assert.match(
		desktopDropdownMatch[0],
		/w-\[var\(--radix-dropdown-menu-trigger-width\)\]/,
	);
	assert.doesNotMatch(desktopDropdownMatch[0], /min-w-48/);
});

test("TopNavigation desktop dropdown close is delayed and scoped to the hovered group", () => {
	const topNavigationSource = fs.readFileSync(
		path.resolve(process.cwd(), "src/components/layout/TopNavigation.tsx"),
		"utf8",
	);

	assert.match(
		topNavigationSource,
		/const DESKTOP_GROUP_CLOSE_DELAY_MS = 240;/,
	);
	assert.match(topNavigationSource, /function TopNavigation/);
	assert.match(topNavigationSource, /openGroupMenu\(group\.group\.id\)/);
	assert.match(topNavigationSource, /scheduleGroupClose\(group\.group\.id\)/);
	assert.match(
		topNavigationSource,
		/currentGroupId === groupId \? null : currentGroupId/,
	);
	assert.doesNotMatch(
		topNavigationSource,
		/setOpenGroupId\(open \? group\.group\.id : null\)/,
	);
});

test("TopNavigation keeps desktop and mobile menu affordances without a left drawer", async () => {
	const markup = await renderTopNavigation();
	const topNavigationSource = fs.readFileSync(
		path.resolve(process.cwd(), "src/components/layout/TopNavigation.tsx"),
		"utf8",
	);

	assert.match(markup, /aria-label="打开导航菜单"/);
	assert.match(markup, /data-top-navigation-shell="true"/);
	assert.doesNotMatch(markup, /<aside/);
	assert.doesNotMatch(topNavigationSource, /translate-x/);
	assert.doesNotMatch(topNavigationSource, /fixed top-4 left-4/);
	assert.doesNotMatch(topNavigationSource, /defaultEntryPath/);
	assert.match(topNavigationSource, /onMouseEnter/);
	assert.match(topNavigationSource, /onFocus/);
	assert.match(topNavigationSource, /DropdownMenuTrigger asChild/);
});

test("TopNavigation highlights parents for hidden detail routes", async () => {
	const projectMarkup = await renderTopNavigation("/projects/example/code-browser");
	assert.match(projectMarkup, /data-top-nav-active="true"/);
	assert.match(projectMarkup, /href="\/projects"/);

	const toolMarkup = await renderTopNavigation(
		"/scan-config/external-tools/opengrep/example",
	);
	assert.match(
		toolMarkup,
		/data-top-nav-group-trigger="scanConfig"[^>]*data-top-nav-active="true"/,
	);
});

test("navigation model returns grouped routes in configured order", async () => {
	const [
		{ buildNavigationModel },
		{ default: routes },
		{ SIDEBAR_NAV_GROUPS },
	] = await Promise.all([
		import("../src/components/layout/navigationModel"),
		import("../src/app/routes.tsx"),
		import("../src/app/sidebarNavGroups.ts"),
	]);

	const model = buildNavigationModel({
		pathname: "/scan-config/external-tools/opengrep/example",
		routes,
		groups: SIDEBAR_NAV_GROUPS,
		getRouteLabel: (route) => route.name,
		getGroupLabel: (group) => group.fallbackLabel,
	});

	assert.deepEqual(
		model.mainRoutes.map((item) => item.route.path),
		["/", "/dashboard", "/projects"],
	);
	assert.deepEqual(
		model.groups.map((group) => ({
			id: group.group.id,
			paths: group.routes.map((item) => item.route.path),
			active: group.isActive,
		})),
		[
			{
				id: "task",
				paths: ["/tasks/static", "/tasks/intelligent"],
				active: false,
			},
			{
				id: "scanConfig",
				paths: [
					"/scan-config/engines",
					"/scan-config/intelligent-engine",
					"/scan-config/external-tools",
				],
				active: true,
			},
			{
				id: "devTest",
				paths: ["/data-management"],
				active: false,
			},
		],
	);
	assert.equal(model.activeNavPath, "/scan-config/external-tools");
});

test("App shell removes the sidebar layout contract", () => {
	const appSource = fs.readFileSync(
		path.resolve(process.cwd(), "src/app/App.tsx"),
		"utf8",
	);

	assert.doesNotMatch(appSource, /Sidebar/);
	assert.doesNotMatch(appSource, /collapsed/);
	assert.doesNotMatch(appSource, /md:ml-20/);
	assert.doesNotMatch(appSource, /md:ml-64/);
	assert.match(appSource, /flex min-h-screen flex-col/);
	assert.match(appSource, /<main className="flex-1">/);
	assert.match(appSource, /TopNavigation/);
});
