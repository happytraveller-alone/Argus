# 删除 MCP 部署与兼容壳层方案

## 概述

- 删除所有仍然把项目描述为“依赖外接 MCP”的 Docker、Compose、sandbox、backend、frontend 残留。
- 保留当前唯一仍然真实生效、但本质上并不是 MCP 的能力：写入范围约束和工具运行所需的可写 XDG 目录。
- 将仍需保留的运行时目录、配置项和文档命名迁移到中性语义，再删除已经成为空壳的 MCP bootstrap、catalog、probe 和前端占位接口。

## 对外接口与行为调整

### 运行时目录

- 将 backend 的 XDG 目录从 `/app/data/mcp/xdg-*` 迁移到 `/app/data/runtime/xdg-*`。
- 将开发态 compose 卷从 `mcp_data` 更名为 `backend_runtime_data`，挂载到 `/app/data/runtime`。
- 如 sandbox 仍需独立 XDG 目录，则同步改为 `/workspace/.VulHunter/runtime/xdg-*`。

### 后端环境变量

- 删除所有 repo 内自维护的 `MCP_*` 配置项。
- 将仍需保留的写入约束改为中性命名：
  - `AGENT_WRITE_SCOPE_HARD_LIMIT`
  - `AGENT_WRITE_SCOPE_DEFAULT_MAX_FILES`
  - `AGENT_WRITE_SCOPE_REQUIRE_EVIDENCE_BINDING`
  - `AGENT_WRITE_SCOPE_FORBID_PROJECT_WIDE_WRITES`

### 后端配置返回

- 不再生成任何 MCP 兼容占位字段，如 `mcpConfig`、`preferMcp`、`skillAvailability`、`deprecatedConfigs`。
- 继续保留对历史 `otherConfig.mcpConfig` 的单向清洗：
  - 读用户配置时去掉它
  - 写用户配置时忽略它

### 前端

- 删除未被使用的 MCP catalog 辅助模块，不再保留 `McpCatalogItem`、`DEFAULT_MCP_CATALOG` 等前端占位定义。

### 工具文档命名

- 将 `MCP_TOOL_PLAYBOOK.md` 重命名为 `TOOL_PLAYBOOK.md`。
- 所有同步 shared memory 的说明与日志文案改为中性“工具调用说明”，不再提 MCP。

## 实施变更

### 1. 容器与部署层清理

- 修改 [backend/Dockerfile](/home/xyf/AuditTool/backend/Dockerfile)
  - 删除 `/app/data/mcp` 及其 `xdg-*` 目录创建逻辑。
  - 改为仅创建 `/app/data/runtime/xdg-*`。
  - 删除 runtime 阶段对 `scripts/install_codex_skills.sh` 和 `scripts/build_skill_registry.py` 的复制。
- 修改 [docker-compose.yml](/home/xyf/AuditTool/docker-compose.yml)
  - 将 `mcp_data:/app/data/mcp` 改为 `backend_runtime_data:/app/data/runtime`。
  - 删除 `MCP_REQUIRE_ALL_READY_ON_STARTUP`、`CODEX_SKILLS_AUTO_INSTALL`、`SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP`、显式 `XDG_CONFIG_HOME` 注入。
  - 底部卷定义同步把 `mcp_data` 改名为 `backend_runtime_data`。
- 修改 [docker-compose.full.yml](/home/xyf/AuditTool/docker-compose.full.yml)
  - 做同样的卷迁移。
  - 删除 `MCP_REQUIRE_ALL_READY_ON_STARTUP`、`CODEX_SKILLS_AUTO_INSTALL`、显式 `XDG_CONFIG_HOME`。
- 修改 [docker/sandbox/Dockerfile](/home/xyf/AuditTool/docker/sandbox/Dockerfile)
  - 删除通过 Node/pnpm 安装的 `@modelcontextprotocol/server-memory`、`@modelcontextprotocol/server-sequential-thinking`、`@tobilu/qmd`。
  - 删除 `command -v qmd` 检查。
  - 删除 `/workspace/.VulHunter/mcp/*`、`/workspace/.VulHunter/qmd`、`QMD_DATA_DIR`。
  - 如仍需 sandbox XDG，则改到 `/workspace/.VulHunter/runtime/xdg-*`。
- 删除 [backend/scripts/install_codex_skills.sh](/home/xyf/AuditTool/backend/scripts/install_codex_skills.sh)。
- 删除 [backend/scripts/build_skill_registry.py](/home/xyf/AuditTool/backend/scripts/build_skill_registry.py)。
- 修改 [backend/docker-entrypoint.sh](/home/xyf/AuditTool/backend/docker-entrypoint.sh)
  - 删除 skills 自动安装与 skill registry 构建逻辑。

### 2. 后端运行时去 MCP 化

- 将 [backend/app/services/agent/mcp/write_scope.py](/home/xyf/AuditTool/backend/app/services/agent/mcp/write_scope.py) 提取到中性模块，例如 `app/services/agent/write_scope.py`。
- 将 [backend/app/api/v1/endpoints/agent_tasks_mcp.py](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_mcp.py) 替换为中性 helper 模块，例如 `agent_tasks_tool_runtime.py`。
  - 只保留写入范围守卫构建逻辑。
  - 只保留工具说明文档加载与 shared memory 同步逻辑。
- 修改 [backend/app/api/v1/endpoints/agent_tasks_execution.py](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_execution.py)
  - 删除 `_build_task_mcp_runtime`、`_bootstrap_task_mcp_runtime`、required MCP 门禁、probe、自检、MCP 初始化步骤文案。
  - 不再调用 `set_mcp_runtime(...)`。
  - 改为直接构建并下发 `set_write_scope_guard(...)`。
- 修改 [backend/app/services/agent/agents/base.py](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py)
  - 删除 MCP-first、MCP-strict、router/proxy、soft fallback 等执行分支。
  - 保留本地工具执行、写入范围校验、缓存、普通 fallback 逻辑。
- 删除无实际价值的 MCP 壳层模块：
  - `app/services/agent/mcp/runtime.py`
  - `app/services/agent/mcp/router.py`
  - `app/services/agent/mcp/catalog.py`
  - `app/services/agent/mcp/protocol_verify.py`
  - `app/services/agent/mcp/probe_specs.py`
  - `app/services/agent/mcp/virtual_tools.py`
  - `app/services/agent/mcp/__init__.py`
- 删除 [backend/pyproject.toml](/home/xyf/AuditTool/backend/pyproject.toml) 中的 `fastmcp` 依赖，并同步更新 lock 文件。

### 3. 配置与接口清理

- 修改 [backend/app/core/config.py](/home/xyf/AuditTool/backend/app/core/config.py)
  - 删除全部 `MCP_*` 字段和死配置 `XDG_CONFIG_HOME`。
  - 新增中性写入范围配置字段。
- 修改 [backend/app/api/v1/endpoints/config.py](/home/xyf/AuditTool/backend/app/api/v1/endpoints/config.py)
  - 删除 `_sanitize_mcp_config()` 及其相关返回结构。
  - 保留对历史 `mcpConfig` 的 strip 行为。
  - 将写入范围默认值与清洗逻辑迁移到中性命名。
- 删除 [frontend/src/pages/intelligent-scan/mcpCatalog.ts](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/mcpCatalog.ts)。

### 4. 文档与文案清理

- 将 [backend/docs/agent-tools/MCP_TOOL_PLAYBOOK.md](/home/xyf/AuditTool/backend/docs/agent-tools/MCP_TOOL_PLAYBOOK.md) 重命名为 `TOOL_PLAYBOOK.md`。
- 修改 [backend/scripts/generate_runtime_tool_docs.py](/home/xyf/AuditTool/backend/scripts/generate_runtime_tool_docs.py)
  - 输出文件名改为 `TOOL_PLAYBOOK.md`。
- 修改 [backend/app/api/v1/endpoints/agent_tasks_execution.py](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_execution.py)
  - shared memory 同步来源、summary、日志文案去掉 MCP 命名。
- 修改 [scripts/README-COMPOSE.md](/home/xyf/AuditTool/scripts/README-COMPOSE.md)
  - 更新对默认 compose 链路的说明，不再提 `MCP_REQUIRE_ALL_READY_ON_STARTUP`。
- 修改 [docs/agentic_scan_core/workflow_overview.md](/home/xyf/AuditTool/docs/agentic_scan_core/workflow_overview.md)
  - 将 “初始化 MCP 运行时” 改为中性的“初始化工具运行时/写入范围守卫”。

## 测试与回归验证

### 需要同步修改的测试

- [backend/tests/test_docker_compose_dev_flow.py](/home/xyf/AuditTool/backend/tests/test_docker_compose_dev_flow.py)
  - 更新 compose、Dockerfile、volume、env 断言。
- [backend/tests/test_mcp_catalog.py](/home/xyf/AuditTool/backend/tests/test_mcp_catalog.py)
  - 删除或改写为中性配置/兼容清理测试。
- [backend/tests/test_mcp_tool_routing.py](/home/xyf/AuditTool/backend/tests/test_mcp_tool_routing.py)
  - 删除 MCP router 相关断言，保留“已下线工具不可路由”或迁移到本地 tool registry 测试。
- [backend/tests/test_agent_task_mcp_bootstrap.py](/home/xyf/AuditTool/backend/tests/test_agent_task_mcp_bootstrap.py)
  - 改写为 tool runtime / write scope guard 初始化测试。
- [backend/tests/test_agent_tasks_module_layout.py](/home/xyf/AuditTool/backend/tests/test_agent_tasks_module_layout.py)
  - 去掉 `agent_tasks_mcp` 模块与 re-export 断言。
- [backend/tests/test_agent_task_project_root_normalization.py](/home/xyf/AuditTool/backend/tests/test_agent_task_project_root_normalization.py)
  - 将 `_build_task_mcp_runtime` 替换为新的中性 helper。

### 需要保留并继续通过的测试

- [backend/tests/test_config_mcp_backend_owned.py](/home/xyf/AuditTool/backend/tests/test_config_mcp_backend_owned.py)
  - 继续验证历史 `mcpConfig` 会被 strip。
- [backend/tests/test_agent_tool_registry.py](/home/xyf/AuditTool/backend/tests/test_agent_tool_registry.py)
  - 继续验证 `qmd_*`、`sequential_thinking` 等不在可用工具中。
- [backend/tests/test_agent_prompt_contracts.py](/home/xyf/AuditTool/backend/tests/test_agent_prompt_contracts.py)
  - 继续验证 prompt 不再提这些已删除能力。

### 建议执行的验证命令

全部使用仓库约定的 `uv run --project .`：

```bash
uv run --project . pytest -s tests/test_docker_compose_dev_flow.py
uv run --project . pytest -s tests/test_config_mcp_backend_owned.py
uv run --project . pytest -s tests/test_agent_tool_registry.py tests/test_agent_prompt_contracts.py
```

并补充一个新的聚焦测试：

- 验证 agent task 执行时，仍会注入 write-scope guard，但不再构建任何 MCP runtime 对象。

## 已知事项

- [backend/tests/test_legacy_cleanup.py](/home/xyf/AuditTool/backend/tests/test_legacy_cleanup.py) 当前已存在与本次变更无关的失败：`app.services.agent.skills.__all__` 不为空。这个问题需要在本轮同步修正或单独调整测试预期。
- 使用 `pytest -q` 在当前环境下可能出现 capture 清理异常，`-s` 更稳定，适合作为本轮验证方式。

## 默认假设

- 仓库外部没有仍然依赖旧 `MCP_*` 环境变量、sandbox 中 `qmd` 命令、或 backend 镜像里 skills/registry 启动脚本的部署链路。
- 需要保留的只有“本地工具执行 + 基于证据的写入范围约束”，而不是任何 MCP transport、catalog、probe 或 adapter 能力。
- 本方案采用以下中性默认值：
  - backend XDG 根目录：`/app/data/runtime`
  - compose 卷名：`backend_runtime_data`
  - sandbox XDG 根目录：`/workspace/.VulHunter/runtime`
  - 工具文档文件名：`TOOL_PLAYBOOK.md`
