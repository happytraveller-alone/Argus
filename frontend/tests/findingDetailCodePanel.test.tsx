import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FindingDetailCodePanel, {
	type FindingDetailPanelState,
	reduceFindingDetailPanelState,
} from "../src/pages/finding-detail/FindingDetailCodePanel.tsx";
import type { FindingDetailCodeView } from "../src/pages/finding-detail/viewModel.ts";

globalThis.React = React;

const baseSection: FindingDetailCodeView = {
	id: "section-a",
	title: "命中代码",
	filePath: "src/demo.ts",
	displayFilePath: "src/demo.ts",
	locationLabel: "第 12-13 行",
	code: "line 11\nline 12\nline 13",
	lineStart: 11,
	lineEnd: 13,
	highlightStartLine: 12,
	highlightEndLine: 13,
	focusLine: 12,
	relatedLines: [
		{ lineNumber: 11, content: "line 11", kind: "code" },
		{
			lineNumber: 12,
			content: "line 12",
			kind: "code",
			isHighlighted: true,
			isFocus: true,
		},
		{ lineNumber: 13, content: "line 13", kind: "code", isHighlighted: true },
	],
	fullFileAvailable: true,
	fullFileRequest: { projectId: "project-1", filePath: "src/demo.ts" },
};

function createPanelState(): FindingDetailPanelState {
	return {
		expandedSectionId: null,
		fullFileStates: {},
	};
}

test("reduceFindingDetailPanelState 在多文件之间保持互斥展开并保留缓存", () => {
	const readyA = {
		status: "ready" as const,
		lines: [{ lineNumber: 1, content: "a", kind: "code" as const }],
	};
	const readyB = {
		status: "ready" as const,
		lines: [{ lineNumber: 1, content: "b", kind: "code" as const }],
	};

	let state = createPanelState();
	state = reduceFindingDetailPanelState(state, {
		type: "expand",
		sectionId: "a",
	});
	assert.equal(state.expandedSectionId, "a");

	state = reduceFindingDetailPanelState(state, {
		type: "resolve",
		sectionId: "a",
		nextState: readyA,
	});
	assert.equal(state.expandedSectionId, "a");
	assert.deepEqual(state.fullFileStates.a, readyA);

	state = reduceFindingDetailPanelState(state, {
		type: "expand",
		sectionId: "b",
	});
	assert.equal(state.expandedSectionId, "b");
	assert.deepEqual(state.fullFileStates.a, readyA);

	state = reduceFindingDetailPanelState(state, {
		type: "resolve",
		sectionId: "b",
		nextState: readyB,
	});
	assert.deepEqual(state.fullFileStates.b, readyB);

	state = reduceFindingDetailPanelState(state, {
		type: "expand",
		sectionId: "a",
	});
	assert.equal(state.expandedSectionId, "a");
	assert.deepEqual(state.fullFileStates.a, readyA);
	assert.deepEqual(state.fullFileStates.b, readyB);
});

test("reduceFindingDetailPanelState 收起当前全文视图但不清空缓存", () => {
	const ready = {
		status: "ready" as const,
		lines: [{ lineNumber: 1, content: "a", kind: "code" as const }],
	};

	let state = reduceFindingDetailPanelState(createPanelState(), {
		type: "resolve",
		sectionId: "a",
		nextState: ready,
	});
	state = reduceFindingDetailPanelState(state, {
		type: "expand",
		sectionId: "a",
	});
	state = reduceFindingDetailPanelState(state, { type: "collapse" });

	assert.equal(state.expandedSectionId, null);
	assert.deepEqual(state.fullFileStates.a, ready);
});

test("FindingDetailCodePanel 隐藏完整文件入口并保留朴素三行分组布局语义", () => {
	const markup = renderToStaticMarkup(
		createElement(FindingDetailCodePanel, {
			title: "关联代码",
			sections: [baseSection],
			emptyMessage: "empty",
		}),
	);

	assert.doesNotMatch(markup, /查看文件/);
	assert.doesNotMatch(markup, /查看文件全部内容/);
	assert.match(markup, /核心漏洞代码/);
	assert.match(markup, /src\/demo\.ts/);
	assert.doesNotMatch(markup, /文件路径/);
	assert.match(markup, /rounded-xl border border-border\/70 bg-card\/35/);
	assert.match(markup, /grid-cols-\[48px_minmax\(0,1fr\)\]/);
	assert.doesNotMatch(markup, /shadow-\[0_14px_32px_rgba\(2,6,23,0\.38\)\]/);
});

test("FindingDetailCodePanel 将暗色滚动条统一挂载到列表与代码容器，并移除行内横向滚动", () => {
	const markup = renderToStaticMarkup(
		createElement(FindingDetailCodePanel, {
			title: "关联代码",
			sections: [baseSection],
			emptyMessage: "empty",
		}),
	);

	assert.match(
		markup,
		/min-h-0 flex-1 overflow-y-auto custom-scrollbar-dark space-y-4 pr-1/,
	);
	assert.match(
		markup,
		/max-h-\[52vh\] overflow-auto custom-scrollbar-dark rounded-lg border border-border\/60 bg-\[#0b1120\]/,
	);
	assert.match(markup, /min-w-max/);
	assert.doesNotMatch(markup, /overflow-x-auto whitespace-pre/);
});
