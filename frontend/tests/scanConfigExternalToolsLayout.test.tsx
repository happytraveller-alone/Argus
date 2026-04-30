import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ScanConfigExternalTools from "../src/pages/ScanConfigExternalTools.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("ScanConfigExternalTools 渲染占位页", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(ScanConfigExternalTools),
    ),
  );

  assert.match(markup, /外部工具列表/);
  assert.match(markup, /暂无外部工具/);
  assert.doesNotMatch(markup, /<table/i);
});
