import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import SkillToolsPanel from "../src/pages/intelligent-scan/SkillToolsPanel.tsx";

globalThis.React = React;

test("SkillToolsPanel 默认渲染为自适应卡片网格而不是表格", () => {
  const markup = renderToStaticMarkup(
    createElement(MemoryRouter, null, createElement(SkillToolsPanel)),
  );

  assert.doesNotMatch(markup, /<table/i);
  assert.match(markup, /repeat\(auto-fit,\s*minmax\(/);
  assert.match(markup, /当前展示/);
  assert.match(markup, />SKILL</);
  assert.match(markup, />详情</);
});
