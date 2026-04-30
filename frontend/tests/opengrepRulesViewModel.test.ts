import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OpengrepRules from "../src/pages/OpengrepRules.tsx";
import { LanguageProvider } from "../src/shared/i18n/LanguageProvider.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;
globalThis.document = { body: {} } as Document;

test("OpengrepRules renders unified table layout shell", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(LanguageProvider, null, createElement(OpengrepRules)),
    ),
  );

  assert.match(markup, /规则数量/);
  assert.match(markup, /支持语言/);
  assert.match(markup, /规则名称/);
  assert.match(markup, /规则来源/);
  assert.match(markup, /语言/);
  assert.match(markup, /序号/);
  assert.match(markup, /上一页/);
  assert.match(markup, /下一页/);
});
