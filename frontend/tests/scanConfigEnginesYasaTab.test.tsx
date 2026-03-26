import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes } from "react-router-dom";

import ScanConfigEngines from "../src/pages/ScanConfigEngines.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("ScanConfigEngines renders yasa rules page when tab=yasa", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      { location: "/scan-config/engines?tab=yasa" },
      createElement(
        Routes,
        null,
        createElement(Route, {
          path: "/scan-config/engines",
          element: createElement(ScanConfigEngines),
        }),
      ),
    ),
  );

  assert.match(markup, /导入自定义规则/);
  assert.match(markup, /高级配置/);
  assert.match(markup, /有效规则总数/);
  assert.doesNotMatch(markup, /YASA 运行配置/);
});
