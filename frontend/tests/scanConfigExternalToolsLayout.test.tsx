import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ScanConfigExternalTools from "../src/pages/ScanConfigExternalTools.tsx";
import type { ExternalToolResourcePayload } from "../src/shared/api/database.ts";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

const initialResources = [
  {
    tool_type: "skill" as const,
    tool_id: "search_code",
    name: "search_code",
    summary: "在项目中检索代码片段、关键字与命中位置。",
    entrypoint: "scan-core/search_code",
    namespace: "scan-core",
    resource_kind_label: "Scan Core",
    status_label: "启用",
    is_enabled: true,
    is_available: true,
    detail_supported: true,
    agent_key: null,
    scope: null,
  },
  {
    tool_type: "prompt-builtin" as const,
    tool_id: "analysis",
    name: "Analysis Agent Prompt Skill",
    summary: "围绕单风险点做证据闭环。",
    entrypoint: null,
    namespace: "prompt-skill",
    resource_kind_label: "Builtin Prompt Skill",
    status_label: "停用",
    is_enabled: false,
    is_available: true,
    detail_supported: true,
    agent_key: "analysis",
    scope: null,
  },
  {
    tool_type: "prompt-custom" as const,
    tool_id: "custom-1",
    name: "Verification Notes",
    summary: "补充验证阶段的证据约束。",
    entrypoint: null,
    namespace: "prompt-skill",
    resource_kind_label: "Custom Prompt Skill",
    status_label: "启用",
    is_enabled: true,
    is_available: true,
    detail_supported: true,
    agent_key: "verification",
    scope: "agent_specific",
  },
] as ExternalToolResourcePayload[];

test("ScanConfigExternalTools 渲染统一混合表并暴露 Prompt Skill 创建入口", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(ScanConfigExternalTools, { initialResources }),
    ),
  );

  assert.match(markup, /<table/i);
  assert.match(markup, /名称/);
  assert.match(markup, /类型/);
  assert.match(markup, /执行功能/);
  assert.match(markup, /状态/);
  assert.match(markup, /新增 Prompt Skill/);
  assert.match(markup, /Scan Core/);
  assert.match(markup, /Builtin Prompt Skill/);
  assert.match(markup, /Custom Prompt Skill/);
  assert.match(markup, /Analysis Agent Prompt Skill/);
  assert.match(markup, /Verification Notes/);
  assert.match(markup, /停用/);
  assert.match(markup, /启用/);
  assert.match(markup, />详情</);
  assert.match(markup, />停用</);
  assert.match(markup, /\/scan-config\/external-tools\/prompt-builtin\/analysis/);
  assert.match(markup, /\/scan-config\/external-tools\/prompt-custom\/custom-1/);
  assert.doesNotMatch(markup, /可用性/);
  assert.match(markup, /执行功能[\s\S]*状态[\s\S]*操作/);
});

test("ScanConfigExternalTools 统一混合表仍通过表格容器提供横向滚动", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      null,
      createElement(ScanConfigExternalTools, { initialResources }),
    ),
  );

  assert.match(markup, /overflow-x-auto/);
  assert.match(markup, /min-w-\[/);
});
