import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import type { DataTableQueryState } from "../src/components/data-table/index.ts";
import type {
	FindingStatus,
	UnifiedFindingRow,
} from "../src/pages/static-analysis/viewModel.ts";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const dataTableColumnHeaderSource = readFileSync(
	"src/components/data-table/DataTableColumnHeader.tsx",
	"utf8",
);

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
	key: "cq-1",
	id: "finding-2",
	taskId: "task-codeql",
	engine: "codeql",
	rule: "codeql-rule",
	filePath: "src/query.cpp",
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
		state: DataTableQueryState;
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

	assert.match(markup, /placeholder="搜索规则、位置或状态"/);
	assert.match(markup, /漏洞状态/);
	assert.match(markup, /待验证/);
	assert.match(markup, /判真/);
	assert.match(markup, /判假/);
	assert.match(markup, /详情/);
	assert.doesNotMatch(markup, /处理状态/);
	assert.doesNotMatch(markup, /修复/);
	assert.doesNotMatch(markup, />验证</);
});

test("StaticAnalysisFindingsTable top search filters visible main row fields only", async () => {
	const tableModule = await loadTableModule();
	const hiddenOnlyFinding = {
		...verifiedFinding,
		key: "hidden-only",
		id: "finding-hidden",
		rule: "safe-rule",
		filePath: "src/safe.ts",
		status: "open",
		rawJsonOnlyNeedle: "hidden-needle",
	} as UnifiedFindingRow & { rawJsonOnlyNeedle: string };

	const visibleMatchMarkup = renderTable(tableModule.default, {
		rows: [openFinding, hiddenOnlyFinding],
		state: {
			...tableState,
			globalFilter: "src/app.py",
		},
	});
	assert.match(visibleMatchMarkup, /src\/app.py/);
	assert.doesNotMatch(visibleMatchMarkup, /src\/safe.ts/);

	const hiddenOnlyMarkup = renderTable(tableModule.default, {
		rows: [hiddenOnlyFinding],
		state: {
			...tableState,
			globalFilter: "hidden-needle",
		},
	});
	assert.match(hiddenOnlyMarkup, /暂无符合条件的漏洞/);
	assert.doesNotMatch(hiddenOnlyMarkup, /src\/safe.ts/);
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

test("StaticAnalysisFindingsTable narrows rule column and fills the page width", async () => {
	const tableModule = await loadTableModule();

	const columns = tableModule.getColumns({
		currentRoute: "/static-analysis/task-1",
		updatingKey: null,
		onToggleStatus: (_row: UnifiedFindingRow, _target: FindingStatus) => {},
	});
	const ruleColumn = columns.find((column) => column.id === "rule");
	const ruleMeta = ruleColumn?.meta as
		| {
				width?: number;
				minWidth?: number;
				maxWidth?: number;
				filterVariant?: string;
		  }
		| undefined;

	assert.equal(ruleMeta?.width, 220);
	assert.equal(ruleMeta?.minWidth, 180);
	assert.equal(ruleMeta?.maxWidth, 260);
	assert.equal(ruleMeta?.filterVariant, "text");

	const markup = renderTable(tableModule.default, {
		rows: [
			{
				...openFinding,
				rule: "vuln-clamav-96ff19a1",
			},
		],
	});

	assert.match(markup, /style="width:100%;min-width:\d+px"/);
	assert.match(markup, /class="[^"]*truncate[^"]*"/);
	assert.match(markup, /title="vuln-clamav-96ff19a1"/);
});

test("StaticAnalysisFindingsTable headers inherit the shared 序号 typography baseline", async () => {
	const tableModule = await loadTableModule();
	const markup = renderTable(tableModule.default);

	assert.match(markup, /序号/);
	assert.match(
		markup,
		/font-mono text-xs font-medium uppercase tracking-\[0\.16em\] text-foreground\/80/,
	);
	assert.match(
		dataTableColumnHeaderSource,
		/inline-flex items-center font-mono text-xs font-medium uppercase tracking-\[0\.16em\] text-foreground\/80/,
	);
});
