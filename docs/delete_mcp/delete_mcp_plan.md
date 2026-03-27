# Delete MCP/RAG 清理实施计划

## Summary

- 本计划已合并前端、后端、部署视角的审阅结论，目标是一次性清理仓库中所有已退役的 `mcp*`、`MCP_*`、`rag*`、Embedding 命名、运行时分支、兼容字段与界面文案。
- 本次采用破坏式清理策略：
  - 后端不再产出任何 `metadata.mcp_*`、`mcp_*` 错误分类、`mcp_*` shared memory source、`MCP`/`RAG` 用户可见文案。
  - 不保留双写或 UI-only 兼容层。
- 当前主要部署形态按“源码 compose”处理；因此部署 runbook 以 `docker compose` 为准，不以 artifact 部署链为默认前提。
- 本轮只更新当前活文档和开发文档；历史设计/规划文档不做全仓同步改写。
- 在开始代码修改前，必须先修正文档中的 4 个错误前提：
  - live 启动入口是 `backend/app/runtime/container_startup.py`，不是 `backend/docker-entrypoint.sh`
  - `agent_tasks_execution.py` 与 `agent_tasks_mcp.py` 各自都维护了一份 tool playbook / skills memory helper，必须先统一归属
  - `config.py` 里的 `_sanitize_mcp_config()` 当前并不参与 `/config/me` 响应，只是被测试引用
  - `install_codex_skills.sh` 不是当前源码 compose 主链的 live 执行路径，不能按“现行关键启动步骤”处理

## Important Interface Changes

- 配置项统一改名为中性写入范围命名：
  - `AGENT_WRITE_SCOPE_HARD_LIMIT`
  - `AGENT_WRITE_SCOPE_DEFAULT_MAX_FILES`
  - `AGENT_WRITE_SCOPE_REQUIRE_EVIDENCE_BINDING`
  - `AGENT_WRITE_SCOPE_FORBID_PROJECT_WIDE_WRITES`
- 删除公开接口 `/embedding/*`。
- 删除以下可见或可消费的旧字段/事件/命名：
  - `metadata.mcp_*`
  - `source="mcp_tool_playbook_sync"`
  - `title="MCP 工具说明同步"`
  - `retry_error_class="mcp_runtime_error"`
  - `mcp_error` / `mcp_error_class`
  - `AgentEventType.RAG_QUERY`
  - `AgentEventType.RAG_RESULT`
- 前端审计分类统一改为中性命名：
  - `TerminalFailureClass: "runtime"` 取代 `"mcp"`
- 文档生成物统一改名：
  - `backend/docs/agent-tools/MCP_TOOL_PLAYBOOK.md` 改为 `TOOL_PLAYBOOK.md`

## Implementation Changes

### 1. 先统一模块归属，再删旧模块

- 新建 `backend/app/api/v1/endpoints/agent_tasks_tool_runtime.py`，作为唯一 owner，承接：
  - write-scope guard 构建
  - `TOOL_SHARED_CATALOG.md` 同步
  - `TOOL_PLAYBOOK.md` 读取与 shared memory 同步
  - tool skills snapshot 构建与 skills memory 同步
- 新建 `backend/app/services/agent/write_scope.py`，迁出：
  - `TaskWriteScopeGuard`
  - `WriteScopeDecision`
  - `HARD_MAX_WRITABLE_FILES_PER_TASK`
- 先把所有导入改到新模块，再删除：
  - `backend/app/api/v1/endpoints/agent_tasks_mcp.py`
  - `backend/app/services/agent/mcp/write_scope.py`
- 同步更新 facade 与布局测试：
  - `backend/app/api/v1/endpoints/agent_tasks.py`
  - `backend/tests/test_agent_tasks_module_layout.py`

### 2. 一次性移除 MCP runtime 体系

- 删除：
  - `backend/app/services/agent/mcp/runtime.py`
  - `router.py`
  - `catalog.py`
  - `protocol_verify.py`
  - `probe_specs.py`
  - `virtual_tools.py`
  - `__init__.py`
- `backend/app/api/v1/endpoints/agent_tasks_execution.py` 删除：
  - `_build_task_mcp_runtime`
  - `_bootstrap_task_mcp_runtime`
  - `_probe_required_mcp_runtime`
  - “正在初始化 MCP 运行时”及 gate/probe 步骤
  - `set_mcp_runtime(...)`
- 启动链改为只做：
  - `_initialize_tools(...)`
  - write-scope guard 注入
  - tool docs / skills memory sync
- `backend/app/services/agent/agents/base.py` 改为仅支持本地工具执行 + write-scope guard：
  - 删除 `_mcp_runtime`
  - 删除 strict MCP routing / proxy fallback / adapter 选择
  - 删除 `mcp_*` metadata 拼装
  - 删除 `mcp_unavailable` 分类
  - 新增 `set_write_scope_guard(...)`
  - 所有失败 metadata 改为中性 runtime 命名
- `backend/app/services/agent/agents/orchestrator.py`、system prompts、`TOOL_USAGE_GUIDE` 删除 “MCP 工具链” 表述，统一为“标准工具链”或“本地工具链”

### 3. 修正 runtime 错误分类与 verification 命名

- `backend/app/api/v1/endpoints/agent_tasks_runtime.py`
  - `code: "mcp_runtime_error"` 改为 `tool_runtime_error`
  - `category: "mcp"` 改为 `runtime`
- `backend/app/services/agent/agents/base.py`
  - `mcp_error` / `mcp_error_class` 改为 `runtime_error` / `runtime_error_class`
  - `mcp_unavailable` 改为 `tool_unavailable`
- `backend/app/services/agent/agents/verification.py`
  - `_mcp_attempt` 改为 `_function_locator_attempt`
  - `function_resolution_method` / `function_resolution_engine` 从 `mcp_symbol_index` 改为中性值
  - 日志文本与 fallback 统一去掉 `MCP`
- 所有依赖旧错误名的测试同步改为中性断言：
  - `backend/tests/test_agent_tool_retry_guard.py`
  - `backend/tests/test_agent_scan_mode_coverage_diagnostics.py`
  - `backend/tests/test_verification_function_locator_fallback.py`

### 4. 清掉死兼容代码和相关测试

- `backend/app/api/v1/endpoints/config.py`
  - 删除 `_default_mcp_write_policy()`
  - 删除 `_sanitize_mcp_write_policy()`
  - 删除 `_sanitize_mcp_config()`
  - 保留且仅保留 `otherConfig.mcpConfig` 的 strip 行为
- 说明：
  - `/config/me` 与默认配置不新增中性 write-scope 返回字段
  - write-scope 继续由服务端设置控制，不经用户配置下发
- 删除或重写这些测试：
  - `backend/tests/test_mcp_catalog.py`
  - `backend/tests/test_mcp_write_scope_guard.py`
  - `backend/tests/test_agent_task_mcp_bootstrap.py`
  - `backend/tests/test_mcp_tool_routing.py`
  - `backend/tests/test_mcp_all_agents_write_policy.py`
  - `backend/tests/test_mcp_router_codebadger_cpg_query.py`

### 5. 移除 RAG / Embedding，但保留 tree-sitter 能力

- 新建中性 parser 模块，迁出 `TreeSitterParser`
- 修改调用方：
  - `backend/app/services/flow_parser_runtime.py`
  - `backend/app/services/agent/flow/lightweight/ast_index.py`
  - `backend/app/services/agent/flow/lightweight/function_locator.py`
- 删除：
  - `backend/app/services/rag/embeddings.py`
  - `indexer.py`
  - `retriever.py`
  - `__init__.py`
  - `backend/app/services/agent/tools/rag_tool.py`
  - `backend/app/services/agent/knowledge/rag_knowledge.py`
- `backend/app/services/agent/knowledge/tools.py` 删除知识库检索工具入口
- `backend/app/services/agent/config.py` 删除 `rag_enabled` / `rag_top_k`
- `backend/app/models/agent_task.py` 与 `backend/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py` 删除 `RAG_QUERY` / `RAG_RESULT`
- `backend/scripts/create_agent_demo_data.py` 删除 `rag_index` / `rag_search` / `RAG_*` 演示数据
- 删除 `backend/app/api/v1/endpoints/embedding_config.py`
- `backend/app/api/v1/api.py` 删除 embedding router 注册

### 6. 前端做一轮完整中性化

- 删除：
  - `frontend/src/components/agent/EmbeddingConfig.tsx`
  - `frontend/src/pages/intelligent-scan/mcpCatalog.ts`
- `frontend/src/components/system/SystemConfig.tsx`
  - 删除 `embedding` section
  - 删除 `ConfigSection` 中的 `"embedding"`
  - 删除对应 tab、import、默认 section 数组中的 embedding
- `frontend/src/pages/ScanConfigIntelligentEngine.tsx`
  - 删除注释残留“搜索增强模块”
- `frontend/src/components/agent/AgentModeSelector.tsx`
  - 删除所有 `RAG` 文案
  - 智能扫描说明改为“跨文件关联 + 结构化代码分析”等中性表述
- `frontend/src/pages/AgentAudit/types.ts`
  - `TerminalFailureClass` 中 `'mcp'` 改为 `'runtime'`
- `frontend/src/pages/AgentAudit/TaskDetailPage.tsx`
  - 删除 `（MCP: ...）`
  - 删除 `MCP 路由：...`
  - 失败分类改为识别中性 runtime 错误
- `frontend/src/pages/AgentAudit/toolEvidence.ts`
  - fallback command chain 不再注入 `mcp_adapter`
- `frontend/src/pages/AgentAudit/components/AuditDetailDialog.tsx`
  - 保留显示原始 detail 的能力，但依赖后端不再下发旧字段
- 更新前端测试与 fixture，确保任何可见文本都不再出现 `MCP` / `RAG`

### 7. 工具文档、skills snapshot、提示词生成链统一改名

- `backend/docs/agent-tools/MCP_TOOL_PLAYBOOK.md` 改为 `TOOL_PLAYBOOK.md`
- `backend/scripts/generate_runtime_tool_docs.py`
  - `PLAYBOOK_PATH` 指向新文件名
  - 删除 `rag_query` 与退役知识库工具叙述
  - 标题与说明全部改为中性工具文档命名
- `backend/scripts/validate_runtime_tool_docs.py` 同步新文件名
- `backend/tests/test_runtime_tool_docs_coverage.py`
  - 改断言到 `TOOL_PLAYBOOK.md`
- `backend/tests/test_tool_skills_memory_sync.py`
  - 不再断言 `MCP 工具说明同步`
  - 改断言中性标题与 source
- `backend/app/services/agent/skills/scan_core.py`
  - 删除空壳 `SCAN_CORE_MCP_BOUND_SKILL_IDS`
  - 删除相关 `*_MCP_*` 命名
- 提示词合同测试继续要求 scan-core 工具集合不变，但不得再出现 retired alias

### 8. 部署与容器修改按真实 live 入口执行

- `backend/app/runtime/container_startup.py`
  - 删除 `_run_optional_skill_setup()`
  - 删除对 `install_codex_skills.sh` / `build_skill_registry.py` 的调用
- `backend/Dockerfile`
  - `dev-runtime` 和 `runtime` 都改为创建 `/app/data/runtime/xdg-*`
  - 删除 `/app/data/mcp`
  - 删除旧 `XDG_*=/app/data/mcp/xdg-*`
  - `runtime` 删除 `COPY scripts/build_skill_registry.py`
- `docker-compose.yml` 与 `docker-compose.full.yml`
  - `mcp_data:/app/data/mcp` 改为 `backend_runtime_data:/app/data/runtime`
  - 删除 `MCP_*`
  - 删除 `XDG_CONFIG_HOME=/app/data/mcp/xdg-config`
  - 删除 `CODEX_SKILLS_*`
  - 删除 `SKILL_REGISTRY_*`
- `backend/.env` 与 `backend/env.example`
  - 删除 `MCP_*`
  - 删除 `XDG_CONFIG_HOME`
  - 删除 `EMBEDDING_*`
  - 删除 `VECTOR_DB_TYPE` / `CHROMA_*`
  - 新增中性 `AGENT_WRITE_SCOPE_*`
- `docker/sandbox/Dockerfile`
  - 删除 `@modelcontextprotocol/*`
  - 删除 `@tobilu/qmd`
  - 删除 `QMD_DATA_DIR`
  - 路径统一为 `/workspace/.VulHunter/runtime/xdg-*`
- `backend/docker-entrypoint.sh`、`backend/scripts/install_codex_skills.sh`、`backend/scripts/build_skill_registry.py`
  - 作为死文件清理
  - 不再当作 live 启动逻辑的一部分

### 9. 源码 compose 卷迁移 runbook

- 默认旧卷为 named volume `mcp_data`
- 迁移步骤固定写入文档：
  - 停止 `backend`
  - 备份旧 `mcp_data`
  - 列出旧卷目录树
  - 仅迁移 `xdg-data` / `xdg-cache` / `xdg-config`
  - 不迁移 `skill-registry` / `codex-home` / `qmd`
  - 创建并切换到 `backend_runtime_data`
  - 启动 compose
  - 校验新挂载、env、健康状态
  - 若失败，回滚到旧 compose 和旧卷名
- 不默认假设 bind mount、外部卷驱动或 artifact 部署链

### 10. 文档更新范围

- 更新：
  - `docs/delete_mcp/delete_mcp_plan.md`
  - `docs/agentic_scan_core/workflow_overview.md`
  - `docs/architecture.md`
  - `scripts/README-COMPOSE.md`
- 不改历史设计文档；如需引用，标注“历史设计，不代表当前实现”

## Test Plan

- 后端必须验证：
  - `/config` 仍只 strip `otherConfig.mcpConfig`
  - `agent task` 启动链不再构建 runtime 对象，只注入 write-scope guard
  - `BaseAgent` 不再产生任何 `mcp_*` metadata
  - `VerificationAgent` 使用中性函数定位命名
  - `TOOL_PLAYBOOK.md`、skills snapshot、prompt contracts 无旧别名
  - 删除 `fastmcp` 后，所有依赖 stub `fastmcp` 的测试同步收敛或删除
- 前端必须验证：
  - AgentAudit 列表、详情、导出文本不再出现 `MCP:` / `MCP 路由：`
  - 终态分类显示 `runtime`
  - `AgentModeSelector` 无 `RAG`
  - `SystemConfig` 任意 visibleSections 下都不再含 embedding section
- 源码 compose smoke 必做：
  - `docker compose config` 不再含 `mcp_data`、`MCP_*`、旧 `XDG_CONFIG_HOME`
  - backend 容器内 `env` 只出现新 `XDG_*`
  - backend `/health`
  - 跑一次真实 agent 任务，验证：
    - 日志无 `MCP`
    - shared memory 无旧 source
    - sandbox 任务可执行
- 建议命令：
  - `uv run --project . pytest -s backend/tests/test_config_mcp_backend_owned.py backend/tests/test_agent_tasks_module_layout.py backend/tests/test_runtime_tool_docs_coverage.py backend/tests/test_tool_skills_memory_sync.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_agent_tool_input_repair.py`
  - `pnpm test:node -- frontend/tests/agentAuditLogEntry.test.tsx`
  - `docker compose up --build -d`
  - `docker compose exec backend env | rg 'MCP_|XDG_|CODEX_SKILLS|SKILL_REGISTRY'`
  - `docker compose exec backend env | rg '/app/data/runtime|/app/data/mcp'`

## Assumptions

- 兼容策略已确定为“直接移除旧字段”，不保留双写或 UI-only 兼容层。
- 文档范围已确定为“只改当前活文档”。
- 部署形态已确定为“源码 compose”。
- 卷迁移按 named volume `mcp_data -> backend_runtime_data` 编写。
- `skill-registry`、`codex-home`、`qmd` 视为历史残留，不做迁移目标。
- subagent 审阅已完成并收口，本计划为完整替换版。
