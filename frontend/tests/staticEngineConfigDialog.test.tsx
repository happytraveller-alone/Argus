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

test("StaticEngineConfigDialogContent shields deprecated CubeSandbox mode for opengrep", () => {
  const markup = renderToStaticMarkup(
    createElement(StaticEngineConfigDialogContent, {
      engine: "opengrep",
      scanMode: "static",
      enabled: false,
      creating: false,
      blockedReason: null,
      opengrepSandbox: "oci_cubesandbox",
      onOpengrepSandboxChange: () => {},
      onNavigateToEngineConfig: () => {},
      onRequestClose: () => {},
    }),
  );

  assert.match(markup, /Opengrep 配置/);
  assert.match(markup, /Dockerfile 容器/);
  assert.match(markup, /A3S Box MicroVM/);
  assert.doesNotMatch(markup, /CubeSandbox/);
  assert.match(markup, /aria-pressed="true"[^>]*><span[^>]*><span[^>]*><\/span><span[^>]*>Dockerfile 容器/);
});
