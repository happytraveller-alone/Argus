import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  PmdImportDialogContent,
  type PmdImportDialogContentProps,
} from "../src/pages/PmdRules.tsx";

globalThis.React = React;

function createProps(
  overrides: Partial<PmdImportDialogContentProps> = {},
): PmdImportDialogContentProps {
  return {
    importName: "",
    importDescription: "",
    importing: false,
    onImportNameChange: () => {},
    onImportDescriptionChange: () => {},
    onImportFileChange: () => {},
    onImport: () => {},
    ...overrides,
  };
}

test("PmdImportDialogContent renders import form fields and default action text", () => {
  const markup = renderToStaticMarkup(
    createElement(PmdImportDialogContent, createProps()),
  );

  assert.match(markup, /导入自定义规则/);
  assert.match(markup, /上传自定义 PMD XML ruleset/);
  assert.match(markup, /输入 ruleset 名称/);
  assert.match(markup, /type="file"/);
  assert.match(markup, /可选：填写 ruleset 描述/);
  assert.match(markup, /导入 XML ruleset/);
});

test("PmdImportDialogContent shows loading copy when import is in progress", () => {
  const markup = renderToStaticMarkup(
    createElement(
      PmdImportDialogContent,
      createProps({
        importing: true,
      }),
    ),
  );

  assert.match(markup, /导入中\.\.\./);
});
