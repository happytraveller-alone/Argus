import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes } from "react-router-dom";

import ScanConfigEngines from "../src/pages/ScanConfigEngines.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("ScanConfigEngines renders pmd rules page when tab=pmd", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      { location: "/scan-config/engines?tab=pmd" },
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

	assert.match(markup, /批量启用/);
	assert.match(markup, /批量禁用/);
	assert.match(markup, /取消操作/);
	assert.match(markup, /导入自定义规则/);
	assert.match(markup, /规则集/);
	assert.doesNotMatch(markup, /导入 XML ruleset/);
});
