import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FindingDetailCodePanel, {
  reduceFindingDetailPanelState,
  type FindingDetailPanelState,
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
    { lineNumber: 12, content: "line 12", kind: "code", isHighlighted: true, isFocus: true },
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
  state = reduceFindingDetailPanelState(state, { type: "expand", sectionId: "a" });
  assert.equal(state.expandedSectionId, "a");

  state = reduceFindingDetailPanelState(state, {
    type: "resolve",
    sectionId: "a",
    nextState: readyA,
  });
  assert.equal(state.expandedSectionId, "a");
  assert.deepEqual(state.fullFileStates.a, readyA);

  state = reduceFindingDetailPanelState(state, { type: "expand", sectionId: "b" });
  assert.equal(state.expandedSectionId, "b");
  assert.deepEqual(state.fullFileStates.a, readyA);

  state = reduceFindingDetailPanelState(state, {
    type: "resolve",
    sectionId: "b",
    nextState: readyB,
  });
  assert.deepEqual(state.fullFileStates.b, readyB);

  state = reduceFindingDetailPanelState(state, { type: "expand", sectionId: "a" });
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
  state = reduceFindingDetailPanelState(state, { type: "expand", sectionId: "a" });
  state = reduceFindingDetailPanelState(state, { type: "collapse" });

  assert.equal(state.expandedSectionId, null);
  assert.deepEqual(state.fullFileStates.a, ready);
});

test("FindingDetailCodePanel 使用深色紧凑代码卡片语义", () => {
  const markup = renderToStaticMarkup(
    createElement(FindingDetailCodePanel, {
      title: "关联代码",
      sections: [baseSection],
      emptyMessage: "empty",
    }),
  );

  assert.match(markup, /查看文件全部内容/);
  assert.match(markup, /核心漏洞代码/);
  assert.match(markup, /bg-\[#0f1720\]|bg-\[#111827\]|bg-slate/);
  assert.doesNotMatch(markup, /bg-\[#fffdfa\]/);
  assert.doesNotMatch(markup, /border-b border-stone-200\/80/);
});
