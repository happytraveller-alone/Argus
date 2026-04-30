import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected helper module ${relativePath} to exist: ${
				error instanceof Error ? error.message : String(error)
			}`,
		);
	}
}

test("DataTable 将所有列筛选收入口头并避免 detached toolbar 列筛选", async () => {
	const dataTableModule = await importOrFail<any>(
		"../src/components/data-table/index.ts",
	);

	const markup = renderToStaticMarkup(
		createElement(dataTableModule.DataTable, {
			data: [
				{
					id: "r1",
					name: "Bandit builtin",
					source: "builtin",
					status: "enabled",
					score: 8,
				},
			],
			columns: [
				{
					accessorKey: "name",
					header: "规则名称",
					meta: {
						label: "规则名称",
						filterVariant: "text",
					},
				},
				{
					accessorKey: "source",
					header: "规则来源",
					meta: {
						label: "规则来源",
						filterVariant: "select",
						filterOptions: [{ label: "内置规则", value: "builtin" }],
					},
				},
				{
					accessorKey: "status",
					header: "启用状态",
					meta: {
						label: "启用状态",
						filterVariant: "boolean",
						filterOptions: [
							{ label: "已启用", value: "true" },
							{ label: "已禁用", value: "false" },
						],
					},
				},
				{
					accessorKey: "score",
					header: "风险分",
					meta: {
						label: "风险分",
						filterVariant: "number-range",
					},
				},
			],
			toolbar: {
				searchPlaceholder: "搜索规则",
			},
			pagination: false,
		}),
	);

	assert.match(markup, /placeholder="搜索规则"/);
	assert.match(markup, /aria-label="筛选规则名称"/);
	assert.match(markup, /aria-label="筛选规则来源"/);
	assert.match(markup, /aria-label="筛选启用状态"/);
	assert.match(markup, /aria-label="筛选风险分"/);
	assert.match(markup, /data-data-table-header-control="true"/);
	assert.match(markup, /data-data-table-filter-trigger="true"/);
	assert.match(
		markup,
		/data-data-table-header-control="true"[\s\S]*aria-label="筛选规则名称"/,
	);
	assert.doesNotMatch(markup, /border-border\/50 bg-background\/35/);
	assert.doesNotMatch(markup, /border-sky-500\/30 bg-sky-500\/10/);
	assert.doesNotMatch(markup, /placeholder="筛选规则名称"/);
	assert.doesNotMatch(markup, /<label[^>]*>规则名称<\/label>/);
	assert.doesNotMatch(markup, /选择规则来源/);
	assert.doesNotMatch(markup, /选择启用状态/);
});

test("DataTable 列头筛选在默认筛选存在时显示高亮标记", async () => {
	const dataTableModule = await importOrFail<any>(
		"../src/components/data-table/index.ts",
	);

	const markup = renderToStaticMarkup(
		createElement(dataTableModule.DataTable, {
			data: [{ id: "r1", deletedStatus: "false" }],
			columns: [
				{
					accessorKey: "deletedStatus",
					header: "删除状态",
					meta: {
						label: "删除状态",
						filterVariant: "select",
						filterOptions: [
							{ label: "未删除", value: "false" },
							{ label: "已删除", value: "true" },
						],
					},
				},
			],
			state: {
				columnFilters: [{ id: "deletedStatus", value: "false" }],
			},
			resetState: {
				columnFilters: [{ id: "deletedStatus", value: "false" }],
			},
			pagination: false,
		}),
	);

	assert.match(markup, /aria-label="筛选删除状态"/);
	assert.match(markup, /data-filter-active="true"/);
	assert.match(markup, /font-bold text-primary/);
});

test("DataTable 列头控件用图标和文字状态表达排序筛选，不保留外框类", () => {
	const source = readFileSync(
		"src/components/data-table/DataTableColumnHeader.tsx",
		"utf8",
	);

	assert.match(source, /data-data-table-header-control="true"/);
	assert.match(source, /data-data-table-filter-trigger="true"/);
	assert.match(source, /onClick=\{\(event\) => event\.stopPropagation\(\)\}/);
	assert.doesNotMatch(source, /event\.preventDefault\(\);/);
	assert.match(
		source,
		/onPointerDown=\{\(event\) => event\.stopPropagation\(\)\}/,
	);
	assert.match(
		source,
		/onMouseDown=\{\(event\) => event\.stopPropagation\(\)\}/,
	);
	assert.match(source, /border border-border\/70 bg-transparent/);
	assert.match(source, /border-l border-border\/70/);
	assert.match(source, /sortState\s*\?\s*"font-bold text-primary"/);
	assert.match(source, /active &&\s*"font-bold text-primary/s);
	assert.match(
		source,
		/font-mono text-xs font-medium uppercase tracking-\[0\.16em\] text-foreground\/80/,
	);
	assert.doesNotMatch(source, /border border-border\/50 bg-background\/35/);
	assert.doesNotMatch(source, /border border-sky-500\/30 bg-sky-500\/10/);
});
