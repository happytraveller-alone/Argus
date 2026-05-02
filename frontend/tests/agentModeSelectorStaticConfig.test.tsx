import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AgentModeSelector from "../src/components/agent/AgentModeSelector.tsx";
import {
  selectPrimaryStaticEngine,
} from "../src/shared/utils/staticEngineSelection.ts";

globalThis.React = React;

test("AgentModeSelector renders mutually exclusive Opengrep and CodeQL static engines", () => {
  const markup = renderToStaticMarkup(
    createElement(AgentModeSelector, {
      value: "static",
      onChange: () => { },
      staticTools: {
        opengrep: true,
        codeql: false,
      },
      onStaticToolsChange: () => { },
      onOpenStaticToolConfig: () => { },
    }),
  );

  assert.match(markup, /配置 规则扫描/);
  assert.match(markup, /配置 CodeQL/);
  assert.match(markup, /CodeQL 语义扫描/);
  assert.doesNotMatch(markup, /配置 Legacy Java 扫描/);
});

test("selectPrimaryStaticEngine keeps Opengrep and CodeQL mutually exclusive", () => {
  const baseSelection = {
    opengrep: true,
    codeql: false,
  };

  assert.deepEqual(selectPrimaryStaticEngine(baseSelection, "codeql", true), {
    ...baseSelection,
    opengrep: false,
    codeql: true,
  });

  assert.deepEqual(
    selectPrimaryStaticEngine(
      { ...baseSelection, opengrep: false, codeql: true },
      "opengrep",
      true,
    ),
    baseSelection,
  );
});
