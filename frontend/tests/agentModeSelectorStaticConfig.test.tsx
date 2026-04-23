import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AgentModeSelector from "../src/components/agent/AgentModeSelector.tsx";

globalThis.React = React;

test("AgentModeSelector renders config buttons for static tools", () => {
  const markup = renderToStaticMarkup(
    createElement(AgentModeSelector, {
      value: "static",
      onChange: () => { },
      staticTools: {
        opengrep: true,
        gitleaks: false,
        bandit: false,
        phpstan: false,
        pmd: false,
      },
      onStaticToolsChange: () => { },
      onOpenStaticToolConfig: () => { },
    }),
  );

  assert.match(markup, /配置 规则扫描/);
  assert.doesNotMatch(markup, /配置 PMD Java 扫描/);
});
