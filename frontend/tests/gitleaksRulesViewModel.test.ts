import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import GitleaksRules from "../src/pages/GitleaksRules.tsx";

globalThis.React = React;

test("GitleaksRules renders expected unified table layout", () => {
  const markup = renderToStaticMarkup(
    createElement(MemoryRouter, {}, createElement(GitleaksRules)),
  );

  assert.match(markup, /有效规则总数/);
  assert.match(markup, /高熵规则数量/);
  assert.match(markup, /搜索名称\/ID\/正则/);
  assert.match(markup, /熵值区间/);
  assert.match(markup, /重置/);
  assert.match(markup, />列</);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
  assert.match(markup, /加载中\.\.\./);
});
