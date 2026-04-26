import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DataTableQueryState } from "../src/components/data-table/index.ts";
import type {
	FindingStatus,
	UnifiedFindingRow,
} from "../src/pages/static-analysis/viewModel.ts";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const tableState: DataTableQueryState = {
	globalFilter: "",
	columnFilters: [],
	sorting: [],
	pagination: {
		pageIndex: 0,
		pageSize: 10,
	},
	columnVisibility: {},
	columnSizing: {},
	rowSelection: {},
	density: "comfortable",
};

const openFinding: UnifiedFindingRow = {
	key: "og-1",
	id: "finding-1",
	taskId: "task-1",
	engine: "opengrep",
	rule: "python-sqli",
	filePath: "src/app.py",
	line: 12,
	severity: "HIGH",
	severityScore: 3,
	confidence: "HIGH",
	confidenceScore: 3,
	status: "open",
};

const verifiedFinding: UnifiedFindingRow = {
	...openFinding,
	key: "gl-1",
	id: "finding-2",
	taskId: "task-2",
	engine: "gitleaks",
	rule: "hardcoded-secret",
	filePath: ".env",
	line: 1,
	status: "verified",
};

type StaticAnalysisFindingsTable =
	typeof import("../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx");

async function loadTableModule(): Promise<StaticAnalysisFindingsTable> {
	return import("../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx");
}

function renderTable(
	Table: StaticAnalysisFindingsTable["default"],
	overrides: Partial<{
		rows: UnifiedFindingRow[];
		updatingKey: string | null;
	}> = {},
) {
	return renderToStaticMarkup(
		createElement(
			SsrRouter,
			{},
			createElement(Table, {
				currentRoute: "/static-analysis/task-1",
				loadingInitial: false,
				rows: [openFinding],
				state: tableState,
				onStateChange: () => {},
				updatingKey: null,
				onToggleStatus: () => {},
				...overrides,
			}),
		),
	);
}

test("StaticAnalysisFindingsTable renders tri-state status copy and truthiness actions", async () => {
	const tableModule = await loadTableModule();
	const markup = renderTable(tableModule.default);

	assert.match(markup, /漏洞状态/);
	assert.match(markup, /待验证/);
	assert.match(markup, /判真/);
	assert.match(markup, /判假/);
	assert.match(markup, /详情/);
	assert.doesNotMatch(markup, /处理状态/);
	assert.doesNotMatch(markup, /修复/);
	assert.doesNotMatch(markup, />验证</);
});

test("StaticAnalysisFindingsTable only disables status actions for the updating row", async () => {
	const tableModule = await loadTableModule();
	const markup = renderTable(tableModule.default, {
		rows: [openFinding, verifiedFinding],
		updatingKey: "opengrep:finding-1:verified",
	});

	assert.equal(
		(
			markup.match(
				/<button(?=[^>]*aria-pressed="(?:true|false)")(?=[^>]*disabled="")[^>]*>/g,
			) ?? []
		).length,
		2,
	);
});

test("StaticAnalysisFindingsTable keeps severity and confidence columns non-hideable", async () => {
	const tableModule = await loadTableModule();

	const columns = tableModule.getColumns({
		currentRoute: "/static-analysis/task-1",
		updatingKey: null,
		onToggleStatus: (_row: UnifiedFindingRow, _target: FindingStatus) => {},
	});

	const severityColumn = columns.find((column) => column.id === "severity");
	const confidenceColumn = columns.find((column) => column.id === "confidence");

	assert.equal(severityColumn?.enableHiding, false);
	assert.equal(confidenceColumn?.enableHiding, false);
});
