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

const readFileCatalog: SkillToolCatalogItem = {
  id: "read_file",
  category: "代码读取与定位",
  summary: "窗口化读取代码并返回按行结构化证据。",
  goal: "获取真实代码窗口、焦点行和附近逻辑。",
  taskList: ["读取目标片段", "返回行号窗口", "高亮焦点行"],
  inputChecklist: ["`file_path` (string, required)", "`start_line` / `end_line` (number, optional)"],
  exampleInput: "{\"file_path\": \"src/main.c\"}",
  pitfalls: ["不要无锚点大段读取整个项目。"],
};

const supportedDetail: SkillDetailResponse = {
  enabled: true,
  skill_id: "read_file",
  name: "read_file",
  namespace: "scan-core",
  summary: "读取项目文件内容并返回证据上下文。",
  entrypoint: "scan-core/read_file",
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
    message: "Action: read_file",
    metadata: { selected_skill: "read_file" },
    ts: 1710000001,
  },
  {
    id: 3,
    type: "tool_call",
    tool_name: "read_file",
    tool_input: { file_path: "src/main.c" },
    ts: 1710000002,
  },
  {
    id: 4,
    type: "tool_result",
    tool_name: "read_file",
    tool_output: "文件: src/main.c",
    metadata: {
      render_type: "code_window",
      display_command: "read_file -> sed",
      command_chain: ["read_file", "sed"],
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
      temp_dir: "/tmp/skill-test-read_file-1234",
      cleanup_success: true,
    },
    ts: 1710000004,
  },
];

const finalResult: SkillTestResult = {
  skill_id: "read_file",
  final_text: "libplist 的主解析入口位于 `src/main.c`，后续会继续调用 plist 解析逻辑。",
  project_name: "libplist",
  test_mode: "single_skill_strict",
  default_test_project_name: "libplist",
  project_root: "/tmp/skill-test-read_file-1234/libplist-2.7.0",
  cleanup: {
    success: true,
    temp_dir: "/tmp/skill-test-read_file-1234",
    error: null,
  },
};

function renderContent(props: Partial<ExternalToolDetailContentProps>) {
  return renderToStaticMarkup(
    createElement(MemoryRouter, {}, createElement(ScanConfigExternalToolDetailContent, {
      toolType: "skill",
      toolId: "read_file",
      toolName: "read_file",
      skillCatalogItem: readFileCatalog,
      skillDetail: supportedDetail,
      prompt: "读取 plist 解析入口",
      examplePrompts: ["读取 plist 解析入口", "这个 skill 能直接定位入口函数吗？"],
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

test("ScanConfigExternalToolDetailContent 在 mcp 类型下保留占位说明", () => {
  const markup = renderToStaticMarkup(
    createElement(MemoryRouter, {}, createElement(ScanConfigExternalToolDetailContent, {
      toolType: "mcp",
      toolId: "legacy-mcp",
      toolName: "Legacy MCP",
      skillCatalogItem: null,
      skillDetail: null,
      prompt: "",
      examplePrompts: [],
      events: [],
      result: null,
      running: false,
      onPromptChange: () => {},
      onRun: () => {},
      onStop: () => {},
    })),
  );

  assert.match(markup, /MCP/);
  assert.match(markup, /详情页待设计/);
  assert.match(markup, /当前页面只保留详情页骨架/);
});

test("ScanConfigExternalToolDetailContent 对 disabled skill 展示禁用原因并隐藏运行按钮", () => {
  const markup = renderContent({
    toolId: "dataflow_analysis",
    toolName: "dataflow_analysis",
    skillCatalogItem: {
      ...readFileCatalog,
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
  assert.match(markup, /读取目标片段/);
  assert.match(markup, /示例提问/);
  assert.match(markup, /运行测试/);
  assert.match(markup, /思考（已折叠）/);
  assert.match(markup, /read_file -&gt; sed/);
  assert.match(markup, /src\/main\.c:1-3/);
  assert.match(markup, /最终结果/);
  assert.match(markup, /主解析入口位于/);
  assert.match(markup, /临时目录已清理/);
  assert.match(markup, /\/tmp\/skill-test-read_file-1234/);
});
