import assert from "node:assert/strict";
import test from "node:test";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CodeqlExplorationProgressEvent } from "../src/shared/api/opengrep.ts";

globalThis.React = React;

type CodeqlExplorationPanel =
  typeof import("../src/pages/static-analysis/CodeqlExplorationPanel.tsx");

async function loadPanelModule(): Promise<CodeqlExplorationPanel> {
  return import("../src/pages/static-analysis/CodeqlExplorationPanel.tsx");
}

const explorationEvents: CodeqlExplorationProgressEvent[] = [
  {
    timestamp: "2026-05-03T00:00:00.000Z",
    event_type: "llm_round_started",
    stage: "llm_round_started",
    progress: 20,
    round: 1,
    payload: {
      reasoning_summary: "识别 C/C++ 编译入口",
      command: "cmake --build build",
      stdout: "build started",
    },
  },
];

test("CodeqlExplorationPanel renders as a scrollable auto-follow timeline module", async () => {
  const panelModule = await loadPanelModule();

  const markup = renderToStaticMarkup(
    createElement(panelModule.default, {
      events: explorationEvents,
      canReset: true,
      resetting: false,
      onReset: () => {},
    }),
  );

  assert.match(markup, /CodeQL 编译探索/);
  assert.match(markup, /overflow-y-auto/);
  assert.match(markup, /min-h-0 flex-1/);
  assert.match(markup, /识别 C\/C\+\+ 编译入口/);
  assert.match(markup, /重置并重新探索/);
});
