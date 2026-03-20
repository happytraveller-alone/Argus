import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import BanditRules from "../src/pages/BanditRules.tsx";

globalThis.React = React;

test("BanditRules renders detail/delete/recover related controls", () => {
  const markup = renderToStaticMarkup(
    createElement(MemoryRouter, {}, createElement(BanditRules)),
  );

  assert.match(markup, /搜索名称\/ID\/描述/);
  assert.match(markup, /删除状态/);
  assert.match(markup, /重置/);
  assert.match(markup, />列</);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
  assert.match(markup, /加载中\.\.\./);
});
