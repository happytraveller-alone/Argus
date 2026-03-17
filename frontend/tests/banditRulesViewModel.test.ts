import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import BanditRules from "../src/pages/BanditRules.tsx";

globalThis.React = React;

test("BanditRules renders detail/delete/recover related controls", () => {
  const markup = renderToStaticMarkup(createElement(BanditRules));

  assert.match(markup, /搜索规则/);
  assert.match(markup, /删除状态/);
  assert.match(markup, /重置/);
  assert.match(markup, /加载中\.\.\./);
});
