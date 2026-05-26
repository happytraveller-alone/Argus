import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DataTableQueryState } from "../src/components/data-table/index.ts";
import type { UnifiedFindingRow } from "../src/pages/static-analysis/viewModel.ts";
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

const baseFinding: UnifiedFindingRow = {
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
	dismissalCategory: null,
	dismissalEvidence: null,
};

type StaticAnalysisFindingsTable =
	typeof import("../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx");

async function loadTableModule(): Promise<StaticAnalysisFindingsTable> {
	return import(
		"../src/pages/static-analysis/StaticAnalysisFindingsTable.tsx"
	);
}

function renderTable(
	Table: StaticAnalysisFindingsTable["default"],
	rows: UnifiedFindingRow[],
): string {
	return renderToStaticMarkup(
		createElement(
			SsrRouter,
			{},
			createElement(Table, {
				currentRoute: "/static-analysis/task-1",
				loadingInitial: false,
				rows,
				state: tableState,
				onStateChange: () => {},
				updatingKey: null,
				onToggleStatus: () => {},
			}),
		),
	);
}

test("findings table renders the dismissal chip with the correct label per category", async () => {
	const tableModule = await loadTableModule();
	const realRow: UnifiedFindingRow = {
		...baseFinding,
		key: "og-real",
		id: "f-real",
		dismissalCategory: "real",
		dismissalEvidence: {
			category: "real",
			confidenceSource: "rule_matched",
			pathPattern: null,
			sanitizerSymbols: null,
			rationale: null,
		},
	};
	const sanitizedRow: UnifiedFindingRow = {
		...baseFinding,
		key: "og-san",
		id: "f-san",
		dismissalCategory: "sanitized",
		dismissalEvidence: {
			category: "sanitized",
			confidenceSource: "path_pattern",
			pathPattern: "tests/",
			sanitizerSymbols: null,
			rationale: null,
		},
	};
	const testRow: UnifiedFindingRow = {
		...baseFinding,
		key: "og-test",
		id: "f-test",
		dismissalCategory: "test",
		dismissalEvidence: {
			category: "test",
			confidenceSource: "path_pattern",
			pathPattern: "tests/",
			sanitizerSymbols: null,
			rationale: null,
		},
	};
	const vendorRow: UnifiedFindingRow = {
		...baseFinding,
		key: "og-vend",
		id: "f-vend",
		dismissalCategory: "vendor",
		dismissalEvidence: {
			category: "vendor",
			confidenceSource: "path_pattern",
			pathPattern: "vendor/",
			sanitizerSymbols: null,
			rationale: null,
		},
	};

	const markup = renderTable(tableModule.default, [
		realRow,
		sanitizedRow,
		testRow,
		vendorRow,
	]);

	assert.match(markup, /data-testid="dismissal-chip-real"/);
	assert.match(markup, /data-testid="dismissal-chip-sanitized"/);
	assert.match(markup, /data-testid="dismissal-chip-test"/);
	assert.match(markup, /data-testid="dismissal-chip-vendor"/);
	assert.match(markup, /真实/);
	assert.match(markup, /已净化/);
	assert.match(markup, /测试代码/);
	assert.match(markup, /第三方依赖/);
	// Confidence source tooltip appears as title attribute
	assert.match(markup, /title="规则命中"/);
	assert.match(markup, /title="路径模式"/);
});

test("findings table omits the dismissal chip when evidence is absent (legacy finding)", async () => {
	const tableModule = await loadTableModule();
	const markup = renderTable(tableModule.default, [baseFinding]);
	assert.doesNotMatch(markup, /data-testid="dismissal-chip-/);
});
