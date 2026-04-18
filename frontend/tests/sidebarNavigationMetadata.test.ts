import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import fs from "node:fs";
import path from "node:path";

globalThis.React = React;

const [{ default: routes }, { SIDEBAR_NAV_GROUPS }] = await Promise.all([
	import("../src/app/routes.tsx"),
	import("../src/app/sidebarNavGroups.ts"),
]);

test("data management route is grouped under devTest navigation", () => {
	const dataManagementRoute = routes.find(
		(route) => route.path === "/data-management",
	);

	assert.ok(dataManagementRoute);
	assert.equal(dataManagementRoute.navGroup, "devTest");
});

test("agent test route has been removed", () => {
	const agentTestRoute = routes.find((route) => route.path === "/agent-test");
	assert.equal(agentTestRoute, undefined);
});

test("task routes keep only the current static and intelligent pages", () => {
	const taskRoutes = routes
		.filter(
			(route) =>
				route.path === "/tasks/static" || route.path === "/tasks/intelligent",
		)
		.map((route) => route.path)
		.sort();

	assert.deepEqual(taskRoutes, ["/tasks/intelligent", "/tasks/static"]);
	assert.equal(
		fs.existsSync(
			path.resolve(process.cwd(), "src/pages/TaskManagementStatic.tsx"),
		),
		true,
	);
	assert.equal(
		fs.existsSync(
			path.resolve(process.cwd(), "src/pages/TaskManagementIntelligent.tsx"),
		),
		true,
	);
});

test("sidebar navigation groups keep the expected parent order", () => {
	assert.deepEqual(
		SIDEBAR_NAV_GROUPS.map((group) => group.id),
		["task", "scanConfig", "devTest"],
	);
});

test("devTest group defaults to the data management page", () => {
	const devTestGroup = SIDEBAR_NAV_GROUPS.find(
		(group) => group.id === "devTest",
	);

	assert.ok(devTestGroup);
	assert.equal(devTestGroup.defaultEntryPath, "/data-management");
});

test("agent task detail route uses a different page component than the home route", () => {
	const homeRoute = routes.find((route) => route.path === "/");
	const agentTaskRoute = routes.find((route) => route.path === "/agent-audit/:taskId");

	assert.ok(homeRoute);
	assert.ok(agentTaskRoute);
	assert.notEqual(
		(homeRoute.element as any)?.type,
		(agentTaskRoute.element as any)?.type,
	);
});

test("project code browser route stays hidden under the projects section", () => {
	const codeBrowserRoute = routes.find(
		(route) => route.path === "/projects/:id/code-browser",
	);

	assert.ok(codeBrowserRoute);
	assert.equal(codeBrowserRoute.visible, false);
	assert.equal(codeBrowserRoute.navVisible, false);
	assert.equal(codeBrowserRoute.navParentPath, "/projects");
});
