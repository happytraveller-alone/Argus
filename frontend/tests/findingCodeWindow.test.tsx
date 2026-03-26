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

test("FindingCodeWindow keeps plain-text rendering when segments are absent", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "plain text line",
			filePath: "src/plain.txt",
			lineStart: 1,
			lineEnd: 1,
		}),
	);

	assert.match(markup, /plain text line/);
});

test("FindingCodeWindow renders token spans when segments are provided", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "const answer = 42;",
			filePath: "src/main.ts",
			displayLines: [
				{
					lineNumber: 1,
					content: "const answer = 42;",
					kind: "code",
					segments: [
						{ text: "const", tokenClasses: ["hljs-keyword"] },
						{ text: " answer = " },
						{ text: "42", tokenClasses: ["number"] },
						{ text: ";" },
					],
				},
			],
		}),
	);

	assert.match(markup, /<span class="text-sky-300">const<\/span>/);
	assert.match(markup, /<span class="text-amber-300">42<\/span>/);
});

test("FindingCodeWindow applies focus decorations when displayLines are provided", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "alpha\nbeta",
			filePath: "src/focus.ts",
			displayLines: [
				{ lineNumber: 1, content: "alpha", kind: "code" },
				{ lineNumber: 2, content: "beta", kind: "code" },
			],
			focusLine: 2,
		}),
	);

	assert.match(markup, /data-line-number="2"/);
	assert.match(markup, /bg-white\/\[0\.08\]/);
	assert.match(markup, /bg-\[\#151d27\]/);
});

test("FindingCodeWindow applies search-hit decorations when displayLines are provided", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "alpha\nbeta",
			filePath: "src/highlight.ts",
			displayLines: [
				{ lineNumber: 1, content: "alpha", kind: "code" },
				{ lineNumber: 2, content: "beta", kind: "code" },
			],
			highlightStartLine: 1,
			highlightEndLine: 1,
		}),
	);

	assert.match(markup, /data-line-number="1"/);
	assert.match(markup, /bg-white\/\[0\.04\]/);
	assert.match(markup, /bg-\[\#101720\]/);
});

test("FindingCodeWindow merges prop-derived focus/highlight with existing line flags", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "first\nsecond",
			filePath: "src/merge.ts",
			displayLines: [
				{
					lineNumber: 1,
					content: "first",
					kind: "code",
					isHighlighted: true,
				},
				{
					lineNumber: 2,
					content: "second",
					kind: "code",
				},
			],
			focusLine: 2,
		}),
	);

	assert.match(markup, /data-line-number="1"/);
	assert.match(markup, /data-line-number="2"/);
	assert.match(markup, /bg-white\/\[0\.04\]/);
	assert.match(markup, /bg-white\/\[0\.08\]/);
});

test("FindingCodeWindow renders meta items in header when provided", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "content",
			filePath: "src/meta.ts",
			meta: ["TypeScript", "纯文本回退"],
		}),
	);

	assert.match(markup, /TypeScript/);
	assert.match(markup, /纯文本回退/);
});

test("FindingCodeWindow keeps project-browser full-height shell in project-browser preset", async () => {
	const module = await importOrFail<any>(
		"../src/pages/AgentAudit/components/FindingCodeWindow.tsx",
	);

	const markup = renderToStaticMarkup(
		createElement(module.default, {
			code: "const x = 1;",
			filePath: "src/project.ts",
			displayPreset: "project-browser",
		}),
	);

	assert.match(markup, /data-display-preset="project-browser"/);
	assert.match(markup, /flex h-full min-h-0 flex-col/);
});

