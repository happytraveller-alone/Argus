import test from "node:test";
import assert from "node:assert/strict";
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
			`expected helper module ${relativePath} to exist: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
}

test("ProjectDescriptionSection renders ready and failed states with source badge", async () => {
	const pageModule = await importOrFail<any>("../src/pages/ProjectDetail.tsx");

	const readyMarkup = renderToStaticMarkup(
		createElement(pageModule.ProjectDescriptionSection, {
			description: "系统会根据项目结构自动生成简要介绍。",
			status: "ready",
			source: "llm",
			unsupported: false,
			onRetry: () => {},
		}),
	);
	assert.match(readyMarkup, /项目简介/);
	assert.match(readyMarkup, /LLM 生成/);

	const failedMarkup = renderToStaticMarkup(
		createElement(pageModule.ProjectDescriptionSection, {
			description: "",
			status: "failed",
			source: null,
			unsupported: false,
			onRetry: () => {},
		}),
	);
	assert.match(failedMarkup, /项目简介生成失败，请稍后重试。/);
	assert.match(failedMarkup, /重新生成/);
});

test("shouldAutoGenerateProjectDescription only runs for empty supported projects once", async () => {
	const pageModule = await importOrFail<any>("../src/pages/ProjectDetail.tsx");

	assert.equal(
		pageModule.shouldAutoGenerateProjectDescription({
			projectId: "project-1",
			description: "",
			status: "idle",
			isPageLoading: false,
			unsupported: false,
			lastRequestedProjectId: null,
		}),
		true,
	);

	assert.equal(
		pageModule.shouldAutoGenerateProjectDescription({
			projectId: "project-1",
			description: "已有简介",
			status: "idle",
			isPageLoading: false,
			unsupported: false,
			lastRequestedProjectId: null,
		}),
		false,
	);

	assert.equal(
		pageModule.shouldAutoGenerateProjectDescription({
			projectId: "project-1",
			description: "",
			status: "idle",
			isPageLoading: false,
			unsupported: true,
			lastRequestedProjectId: null,
		}),
		false,
	);

	assert.equal(
		pageModule.shouldAutoGenerateProjectDescription({
			projectId: "project-1",
			description: "",
			status: "failed",
			isPageLoading: false,
			unsupported: false,
			lastRequestedProjectId: "project-1",
		}),
		false,
	);
});
