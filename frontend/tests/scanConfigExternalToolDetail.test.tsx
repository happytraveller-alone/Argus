import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ScanConfigExternalToolDetailContent,
  type ExternalToolDetailContentProps,
} from "../src/pages/ScanConfigExternalToolDetail.tsx";
import type {
  SkillDetailResponse,
  SkillTestEvent,
  SkillTestResult,
} from "../src/pages/skill-test/types.ts";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

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
  tool_test_preset: null,
  category: "代码读取与定位",
  goal: "获取真实代码窗口、焦点行和附近逻辑。",
  task_list: ["围绕锚点取证", "返回最小代码窗口", "高亮焦点行"],
  input_checklist: ["`file_path` (string, required)", "`anchor_line` (number, required)"],
  example_input: "{\"file_path\": \"src/main.c\", \"anchor_line\": 2}",
  pitfalls: ["不要无锚点取窗口。"],
  sample_prompts: ["读取 plist 解析入口", "这个 skill 能直接围绕锚点取证吗？"],
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

const structuredDetail: SkillDetailResponse = {
  ...supportedDetail,
  skill_id: "dataflow_analysis",
  name: "dataflow_analysis",
  summary: "分析 Source 到 Sink 的传播链与污点证据。",
  entrypoint: "scan-core/dataflow_analysis",
  test_mode: "structured_tool",
  tool_test_preset: {
    project_name: "libplist",
    file_path: "src/xplist.c",
    function_name: "plist_from_xml",
    line_start: null,
    line_end: null,
    tool_input: {
      variable_name: "plist_xml",
      sink_hints: ["xmlReadMemory", "xmlParseMemory", "xml_to_node"],
    },
  },
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
  tool_name: null,
  target_function: null,
  resolved_file_path: null,
  resolved_line_start: null,
  resolved_line_end: null,
  runner_image: null,
  input_payload: null,
  cleanup: {
    success: true,
    temp_dir: "/tmp/skill-test-get_code_window-1234",
    error: null,
  },
};

function renderContent(props: Partial<ExternalToolDetailContentProps>) {
  return renderToStaticMarkup(
    createElement(SsrRouter, {}, createElement(ScanConfigExternalToolDetailContent, {
      toolType: "skill",
      toolId: "get_code_window",
      toolName: "get_code_window",
      skillDetail: supportedDetail,
      prompt: "读取 plist 解析入口",
      examplePrompts: supportedDetail.sample_prompts,
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
    skillDetail: {
      ...disabledDetail,
      category: "可达性与逻辑分析",
      goal: "沉淀结构化流证据，支撑真实性判断。",
      task_list: ["识别 source/sink", "输出传播步骤", "标记风险等级"],
      input_checklist: ["`file_path` (string, optional): 直接从文件读取源码"],
      example_input: "{\"file_path\":\"src/xplist.c\"}",
      pitfalls: ["不要把数据流结果直接当成最终确认。"],
      sample_prompts: ["检查 plist_xml 是否流向 xmlReadMemory"],
    },
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

test("ScanConfigExternalToolDetailContent 仅把带 native payload 的事件当作 latest evidence", () => {
  const markup = renderContent({
    events: [
      ...streamEvents,
      {
        id: 6,
        type: "tool_result",
        tool_name: "get_code_window",
        tool_output: { result: "legacy-only", truncated: false },
        metadata: {
          tool_status: "completed",
        },
        ts: 1710000005,
      },
    ],
  });

  assert.match(markup, /src\/main\.c:1-3/);
  assert.match(markup, /return 0;/);
});

test("ScanConfigExternalToolDetailContent 对 structured_tool 渲染结构化参数表单", () => {
  const markup = renderContent({
    toolId: "dataflow_analysis",
    toolName: "dataflow_analysis",
    skillDetail: {
      ...structuredDetail,
      category: "可达性与逻辑分析",
      goal: "沉淀结构化流证据，支撑真实性判断。",
      task_list: ["识别 source/sink", "输出传播步骤", "标记风险等级"],
      input_checklist: ["`file_path` (string, optional): 直接从文件读取源码"],
      example_input: "{\"file_path\":\"src/xplist.c\"}",
      pitfalls: ["不要把数据流结果直接当成最终确认。"],
      sample_prompts: [],
    },
    prompt: "",
    examplePrompts: [],
    events: [],
    result: {
      ...finalResult,
      test_mode: "structured_tool",
      tool_name: "dataflow_analysis",
      target_function: "plist_from_xml",
      resolved_file_path: "src/xplist.c",
      resolved_line_start: 42,
      resolved_line_end: 58,
      runner_image: "vulhunter/flow-parser-runner-local:latest",
      input_payload: structuredDetail.tool_test_preset,
    },
  });

  assert.match(markup, /结构化工具测试/);
  assert.match(markup, /src\/xplist\.c/);
  assert.match(markup, /plist_from_xml/);
  assert.match(markup, /variable_name/);
  assert.match(markup, /sink_hints/);
  assert.match(markup, /flow-parser-runner-local:latest/);
  assert.doesNotMatch(markup, /请输入基于 libplist 的自然语言测试问题/);
});

test("ScanConfigExternalToolDetailContent 对 builtin Prompt Skill 渲染只读详情与启停入口", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(ScanConfigExternalToolDetailContent, {
        toolType: "prompt-builtin",
        toolId: "analysis",
        toolName: "Analysis Agent Prompt Skill",
        promptSkillDetail: {
          tool_type: "prompt-builtin",
          tool_id: "analysis",
          name: "Analysis Agent Prompt Skill",
          summary: "围绕单风险点做证据闭环。",
          status_label: "停用",
          is_enabled: false,
          is_available: true,
          content: "围绕单风险点做证据闭环。",
          agent_key: "analysis",
          scope: null,
          is_builtin: true,
          can_toggle: true,
          can_edit: false,
          can_delete: false,
        },
        events: [],
        result: null,
        running: false,
        onPromptChange: () => {},
        onRun: () => {},
        onStop: () => {},
      } as ExternalToolDetailContentProps),
    ),
  );

  assert.match(markup, /Prompt Skill 详情/);
  assert.match(markup, /Analysis Agent Prompt Skill/);
  assert.match(markup, /Analysis Agent/);
  assert.match(markup, /停用/);
  assert.match(markup, />启用</);
  assert.doesNotMatch(markup, />编辑</);
  assert.doesNotMatch(markup, />删除</);
  assert.doesNotMatch(markup, /运行测试/);
});

test("ScanConfigExternalToolDetailContent 对 custom Prompt Skill 渲染编辑与删除入口", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      {},
      createElement(ScanConfigExternalToolDetailContent, {
        toolType: "prompt-custom",
        toolId: "custom-1",
        toolName: "Verification Notes",
        promptSkillDetail: {
          tool_type: "prompt-custom",
          tool_id: "custom-1",
          name: "Verification Notes",
          summary: "补充验证阶段的证据约束。",
          status_label: "启用",
          is_enabled: true,
          is_available: true,
          content: "补充验证阶段的证据约束。",
          agent_key: "verification",
          scope: "agent_specific",
          is_builtin: false,
          can_toggle: true,
          can_edit: true,
          can_delete: true,
        },
        events: [],
        result: null,
        running: false,
        onPromptChange: () => {},
        onRun: () => {},
        onStop: () => {},
      } as ExternalToolDetailContentProps),
    ),
  );

  assert.match(markup, /Prompt Skill 详情/);
  assert.match(markup, /Verification Notes/);
  assert.match(markup, /Verification Agent/);
  assert.match(markup, /智能体专属/);
  assert.match(markup, />停用</);
  assert.match(markup, />编辑</);
  assert.match(markup, />删除</);
});

test("ScanConfigExternalToolDetailContent 返回链接保留原列表 query", () => {
  const markup = renderToStaticMarkup(
    createElement(
      SsrRouter,
      { location: "/scan-config/external-tools/skill/get_code_window?page=3&q=xml&type=prompt-custom&status=enabled" },
      createElement(ScanConfigExternalToolDetailContent, {
        toolType: "skill",
        toolId: "get_code_window",
        toolName: "get_code_window",
        skillDetail: supportedDetail,
        prompt: "读取 plist 解析入口",
        examplePrompts: ["读取 plist 解析入口"],
        events: [],
        result: null,
        running: false,
        onPromptChange: () => {},
        onRun: () => {},
        onStop: () => {},
        returnToSearch: "?page=3&q=xml&type=prompt-custom&status=enabled",
      } as ExternalToolDetailContentProps),
    ),
  );

  assert.match(markup, /\/scan-config\/external-tools\?page=3&amp;q=xml&amp;type=prompt-custom&amp;status=enabled/);
});
