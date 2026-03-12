import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ErrorBoundaryFallbackView,
} from "../src/components/common/ErrorBoundaryFallbackView.tsx";
import {
  resolveErrorBoundaryViewModel,
} from "../src/components/common/errorBoundaryState.ts";

globalThis.React = React;

function createComponentStack(): React.ErrorInfo {
  return {
    componentStack: "\n    at Projects\n    at App",
  };
}

test("Projects dynamic import failures resolve to backend-offline copy", () => {
  const state = resolveErrorBoundaryViewModel(
    new Error(
      "Failed to fetch dynamically imported module: http://localhost:3000/src/pages/Projects.tsx?t=1773289874285",
    ),
  );

  assert.equal(state.variant, "backend-offline");
  assert.equal(state.title, "服务没有启动");
  assert.equal(state.description, "请启动后再使用项目");
  assert.deepEqual(
    state.actions.map((action) => action.label),
    ["重试连接", "返回首页", "刷新页面"],
  );
});

test("API proxy and network failures resolve to backend-offline copy", () => {
  const offlineErrors = [
    {
      isAxiosError: true,
      message: "Network Error",
      config: { url: "/api/v1/projects/" },
    },
    {
      isAxiosError: true,
      message: "Request failed with status code 502",
      config: { url: "/api/v1/projects/" },
      response: { status: 502 },
    },
    new TypeError("Failed to fetch"),
  ];

  for (const error of offlineErrors) {
    const state = resolveErrorBoundaryViewModel(error);
    assert.equal(state.variant, "backend-offline");
    assert.equal(state.title, "服务没有启动");
  }
});

test("unrelated render errors stay on the generic error page", () => {
  const state = resolveErrorBoundaryViewModel(
    new Error("Cannot read properties of undefined"),
  );

  assert.equal(state.variant, "generic");
  assert.equal(state.title, "出错了");
  assert.equal(state.description, "应用遇到了一个错误");
});

test("backend-offline fallback keeps dev diagnostics visible", () => {
  const error = new Error(
    "Failed to fetch dynamically imported module: http://localhost:3000/src/pages/Projects.tsx?t=1773289874285",
  );
  error.stack = [
    "Error: Failed to fetch dynamically imported module",
    "    at Projects",
  ].join("\n");

  const markup = renderToStaticMarkup(
    createElement(ErrorBoundaryFallbackView, {
      state: resolveErrorBoundaryViewModel(error),
      error,
      errorInfo: createComponentStack(),
      onReset: () => {},
      onGoHome: () => {},
      onReload: () => {},
      isDev: true,
    }),
  );

  assert.match(markup, /服务没有启动/);
  assert.match(markup, /请启动后再使用项目/);
  assert.match(markup, /查看错误堆栈/);
  assert.match(markup, /查看组件堆栈/);
  assert.match(markup, /Failed to fetch dynamically imported module/);
  assert.match(markup, /重试连接/);
});
