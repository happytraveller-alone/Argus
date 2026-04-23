# Current State And Ledger

> 最后更新：2026-04-23

## 总览

| 指标 | 数值 |
|------|------|
| Python 源文件（`backend_old/app`，不含 `__init__.py`） | 66 |
| Python `__init__.py`（全部为空壳） | 0 个非空 |
| Python 脚本（`backend_old/scripts`） | 1（`flow_parser_runner.py`） |
| Python 测试文件（`backend_old/tests`） | ~80 |
| Rust 源文件（`backend/src`） | 46 |
| Rust 集成测试（`backend/tests`） | 12 |

## Rust 已完全接管的功能域

### HTTP API 路由（7 个 router，100% Rust）

| Router | 路径前缀 | 主要端点数 |
|--------|----------|-----------|
| `agent_tasks` | `/api/v1/agent-tasks` | 16（CRUD + stream + findings + report；route Rust-owned，但 runtime 仍未真接管） |
| `agent_test` | `/api/v1/agent-test` | 6（recon/analysis/verification/business-logic） |
| `projects` | `/api/v1/projects` | 27（CRUD + zip + files + cache + dashboard + export） |
| `search` | `/api/v1/search` | 4（global + projects + tasks + findings） |
| `skills` | `/api/v1/skills` | 8（catalog + CRUD + detail + test） |
| `static_tasks` | `/api/v1/static-tasks` | 20+（rules CRUD + tasks + findings + cache） |
| `system_config` | `/api/v1/system-config` | 7（defaults + CRUD + test-llm + models + preflight） |
| `health` | `/health` | 1 |

### 基础设施层（100% Rust）

- DB 层：projects, prompt_skills, scan_rule_assets, system_config, task_state
- Bootstrap/启动：dev/prod 模式、env 同步、DB 等待、optional resets
- LLM：config, providers, tokenizer, compression, prompt_cache, runtime
- Core：encryption, security, date_utils
- Scan：opengrep, path_utils, scope_filters

### Agent Task Runtime 当前状态

- `agent_tasks`、`skills`、`task_state` 的外部 surface 已由 Rust 持有。
- 当前 `start_agent_task` 仍会直接把任务推进到 terminal，并 seeded findings / tree / checkpoints / report。
- 当前 `/stream` 主要回放已存事件，不是实时反映真实 Rust runtime 执行。
- 当前 Phase E 主线已改为：在 Rust 内部引入 ACP-aligned runtime + 本地 ACP adapter boundary，用它替换 synthetic runtime。
- ACP 官方 Rust SDK 已存在，但本路线图要求它先作为内部 runtime 建模输入，不直接替换当前前端 contract。

### Runtime 计算内核（Rust 实现，Python 通过 subprocess bridge 调用）

| 子命令 | Rust 模块 | Python Bridge |
|--------|-----------|---------------|
| `runner execute/stop` | `runtime/runner.rs` | `sandbox_runner_client.py` |
| `code2flow` | `runtime/code2flow.rs` | `callgraph_code2flow.py` |
| `flow-parser` | `runtime/flow_parser.rs` | `flow_parser_runtime.py` |
| `scan-scope` | `scan/scope_filters.rs` | `task_findings.py`（部分） |
| `finding-payload normalize` | `runtime/finding_payload.rs` | `finding_payload_runtime.py` |
| `queue` | `runtime/queue.rs` | `queue_tools.py` / `recon_queue_tools.py` |
| `sandbox` | `runtime/sandbox.rs` | `sandbox_tool.py` |

## Python 仍为唯一实现的功能域（66 个文件）

### Agent 框架（8 个文件）

- `agents/base.py` — BaseAgent 基类 + AgentConfig/AgentResult/AgentType
- `agents/react_parser.py` — ReAct 输出解析器
- `core/context.py` — Agent 上下文
- `core/errors.py` — Agent 错误类型
- `core/executor.py` — Agent 执行器
- `core/registry.py` — Agent 注册表
- `core/state.py` — Agent 状态管理
- `core/logging.py` — Agent 日志
- `core/message.py` — Agent 消息

### Agent 类型实现（7 个文件）

- `agents/analysis.py` — AnalysisAgent
- `agents/orchestrator.py` — OrchestratorAgent
- `agents/recon.py` — ReconAgent
- `agents/report.py` — ReportAgent
- `agents/verification.py` — VerificationAgent
- `agents/verification_table.py` — 验证表

### 工具系统（14 个文件）

- `tools/base.py` — AgentTool 基类 + ToolResult
- `tools/agent_tools.py` — 7 个 Agent 协作工具
- `tools/code_analysis_tool.py` — 代码分析 + 数据流 + 漏洞验证
- `tools/control_flow_tool.py` — 控制流分析
- `tools/evidence_protocol.py` — 证据协议
- `tools/file_tool.py` — 8 个文件操作工具
- `tools/finish_tool.py` — 扫描完成
- `tools/pattern_tool.py` — 模式匹配
- `tools/queue_tools.py` — 4 个队列工具（调用 Rust queue）
- `tools/recon_file_tree_tool.py` — 侦察文件树
- `tools/recon_queue_tools.py` — 8 个侦察队列工具
- `tools/reporting_tool.py` — 漏洞报告生成
- `tools/run_code.py` — 代码运行 + 函数提取
- `tools/sandbox_tool.py` — SandboxManager + SandboxConfig + SandboxTool
- `tools/sandbox_runner_client.py` — 沙箱 Runner 客户端（调用 Rust runner）
- `tools/verification_result_tools.py` — 验证结果保存/更新

### 工具运行时协调（4 个文件）

- `tools/runtime/context.py`
- `tools/runtime/contracts.py`
- `tools/runtime/coordinator.py`
- `tools/runtime/hooks.py`

### 流分析 / AST（11 个文件）

- `core/flow/models.py` — 流模型
- `core/flow/pipeline.py` — 流 pipeline
- `core/flow/lightweight/ast_index.py` — AST 索引
- `core/flow/lightweight/callgraph_code2flow.py` — 调用图（调用 Rust code2flow）
- `core/flow/lightweight/definition_provider.py` — 定义提供者
- `core/flow/lightweight/flow_parser_runtime.py` — Flow Parser Bridge（调用 Rust）
- `core/flow/lightweight/function_locator.py` — 函数定位器
- `core/flow/lightweight/function_locator_cli.py` — 函数定位器 CLI
- `core/flow/lightweight/function_locator_payload.py` — 函数定位器 payload
- `core/flow/lightweight/path_scorer.py` — 路径评分器
- `core/flow/lightweight/tree_sitter_parser.py` — Tree-sitter 解析器

### 其他独立模块（16 个文件）

- `config.py` — Agent 配置
- `event_manager.py` — 事件管理器
- `finding_payload_runtime.py` — Finding Payload Bridge（调用 Rust）
- `json_parser.py` — JSON 解析
- `json_safe.py` — JSON 安全序列化
- `logic/authz_graph_builder.py` — 授权图构建
- `logic/authz_rules.py` — 授权规则引擎
- `memory/markdown_memory.py` — Markdown 记忆存储
- `orm_base.py` — ORM 基类
- `prompts/system_prompts.py` — 系统提示词
- `runtime_settings.py` — 运行时设置（含 Rust binary 路径配置）
- `skills/scan_core.py` — 扫描核心 skill 目录
- `streaming/stream_handler.py` — 流处理器
- `streaming/token_streamer.py` — Token 流
- `streaming/tool_stream.py` — 工具流
- `task_findings.py` — 任务 findings 管理（含 scope filter bridge）
- `task_models.py` — AgentTask / AgentTaskPhase / AgentTaskStatus
- `utils/vulnerability_naming.py` — 漏洞命名
- `verification_dataflow.py` — 验证数据流常量
- `write_scope.py` — 写入范围控制

## 已删除的功能域（本轮清理）

- 知识库（`knowledge/`）：17 个文件（base + loader + rag + 6 frameworks + 12 vulnerabilities）
- 外部扫描引擎工具（`external_tools.py`）：Opengrep/NpmAudit/Safety/TruffleHog/OSVScanner
- 智能审计工具（`smart_scan_tool.py`）：SmartScanTool + QuickAuditTool
- 沙箱语言工具（`sandbox_language.py`）：8 个语言测试工具 + UniversalCodeTestTool
- 漏洞专项沙箱（`sandbox_vuln.py`）：7 个漏洞类型测试工具
- 昆仑引擎（`kunlun_tool.py`）：3 个昆仑工具
- 授权逻辑工具（`logic_authz_tool.py`）：LogicAuthzAnalysisTool
- sandbox_tool.py 中的非通用工具：SandboxHttpTool/VulnerabilityVerifyTool/PhpTestTool/CommandInjectionTestTool
- 34 个 `_retired` 守卫测试 + 5 个废弃测试文件 + chat2rule 模块

## Scripts 遗留

| 文件 | 状态 |
|------|------|
| `scripts/flow_parser_runner.py` | 活跃，被 `function_locator.py` 和 Docker 构建引用 |
| `scripts/dev-entrypoint.sh` | 活跃，开发环境入口 |
| `scripts/release-templates/runner_preflight.py` | 已删除 |
