import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AgentModeSelector from "../src/components/agent/AgentModeSelector.tsx";
import {
  selectPrimaryStaticEngine,
} from "../src/shared/utils/staticEngineSelection.ts";

globalThis.React = React;

test("AgentModeSelector renders mutually exclusive static engines", () => {
  const markup = renderToStaticMarkup(
    createElement(AgentModeSelector, {
      value: "static",
      onChange: () => { },
      staticTools: {
        opengrep: true,
        codeql: false,
        joern: false,
      },
      onStaticToolsChange: () => { },
      onOpenStaticToolConfig: () => { },
    }),
  );

  assert.match(markup, /配置 规则扫描/);
  assert.match(markup, /配置 CodeQL/);
  assert.match(markup, /CodeQL 语义扫描/);
  assert.match(markup, /配置 Joern 图扫描/);
  assert.doesNotMatch(markup, /配置 Legacy Java 扫描/);
});

test("selectPrimaryStaticEngine keeps static engines mutually exclusive", () => {
  const baseSelection = {
    opengrep: true,
    codeql: false,
    joern: false,
  };

  assert.deepEqual(selectPrimaryStaticEngine(baseSelection, "codeql", true), {
    ...baseSelection,
    opengrep: false,
    codeql: true,
    joern: false,
  });

  assert.deepEqual(selectPrimaryStaticEngine(baseSelection, "joern", true), {
    ...baseSelection,
    opengrep: false,
    codeql: false,
    joern: true,
  });

  assert.deepEqual(
    selectPrimaryStaticEngine(
      { ...baseSelection, opengrep: false, codeql: true, joern: false },
      "opengrep",
      true,
    ),
    baseSelection,
  );
});
