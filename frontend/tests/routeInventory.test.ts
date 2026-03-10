import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const routesFile = path.join(frontendDir, "src/app/routes.tsx");

interface ParsedRoute {
	name: string;
	path: string;
	visible: boolean | null;
	navVisible: boolean | null;
}

function parseRoutes(): ParsedRoute[] {
	const text = fs.readFileSync(routesFile, "utf8");
	return Array.from(text.matchAll(/\{([\s\S]*?)\n\s*\},/g), (match) => {
		const block = match[1];
		return {
			name: block.match(/name:\s*"([^"]+)"/)?.[1] ?? "",
			path: block.match(/path:\s*"([^"]+)"/)?.[1] ?? "",
			visible: block.includes("visible: true")
				? true
				: block.includes("visible: false")
					? false
					: null,
			navVisible: block.includes("navVisible: true")
				? true
				: block.includes("navVisible: false")
					? false
					: null,
		};
	}).filter((route) => route.path);
}

function routePathsBy(predicate: (route: ParsedRoute) => boolean) {
	return parseRoutes().filter(predicate).map((route) => route.path);
}

test("route inventory keeps the current visible, hidden, and redirect page groups stable", () => {
	const navVisible = routePathsBy(
		(route) => (route.navVisible ?? route.visible) !== false,
	);
	const hiddenButRouted = routePathsBy(
		(route) =>
			(route.navVisible ?? route.visible) === false &&
			!route.name.includes("重定向"),
	);
	const redirectOnly = routePathsBy(
		(route) => route.name.includes("重定向"),
	);

	assert.deepEqual(navVisible, [
		"/",
		"/dashboard",
		"/projects",
		"/tasks/static",
		"/tasks/intelligent",
		"/tasks/hybrid",
		"/scan-config/engines",
		"/scan-config/intelligent-engine",
		"/scan-config/external-tools",
	]);

	assert.deepEqual(hiddenButRouted, [
		"/agent-audit/:taskId",
		"/projects/:id",
		"/static-analysis/:taskId",
		"/finding-detail/:source/:taskId/:findingId",
		"/static-analysis/:taskId/findings/:findingId",
		"/admin",
	]);

	assert.deepEqual(redirectOnly, [
		"/opengrep-rules",
		"/tasks/overview",
		"/scan-config",
	]);
});

test("orphan page files scheduled for phase-one trim are absent", () => {
	const removedFiles = [
		"src/pages/TaskManagementOverview.tsx",
		"src/pages/ScanConfigOverview.tsx",
		"src/pages/project-detail/components/ProjectTasksTab.tsx",
		"src/pages/project-detail/constants.ts",
	];

	for (const relativePath of removedFiles) {
		assert.equal(
			fs.existsSync(path.join(frontendDir, relativePath)),
			false,
			`${relativePath} should be removed in phase-one page trimming`,
		);
	}
});

test("runtime-dead business files scheduled for phase-two trim are absent", () => {
	const removedFiles = [
		"src/components/agent/AgentSettingsPanel.tsx",
		"src/components/agent/CreateAgentTaskDialog.tsx",
		"src/components/scan/CreateAgentScanDialog.tsx",
		"src/components/scan/CreateStaticScanDialog.tsx",
		"src/components/scan/components/ZipFileSection.tsx",
		"src/features/reports/services/reportExport.ts",
	];

	for (const relativePath of removedFiles) {
		assert.equal(
			fs.existsSync(path.join(frontendDir, relativePath)),
			false,
			`${relativePath} should be removed in phase-two trimming`,
		);
	}
});
