import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import PhpstanRules from "../src/pages/PhpstanRules.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("PhpstanRules renders expected layout blocks", () => {
  const markup = renderToStaticMarkup(
    createElement(SsrRouter, {}, createElement(PhpstanRules)),
  );

  assert.match(markup, /有效规则总数/);
  assert.match(markup, /规则来源数量/);
  assert.match(markup, /扩展包数量/);
  assert.match(markup, />规则</);
  assert.match(markup, /筛选规则/);
  assert.match(markup, /启用状态/);
  assert.match(markup, /aria-label="筛选启用状态"/);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
  assert.match(markup, /加载中\.\.\./);
});
