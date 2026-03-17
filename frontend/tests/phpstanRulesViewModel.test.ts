import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import PhpstanRules from "../src/pages/PhpstanRules.tsx";

globalThis.React = React;

test("PhpstanRules renders expected layout blocks", () => {
  const markup = renderToStaticMarkup(createElement(PhpstanRules));

  assert.match(markup, /有效规则总数/);
  assert.match(markup, /扩展包数量/);
  assert.match(markup, /搜索规则/);
  assert.match(markup, /删除状态/);
  assert.match(markup, /重置/);
  assert.match(markup, /加载中\.\.\./);
});
