import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import {
  ScanConfigExternalToolDetailContent,
  type ExternalToolDetailContentProps,
} from "../src/pages/ScanConfigExternalToolDetail.tsx";
import type {
  SkillDetailResponse,
  SkillTestEvent,
  SkillTestResult,
} from "../src/pages/skill-test/types.ts";
import type { SkillToolCatalogItem } from "../src/pages/intelligent-scan/skillToolsCatalog.ts";

globalThis.React = React;

const codeWindowCatalog: SkillToolCatalogItem = {
  id: "get_code_window",
  category: "代码读取与定位",
  summary: "围绕锚点返回极小代码窗口，是唯一代码取证工具。",
  goal: "获取真实代码窗口、焦点行和附近逻辑。",
  taskList: ["围绕锚点取证", "返回最小代码窗口", "高亮焦点行"],
  inputChecklist: ["`file_path` (string, required)", "`anchor_line` (number, required)"],
  exampleInput: "{\"file_path\": \"src/main.c\", \"anchor_line\": 2}",
  pitfalls: ["不要无锚点取窗口。"],
};

const supportedDetail: SkillDetailResponse = {
  enabled: true,
  skill_id: "get_code_window",
  name: "get_code_window",
  namespace: "scan-core",
  summary: "围绕锚点返回极小代码窗口。",
  entrypoint: "scan-core/get_code_window",
  mirror_dir: "",
  source_root: "",
  source_dir: "",
  source_skill_md: "",
  aliases: [],
  has_scripts: false,
  has_bin: false,
  has_assets: false,
  files_count: 0,
  workflow_content: null,
  workflow_truncated: false,
  workflow_error: "scan_core_static_catalog",
  test_supported: true,
  test_mode: "single_skill_strict",
  test_reason: null,
  default_test_project_name: "libplist",
};

const disabledDetail: SkillDetailResponse = {
  ...supportedDetail,
  skill_id: "dataflow_analysis",
  name: "dataflow_analysis",
  summary: "分析 Source 到 Sink 的传播链与污点证据。",
  entrypoint: "scan-core/dataflow_analysis",
  test_supported: false,
  test_mode: "disabled",
  test_reason: "首版仅开放可直接基于 libplist 自然语言提问的 skill；数据流分析依赖更复杂的上下文建模。",
};

const streamEvents: SkillTestEvent[] = [
  {
    id: 1,
    type: "llm_thought",
    message: "我先读取 plist 相关入口，再确认解析流程是否会经过 plist_from_memory。",
    ts: 1710000000,
  },
  {
    id: 2,
    type: "llm_action",
    message: "Action: get_code_window",
    metadata: { selected_skill: "get_code_window" },
    ts: 1710000001,
  },
  {
    id: 3,
    type: "tool_call",
    tool_name: "get_code_window",
    tool_input: { file_path: "src/main.c", anchor_line: 2 },
    ts: 1710000002,
  },
  {
    id: 4,
    type: "tool_result",
    tool_name: "get_code_window",
    tool_output: "文件: src/main.c",
    metadata: {
      render_type: "code_window",
      display_command: "get_code_window",
      command_chain: ["get_code_window"],
      entries: [
        {
          file_path: "src/main.c",
          start_line: 1,
          end_line: 3,
          focus_line: 2,
          language: "c",
          lines: [
            { line_number: 1, text: "int main() {", kind: "context" },
            { line_number: 2, text: "  return 0;", kind: "focus" },
            { line_number: 3, text: "}", kind: "context" },
          ],
        },
      ],
    },
    ts: 1710000003,
  },
  {
    id: 5,
    type: "project_cleanup",
    message: "临时目录清理完成",
    metadata: {
      temp_dir: "/tmp/skill-test-get_code_window-1234",
      cleanup_success: true,
    },
    ts: 1710000004,
  },
];

const finalResult: SkillTestResult = {
  skill_id: "get_code_window",
  final_text: "libplist 的主解析入口位于 `src/main.c`，后续会继续调用 plist 解析逻辑。",
  project_name: "libplist",
  test_mode: "single_skill_strict",
  default_test_project_name: "libplist",
  project_root: "/tmp/skill-test-get_code_window-1234/libplist-2.7.0",
  cleanup: {
    success: true,
    temp_dir: "/tmp/skill-test-get_code_window-1234",
    error: null,
  },
};

function renderContent(props: Partial<ExternalToolDetailContentProps>) {
  return renderToStaticMarkup(
    createElement(MemoryRouter, {}, createElement(ScanConfigExternalToolDetailContent, {
      toolType: "skill",
      toolId: "get_code_window",
      toolName: "get_code_window",
      skillCatalogItem: codeWindowCatalog,
      skillDetail: supportedDetail,
      prompt: "读取 plist 解析入口",
      examplePrompts: ["读取 plist 解析入口", "这个 skill 能直接围绕锚点取证吗？"],
      events: streamEvents,
      result: finalResult,
      running: false,
      onPromptChange: () => {},
      onRun: () => {},
      onStop: () => {},
      ...props,
    })),
  );
}

test("ScanConfigExternalToolDetailContent 对 disabled skill 展示禁用原因并隐藏运行按钮", () => {
  const markup = renderContent({
    toolId: "dataflow_analysis",
    toolName: "dataflow_analysis",
    skillCatalogItem: {
      ...codeWindowCatalog,
      id: "dataflow_analysis",
      category: "可达性与逻辑分析",
    },
    skillDetail: disabledDetail,
    events: [],
    result: null,
  });

  assert.match(markup, /测试已禁用/);
  assert.match(markup, /数据流分析依赖更复杂的上下文建模/);
  assert.doesNotMatch(markup, />运行测试</);
});

test("ScanConfigExternalToolDetailContent 渲染 skill 概览、事件流、结构化证据与最终结果", () => {
  const markup = renderContent({});

  assert.match(markup, /单技能严格模式/);
  assert.match(markup, /libplist/);
  assert.match(markup, /代码读取与定位/);
  assert.match(markup, /围绕锚点取证/);
  assert.match(markup, /示例提问/);
  assert.match(markup, /运行测试/);
  assert.match(markup, /思考（已折叠）/);
  assert.match(markup, /Action: get_code_window/);
  assert.match(markup, /文件: src\/main\.c/);
  assert.match(markup, /src\/main\.c:1-3/);
  assert.match(markup, /return 0;/);
  assert.match(markup, /最终结果/);
  assert.match(markup, /主解析入口位于/);
  assert.match(markup, /临时目录已清理/);
  assert.match(markup, /\/tmp\/skill-test-get_code_window-1234/);
});
