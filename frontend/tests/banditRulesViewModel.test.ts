import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import BanditRules from "../src/pages/BanditRules.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("BanditRules renders detail/delete/recover related controls", () => {
  const markup = renderToStaticMarkup(
    createElement(SsrRouter, {}, createElement(BanditRules)),
  );

  assert.match(markup, /规则名称/);
  assert.match(markup, /启用状态/);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
  assert.match(markup, /加载中\.\.\./);
});
