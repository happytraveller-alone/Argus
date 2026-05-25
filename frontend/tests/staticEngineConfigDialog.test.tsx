import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { StaticEngineConfigDialogContent } from "../src/components/scan/StaticEngineConfigDialog.tsx";

globalThis.React = React;

test("StaticEngineConfigDialogContent renders placeholder text and footer actions for CodeQL", () => {
  const markup = renderToStaticMarkup(
    createElement(StaticEngineConfigDialogContent, {
      engine: "codeql",
      scanMode: "static",
      enabled: true,
      creating: false,
      blockedReason: null,
      onNavigateToEngineConfig: () => {},
      onRequestClose: () => {},
    }),
  );

  assert.match(markup, /CodeQL 配置/);
  assert.match(markup, /任务级配置即将开放/);
  assert.match(markup, /前往扫描引擎配置页/);
});

test("StaticEngineConfigDialogContent renders opengrep options without retired sandbox surface", () => {
  const markup = renderToStaticMarkup(
    createElement(StaticEngineConfigDialogContent, {
      engine: "opengrep",
      scanMode: "static",
      enabled: false,
      creating: false,
      blockedReason: null,
      opengrepSandbox: "a3s_box",
      onOpengrepSandboxChange: () => {},
      onNavigateToEngineConfig: () => {},
      onRequestClose: () => {},
    }),
  );

  assert.match(markup, /Opengrep 配置/);
  assert.match(markup, /Dockerfile 容器/);
  assert.match(markup, /A3S Box MicroVM/);
  assert.doesNotMatch(markup, new RegExp("Cube" + "Sandbox"));
  assert.match(markup, /aria-pressed="false"[^>]*>[\s\S]*Dockerfile 容器/);
});

test("StaticEngineConfigDialogContent renders Joern as backend-managed CPG scan", () => {
  const markup = renderToStaticMarkup(
    createElement(StaticEngineConfigDialogContent, {
      engine: "joern",
      scanMode: "static",
      enabled: true,
      creating: false,
      blockedReason: null,
      onNavigateToEngineConfig: () => {},
      onRequestClose: () => {},
    }),
  );

  assert.match(markup, /Joern 配置/);
  assert.match(markup, /Joern 图结构扫描/);
  assert.match(markup, /后端配置的 Joern 镜像/);
  assert.match(markup, /libplist C 代码 CPG/);
  assert.doesNotMatch(markup, /启用规则/);
});
