import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  YasaRuntimeConfigContent,
  type YasaRuntimeConfigContentProps,
} from "../src/pages/YasaRules.tsx";

globalThis.React = React;

function createProps(
  overrides: Partial<YasaRuntimeConfigContentProps> = {},
): YasaRuntimeConfigContentProps {
  return {
    runtimeConfigForm: {
      yasa_timeout_seconds: 600,
      yasa_orphan_stale_seconds: 120,
      yasa_exec_heartbeat_seconds: 15,
      yasa_process_kill_grace_seconds: 2,
    },
    runtimeConfigLoadError: null,
    savingRuntimeConfig: false,
    isRuntimeConfigDirty: false,
    onSave: () => {},
    onUpdateRuntimeField: () => {},
    ...overrides,
  };
}

test("YasaRuntimeConfigDialog renders runtime config fields when open", () => {
  const markup = renderToStaticMarkup(
    createElement(YasaRuntimeConfigContent, createProps()),
  );

  assert.match(markup, /YASA 运行配置/);
  assert.match(markup, /修改后对后续新建任务全局生效/);
  assert.match(markup, /YASA超时\(秒\)/);
  assert.match(markup, /Orphan判定阈值\(秒\)/);
  assert.match(markup, /心跳间隔\(秒\)/);
  assert.match(markup, /进程回收宽限\(秒\)/);
  assert.match(markup, /保存配置/);
  assert.match(markup, /disabled/);
});

test("YasaRuntimeConfigDialog renders runtime config load errors inside the dialog", () => {
  const markup = renderToStaticMarkup(
    createElement(
      YasaRuntimeConfigContent,
      createProps({
        runtimeConfigForm: null,
        runtimeConfigLoadError: "加载 YASA 运行配置失败，当前不可编辑",
      }),
    ),
  );

  assert.match(markup, /加载 YASA 运行配置失败，当前不可编辑/);
});

test("YasaRuntimeConfigDialog enables save button after runtime config changes", () => {
  const markup = renderToStaticMarkup(
    createElement(
      YasaRuntimeConfigContent,
      createProps({
        isRuntimeConfigDirty: true,
      }),
    ),
  );

  const saveButtonMarkup = markup.match(/<button[^>]*>保存配置<\/button>/)?.[0] || "";
  assert.ok(saveButtonMarkup.includes("保存配置"));
  assert.ok(!/\sdisabled(?:=|>)/.test(saveButtonMarkup));
});
