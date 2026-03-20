# 原子化检索工具重构开发文档

> 目标落盘路径：`docs/superpowers/plans/2026-03-20-atomic-search-tools-refactor.md`
> 文档日期：2026-03-20
> 当前状态：In Progress

## 1. 背景与目标

### 1.1 背景
当前智能/混合扫描流程中的高频主链路是：

1. `list_files`：查看目录/文件候选
2. `search_code`：搜索文本命中
3. `read_file`：读取大段代码上下文

这条链路的问题不在“缺少工具”，而在“工具职责混乱”：

- `read_file` 同时承担了文件读取、文件功能理解、函数功能理解、证据窗口提取等多种职责。
- `search_code` 目前还返回上下文窗口，与窗口读取能力重叠。
- Agent 依赖 prompt 建议选择工具，但系统层没有真正限制工具越权使用。
- 结果是：
  - Agent 容易走“宽搜 -> 大段读文件”的低效路径。
  - 代码证据、文件概览、函数理解混在一个工具里，前后端都难以稳定约束。
  - 无法从平台层保证“一个问题只走正确工具”。

### 1.2 重构目标
本次重构的核心目标是建立 **原子化检索工具体系**：

- 每个工具只做一件事。
- 工具之间职责不重叠。
- `read_file` 从主路径中彻底移除。
- `search_code` 收缩为纯定位器。
- 文件级概览、函数级理解、代码窗口取证彻底拆开。
- Agent 的工具使用策略从“建议”升级为“系统约束”。

### 1.3 非目标
本次不包含以下内容：

- 不重构 `smart_scan / quick_audit / pattern_match` 的底层算法。
- 不引入独立搜索服务或外部代码索引系统。
- 不保留 `read_file` 兼容转发能力作为对外公开能力。
- 不做“一个万能 inspect 工具”来重新聚合职责。

## 2. 最终工具模型

### 2.1 `list_files`
**职责**：列出目录/文件候选，用于缩小范围。  
**输入**：

- `directory`
- `pattern`
- `recursive_mode`
- `max_entries`

**输出**：

- `directories`
- `files`
- `truncated`
- `recommended_next_directories`

**禁止承担的职责**：

- 全文搜索
- 代码窗口输出
- 文件/函数语义解释

### 2.2 `search_code`
**职责**：纯命中定位。  
**输入**：

- `keyword`
- `directory`
- `file_pattern`
- `is_regex`
- `case_sensitive`
- `max_results`

**输出**：

- `matches[]`
- 每条 match 仅允许包含：
  - `file_path`
  - `line`
  - `column`
  - `match_text`
  - `symbol_name`
  - `match_kind`
- 补充字段：
  - `match_count_raw`
  - `match_count_returned`
  - `overflow_count`
  - `recommended_followup_tool`

**禁止承担的职责**：

- 前后文代码窗口
- 文件概览
- 函数解释
- 证据代码块渲染数据

### 2.3 `get_code_window`
**职责**：围绕锚点返回极小代码窗口。  
**输入**：

- `file_path`
- `anchor_line`
- `before_lines`
- `after_lines`

**输出**：

- `file_path`
- `start_line`
- `end_line`
- `focus_line`
- `language`
- `lines`

**禁止承担的职责**：

- 搜索
- 函数解释
- 文件概览
- 无锚点读取

### 2.4 `get_function_summary`
**职责**：解释单个函数做什么。  
**输入**：

- `file_path`
- `function_name` 或 `line`

**输出**：

- `resolved_function`
- `signature`
- `purpose`
- `inputs`
- `outputs`
- `key_calls`
- `risk_points`
- `related_symbols`

**禁止承担的职责**：

- 文件级概览
- 大段源码输出
- 搜索定位

### 2.5 `get_file_outline`
**职责**：给出文件整体结构与职责。  
**输入**：

- `file_path`

**输出**：

- `file_role`
- `key_symbols`
- `imports`
- `entrypoints`
- `risk_markers`
- `framework_hints`

**禁止承担的职责**：

- 函数内部解释
- 代码窗口输出
- 文本搜索

### 2.6 `get_symbol_body`
**职责**：提取函数/方法主体源码。  
**输入**：

- `file_path`
- `symbol_name`

**输出**：

- `symbol_name`
- `start_line`
- `end_line`
- `body`
- `language`

**说明**：

- 这是现有 `extract_function` 的原子化命名替代。
- 它只负责“提取源码”，不负责解释逻辑。

## 3. `read_file` 的处理方案

### 3.1 决策
- `read_file` 从新任务路径中完全移除。
- 不作为公开 catalog 能力。
- 不作为 skill test 对外能力。
- 不再在前端目录页中暴露。

### 3.2 保留范围
仅保留必要的工程级历史兼容：

- 前端对历史日志的展示兼容。
- 后端对旧 prompt/旧链路的临时隐藏兼容。
- 不再生成新的公开 `read_file` 示例与说明。

### 3.3 影响范围
需要同步替换：

- tool registry
- MCP router
- skill catalog
- Agent prompt
- 自动补救逻辑
- 前端工具详情页
- 技能测试台示例

## 4. Agent 使用规范

### 4.1 Recon 阶段
推荐链路：

1. `list_files`
2. 候选目录继续 `list_files`
3. 需要文本定位时 `search_code`
4. 需要理解文件作用时 `get_file_outline`

禁止：

- 直接使用 `get_code_window`
- 用 `search_code` 代替文件概览

### 4.2 Analysis 阶段
推荐链路：

1. `search_code`
2. `get_code_window`
3. `get_function_summary`
4. 必要时 `get_symbol_body`

禁止：

- 让 `search_code` 输出上下文窗口
- 用 `get_code_window` 替代函数解释
- 用 `get_symbol_body` 替代函数语义总结

### 4.3 Verification 阶段
推荐链路：

1. `search_code`
2. `get_code_window`
3. `get_symbol_body` 或 `get_function_summary`
4. 动态验证工具

禁止：

- 无锚点读取代码窗口
- 跳过定位直接做证据提取

## 5. 执行层治理规则

### 5.1 pre-hook 规则
在 Agent 调用工具前统一校验：

- 工具是否与当前意图匹配
- 参数是否满足原子职责边界
- 是否存在重复错误调用
- 是否存在“用窗口工具做总结”或“用搜索工具做阅读”的越权情况

### 5.2 post-hook 规则
在工具执行后统一检查输出是否越界：

- `search_code` 不允许包含窗口字段
- `get_code_window` 不允许跨度过大
- `get_file_outline` 不允许输出大段源码
- `get_function_summary` 不允许退化成源码复制

### 5.3 重试与去重
- 同指纹失败 2 次后必须切换工具或调整参数
- 不允许连续对同一意图使用错误工具试探
- 搜索命中过多时只能精细化，不能跳过定位直接盲读

## 6. `search_code` 的精细化策略

### 6.1 默认约束
- 默认 `max_results = 10`
- 超过 10 条命中时，必须自动精细化或给出明确收敛建议
- 不允许通过截断上下文窗口掩盖搜索过宽

### 6.2 精细化顺序
1. 限定 `directory`
2. 限定 `file_pattern`
3. 提高匹配表达式精度

### 6.3 结果输出规则
即使命中过多，`search_code` 也只能输出定位摘要，不得输出代码窗口。

## 7. 后端改造方案

### 7.1 工具实现
目标文件：`backend/app/services/agent/tools/file_tool.py`

改造内容：

- 保留旧 `FileReadTool` 仅作内部兼容，不再公开。
- 收缩 `FileSearchTool`：
  - 去掉上下文读取逻辑
  - 去掉 `sed` 窗口拼装
  - 去掉 `lines/window_start_line/window_end_line`
- 新增工具类：
  - `CodeWindowTool`
  - `FileOutlineTool`
  - `FunctionSummaryTool`
  - `SymbolBodyTool`

### 7.2 路由与参数归一化
目标文件：`backend/app/services/agent/mcp/router.py`

改造内容：

- 新增新工具路由：
  - `get_code_window`
  - `get_file_outline`
  - `get_function_summary`
  - `get_symbol_body`
- `search_code` 参数归一化保持纯定位语义
- `read_file` 仅留隐藏兼容，不再作为对外目录能力

### 7.3 Agent 执行入口
目标文件：`backend/app/api/v1/endpoints/agent_tasks.py`

改造内容：

- 新任务工具集新增原子工具
- 公共路径不再依赖 `read_file`
- 内部保留短期兼容别名，防止旧 prompt 立即失效

### 7.4 Skill 注册与测试台
目标文件：

- `backend/app/services/agent/skills/scan_core.py`
- `backend/app/services/agent/skill_test_runner.py`

改造内容：

- 删除 `read_file`
- 注册新工具
- 更新测试 allowlist
- 更新默认测试说明

### 7.5 Prompt 规范
目标文件：

- `backend/app/services/agent/prompts/system_prompts.py`
- 以及相关 agent prompt 文件

改造内容：

- 全量替换 `read_file` 使用说明
- 明确：
  - `search_code` 负责定位
  - `get_code_window` 负责取证
  - `get_function_summary` 负责函数理解
  - `get_file_outline` 负责文件理解

## 8. 前端改造方案

### 8.1 工具证据渲染
目标文件：`frontend/src/pages/AgentAudit/toolEvidence.ts`

改造内容：

- `search_code`
  - 渲染为纯命中列表
  - 不再渲染代码块
- `get_code_window`
  - 独占 `code_window`
- 新增 render type：
  - `outline_summary`
  - `function_summary`
  - `symbol_body`

### 8.2 工具目录与详情页
目标文件：`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`

改造内容：

- 删除 `read_file`
- 新增新工具条目
- 更新示例输入、注意事项、任务描述

### 8.3 历史兼容
- 旧 `read_file` 日志仍可展示
- 新任务不再显示 `read_file`

## 9. 实施阶段

### Phase 1：新增原子工具
- 新增后端工具类
- 前端新增 render type
- 更新 catalog 与 skill registry
- 新任务停止暴露 `read_file`

### Phase 2：切换 Agent 链路
- 修改 prompt
- 修改自动补救逻辑
- Skill test / intelligent / hybrid 全切新工具链

### Phase 3：删除 `read_file`
- 删除 builder、route、allowlist、核心逻辑
- 删除相关测试
- 保留前端历史兼容

## 10. 验收标准

### 10.1 功能标准
- 新任务中 `read_file` 调用数为 0
- `search_code` 输出中不再出现代码窗口字段
- `get_code_window` 成为唯一代码窗口来源
- 文件总体功能、函数功能、代码窗口分别由不同工具承担

### 10.2 工程标准
- 前后端类型定义统一
- 历史日志展示不报错
- skill test 能完整跑通新链路
- prompt 与运行时规则一致

### 10.3 效率标准
- 大窗口源码输出量明显下降
- 错误工具使用次数下降
- 从“首次定位”到“首次有效理解”的步数下降

## 11. 测试计划

### 11.1 单元测试
- `search_code`
  - 不返回 `lines/window_start_line/window_end_line`
  - 精细化逻辑正常
- `get_code_window`
  - 无锚点报错
  - 超大跨度报错
- `get_file_outline`
  - 只返回结构概览
- `get_function_summary`
  - 返回函数级语义
- `get_symbol_body`
  - 返回符号主体源码

### 11.2 集成测试
- Recon 不再依赖公开 `read_file`
- Analysis 走 `search_code -> get_code_window -> get_function_summary`
- Verification 代码证据全部来自 `get_code_window`

### 11.3 前端测试
- `search_code` 不再渲染代码块
- 新 render type 正常显示
- 历史 `read_file` 证据仍可看

## 12. 风险与注意事项

- 这次改动范围较大，必须前后端同步推进。
- 如果 `get_function_summary` 和 `get_file_outline` 结构不稳定，Agent 可能出现短期 prompt 偏移。
- 历史用例和测试文案中凡是提到 `read_file` 的地方都要系统替换，不能只改注册表。
- 当前代码库里仍存在大量旧 prompt/旧 agent 指令引用 `read_file`，若直接硬拔会造成链路瞬时失效。

## 13. 默认假设

- 本轮以边界清晰优先于渐进兼容。
- `read_file` 不再保留为新任务可用工具。
- `search_code` 永远不得再回流上下文窗口能力。
- 代码窗口型证据统一由 `get_code_window` 提供。

## 14. 详细执行 Plan 记录

### 14.1 当前已实施项
- 后端新增原子工具类与基础输出协议。
- `search_code` 收缩为纯定位输出。
- skill catalog、skill test runner、前端 catalog 已开始切换到新工具名。
- 前端证据协议新增 `outline_summary / function_summary / symbol_body`。

### 14.2 当前保留的过渡项
- 内部 `read_file` 兼容别名仍保留在部分 builder/router 中。
- `extract_function` 仍作为旧调用路径存在，但对外推荐改为 `get_symbol_body`。
- 旧 Agent prompt 尚需继续系统替换。

### 14.3 下一轮开发顺序
1. 清理 Agent prompt、system prompt、自动补救逻辑中的 `read_file` 叙述与 hardcode。
2. 将运行时约束从“提示规范”升级为“强校验阻断”。
3. 补齐 `search_code` 过宽结果时的自动二次收敛策略。
4. 移除内部 `read_file` 隐藏兼容入口。
5. 扩大前后端测试面并补齐历史用例迁移。

### 14.4 上会答辩要点
- 原子化后，工具边界可从系统层而不是 prompt 层约束。
- `search_code` 纯定位后，证据与理解被清晰拆分，前端渲染协议更稳定。
- `get_code_window` 作为唯一取证窗口，能够显著降低大段源码输出和盲读路径。
- `get_file_outline / get_function_summary / get_symbol_body` 分别对应文件理解、函数理解、源码提取，职责足够清晰，便于做 pre-hook/post-hook 治理。
