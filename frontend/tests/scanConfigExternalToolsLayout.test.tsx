import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SkillToolsPanel from "../src/pages/intelligent-scan/SkillToolsPanel.tsx";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const initialSkillCatalog = [
  {
    skill_id: "search_code",
    name: "search_code",
    summary: "在项目中检索代码片段、关键字与命中位置。",
    entrypoint: "scan-core/search_code",
    namespace: "scan-core",
    aliases: [],
    has_scripts: false,
    has_bin: false,
    has_assets: false,
  },
  {
    skill_id: "run_code",
    name: "run_code",
    summary: "运行验证 Harness/PoC，收集动态执行证据。",
    entrypoint: "scan-core/run_code",
    namespace: "scan-core",
    aliases: [],
    has_scripts: false,
    has_bin: false,
    has_assets: false,
  },
];

test("SkillToolsPanel 渲染为表格列表并保留详情入口", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(SkillToolsPanel, { initialSkillCatalog }),
    ),
  );

  assert.match(markup, /<table/i);
  assert.match(markup, /序号/);
  assert.match(markup, /工具名称/);
  assert.match(markup, /类型/);
  assert.match(markup, /执行功能/);
  assert.match(markup, /PROMPT/);
  assert.match(markup, /CLI/);
  assert.match(markup, /检索关键字; 返回 file_path:line 定位摘要; 提示继续收敛或取证/);
  assert.match(markup, />详情</);
  assert.doesNotMatch(markup, /repeat\(auto-fit,\s*minmax\(/);
});

test("SkillToolsPanel 小屏通过表格容器提供横向滚动", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(SkillToolsPanel, { initialSkillCatalog }),
    ),
  );

  assert.match(markup, /overflow-x-auto/);
  assert.match(markup, /min-w-\[/);
});
