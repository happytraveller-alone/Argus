# Remaining Python Function Inventory

> 最后更新：2026-04-23

## 统计

- `backend_old/app/services/agent/` 源文件（不含 `__init__.py`）：**66**
- `backend_old/scripts/` Python 脚本：**1**（`flow_parser_runner.py`）
- `backend_old/tests/` 测试文件：**~80**

## 当前主线优先级（ACP + Rust runtime）

当前不是按全目录平均推进，而是优先服务 `agent_tasks` runtime 真接管。

一阶 blocker：

1. `task_models.py`
2. `event_manager.py`
3. `streaming/*.py`
4. `core/state.py`
5. `core/executor.py`
6. `agents/base.py`
7. `tools/runtime/*.py`
8. `tools/queue_tools.py` / `tools/recon_queue_tools.py`

二阶依赖：

1. `tools/file_tool.py`
2. `tools/code_analysis_tool.py`
3. `tools/control_flow_tool.py`
4. `tools/pattern_tool.py`
5. `core/flow/lightweight/*`

这份 inventory 仍是完整文件面清单，但执行顺序以 [.omx/plans/prd-acp-rust-runtime-agent-tasks.md](/home/xyf/audittool_personal/.omx/plans/prd-acp-rust-runtime-agent-tasks.md) 为准。

## 按功能域分类

### 1. Agent 框架核心（9 个文件）

| 文件 | 职责 |
|------|------|
| `agents/base.py` | BaseAgent + AgentConfig + AgentResult + AgentType + AgentPattern |
| `agents/react_parser.py` | ReAct Thought/Action/Observation 解析 |
| `core/context.py` | Agent 执行上下文 |
| `core/errors.py` | Agent 错误类型 |
| `core/executor.py` | Agent 执行器 |
| `core/registry.py` | Agent 注册表 |
| `core/state.py` | Agent 状态管理 |
| `core/logging.py` | Agent 日志 |
| `core/message.py` | Agent 消息 |

### 2. Agent 类型实现（7 个文件）

| 文件 | Agent | 职责 |
|------|-------|------|
| `agents/orchestrator.py` | OrchestratorAgent | 编排调度、TODO 模式、多轮循环 |
| `agents/analysis.py` | AnalysisAgent | 代码审计、漏洞候选发现 |
| `agents/recon.py` | ReconAgent | 项目结构探索、风险点队列 |
| `agents/verification.py` | VerificationAgent | 动态验证、PoC、verdict |
| `agents/report.py` | ReportAgent | 结构化漏洞报告 |
| `agents/verification_table.py` | — | 验证表辅助 |

### 3. 工具系统（15 个文件）

| 文件 | 工具数 | 说明 |
|------|--------|------|
| `tools/base.py` | 2 | AgentTool 基类 + ToolResult |
| `tools/agent_tools.py` | 7 | Agent 协作（CreateSubAgent/SendMessage/RunSubAgents 等） |
| `tools/code_analysis_tool.py` | 3 | CodeAnalysis + DataFlow + VulnerabilityValidation |
| `tools/control_flow_tool.py` | 1 | ControlFlowAnalysisLight |
| `tools/evidence_protocol.py` | — | 证据协议 |
| `tools/file_tool.py` | 8 | FileRead/Search/CodeWindow/Outline/Summary/SymbolBody/ListFiles/LocateFunction |
| `tools/finish_tool.py` | 1 | FinishScan |
| `tools/pattern_tool.py` | 1 | PatternMatch |
| `tools/queue_tools.py` | 4 | GetQueueStatus/Dequeue/IsInQueue/PushFinding |
| `tools/recon_file_tree_tool.py` | 1 | UpdateReconFileTree |
| `tools/recon_queue_tools.py` | 7 | ReconRiskQueue 全套操作 |
| `tools/reporting_tool.py` | 1 | CreateVulnerabilityReport |
| `tools/run_code.py` | 2 | RunCode + ExtractFunction |
| `tools/sandbox_tool.py` | 1 | SandboxTool（+ SandboxManager/SandboxConfig） |
| `tools/sandbox_runner_client.py` | — | Rust runner subprocess bridge |
| `tools/verification_result_tools.py` | 2 | SaveVerificationResult + UpdateVulnerabilityFinding |

### 4. 工具运行时协调（4 个文件）

| 文件 | 职责 |
|------|------|
| `tools/runtime/context.py` | 运行时上下文 |
| `tools/runtime/contracts.py` | 运行时契约 |
| `tools/runtime/coordinator.py` | 运行时协调器 |
| `tools/runtime/hooks.py` | 运行时钩子 |

### 5. 流分析 / AST（11 个文件）

| 文件 | 职责 | Rust Bridge |
|------|------|-------------|
| `core/flow/models.py` | 流模型 | — |
| `core/flow/pipeline.py` | 流 pipeline | — |
| `core/flow/lightweight/ast_index.py` | AST 索引 | — |
| `core/flow/lightweight/callgraph_code2flow.py` | 调用图 | code2flow |
| `core/flow/lightweight/definition_provider.py` | 定义提供者 | — |
| `core/flow/lightweight/flow_parser_runtime.py` | Flow Parser Bridge | flow-parser |
| `core/flow/lightweight/function_locator.py` | 函数定位器 | — |
| `core/flow/lightweight/function_locator_cli.py` | 函数定位器 CLI | — |
| `core/flow/lightweight/function_locator_payload.py` | 函数定位器 payload | — |
| `core/flow/lightweight/path_scorer.py` | 路径评分器 | — |
| `core/flow/lightweight/tree_sitter_parser.py` | Tree-sitter 解析器 | — |

### 6. 其他独立模块（20 个文件）

| 文件 | 职责 | Rust Bridge |
|------|------|-------------|
| `config.py` | Agent 配置 | — |
| `event_manager.py` | 事件管理器 | — |
| `finding_payload_runtime.py` | Finding Payload Bridge | finding-payload |
| `json_parser.py` | JSON 解析 | — |
| `json_safe.py` | JSON 安全序列化 | — |
| `logic/authz_graph_builder.py` | 授权图构建 | — |
| `logic/authz_rules.py` | 授权规则引擎 | — |
| `memory/markdown_memory.py` | Markdown 记忆存储 | — |
| `orm_base.py` | ORM 基类 | — |
| `prompts/system_prompts.py` | 系统提示词 | — |
| `runtime_settings.py` | 运行时设置 | — |
| `skills/scan_core.py` | 扫描核心 skill 目录 | — |
| `streaming/stream_handler.py` | 流处理器 | — |
| `streaming/token_streamer.py` | Token 流 | — |
| `streaming/tool_stream.py` | 工具流 | — |
| `task_findings.py` | 任务 findings 管理 | scan-scope |
| `task_models.py` | AgentTask 模型 | — |
| `utils/vulnerability_naming.py` | 漏洞命名 | — |
| `verification_dataflow.py` | 验证数据流常量 | — |
| `write_scope.py` | 写入范围控制 | — |

### 7. Scripts（1 个文件）

| 文件 | 职责 | 状态 |
|------|------|------|
| `scripts/flow_parser_runner.py` | Flow Parser 脚本宿主 | 活跃，Docker 构建 + function_locator 引用 |

## 已删除功能域汇总

| 功能域 | 文件数 | 删除时间 |
|--------|--------|----------|
| 知识库（knowledge/） | 17 | 2026-04-22 |
| 外部扫描引擎（external_tools.py） | 1 | 2026-04-22 |
| 智能审计（smart_scan_tool.py） | 1 | 2026-04-22 |
| 沙箱语言工具（sandbox_language.py） | 1 | 2026-04-22 |
| 漏洞专项沙箱（sandbox_vuln.py） | 1 | 2026-04-22 |
| 昆仑引擎（kunlun_tool.py） | 1 | 2026-04-22 |
| 授权逻辑工具（logic_authz_tool.py） | 1 | 2026-04-22 |
| sandbox_tool.py 非通用工具 | 4 类 | 2026-04-22 |
| retired 守卫测试 | 34 | 2026-04-22 |
| 废弃测试文件 | 5 | 2026-04-22 |
| chat2rule 模块 | 1 | 2026-04-22 |
| runner_preflight.py | 1 | 已删除（早于本轮） |
