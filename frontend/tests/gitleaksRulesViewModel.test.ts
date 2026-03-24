import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GitleaksRules from "../src/pages/GitleaksRules.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("GitleaksRules renders expected unified table layout", () => {
  const markup = renderToStaticMarkup(
    createElement(SsrRouter, {}, createElement(GitleaksRules)),
  );

  assert.match(markup, /有效规则总数/);
  assert.match(markup, /高熵规则数量/);
  assert.match(markup, /规则名称/);
  assert.match(markup, /aria-label="筛选熵值"/);
  assert.match(markup, /aria-label="筛选启用状态"/);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
  assert.match(markup, /加载中\.\.\./);
});
