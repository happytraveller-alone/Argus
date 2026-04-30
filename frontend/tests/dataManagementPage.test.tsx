import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

test("DataManagement page only exposes transfer-oriented content", async () => {
	const { default: DataManagementPage } = await import(
		"../src/pages/DataManagement.tsx"
	);

	const markup = renderToStaticMarkup(createElement(DataManagementPage));

	assert.match(markup, /数据管理/);
	assert.match(markup, /导出迁移包/);
	assert.match(markup, /导入迁移包/);
	assert.match(markup, /rounded-lg border border-border bg-card/);
	assert.doesNotMatch(markup, /Agent 单体测试/);
	assert.doesNotMatch(markup, /Agent 测试/);
	assert.doesNotMatch(markup, /Recon/);
});
