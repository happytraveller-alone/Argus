import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Dialog } from "../src/components/ui/dialog.tsx";
import { StaticEngineConfigDialogContent } from "../src/components/scan/StaticEngineConfigDialog.tsx";

globalThis.React = React;

test("StaticEngineConfigDialogContent renders YASA controls and footer actions", () => {
  const markup = renderToStaticMarkup(
    createElement(
      Dialog,
      { open: true },
      createElement(StaticEngineConfigDialogContent, {
        engine: "yasa",
        scanMode: "hybrid",
        enabled: true,
        creating: false,
        blockedReason: null,
        yasaLanguage: "auto",
        onYasaLanguageChange: () => {},
        yasaRuleConfigs: [{ id: "cfg-1", name: "custom", language: "javascript" }],
        selectedYasaRuleConfigId: "default",
        onSelectedYasaRuleConfigIdChange: () => {},
        showYasaAutoSkipHint: true,
        onNavigateToEngineConfig: () => {},
        onRequestClose: () => {},
      }),
    ),
  );

  assert.match(markup, /YASA 配置/);
  assert.match(markup, /YASA 规则配置/);
  assert.match(markup, /YASA 语言/);
  assert.match(markup, /前往扫描引擎配置页/);
  assert.match(markup, /YASA 将自动跳过/);
});

test("StaticEngineConfigDialogContent renders placeholder text for opengrep", () => {
  const markup = renderToStaticMarkup(
    createElement(
      Dialog,
      { open: true },
      createElement(StaticEngineConfigDialogContent, {
        engine: "opengrep",
        scanMode: "static",
        enabled: false,
        creating: false,
        blockedReason: null,
        yasaLanguage: "auto",
        onYasaLanguageChange: () => {},
        yasaRuleConfigs: [],
        selectedYasaRuleConfigId: "default",
        onSelectedYasaRuleConfigIdChange: () => {},
        showYasaAutoSkipHint: false,
        onNavigateToEngineConfig: () => {},
        onRequestClose: () => {},
      }),
    ),
  );

  assert.match(markup, /Opengrep 配置/);
  assert.match(markup, /任务级配置即将开放/);
});
