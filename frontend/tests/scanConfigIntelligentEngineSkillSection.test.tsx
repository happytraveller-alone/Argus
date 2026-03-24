import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ScanConfigIntelligentEngine from "../src/pages/ScanConfigIntelligentEngine.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("ScanConfigIntelligentEngine 展示 Skill 管理区与外部工具入口", () => {
	const markup = renderToStaticMarkup(
		createElement(
			SsrRouter,
			null,
			createElement(ScanConfigIntelligentEngine),
		),
	);

	assert.match(markup, /Skill 管理/);
	assert.match(markup, /前往外部工具详情/);
	assert.match(markup, /\/scan-config\/external-tools/);
	assert.match(markup, /Agent 角色/);
	assert.match(markup, /Skill Key/);
	assert.match(markup, /business_logic_recon/);
});
