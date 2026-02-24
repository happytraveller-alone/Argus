# 智能审计 MCP 稳定性修复 + QMD 持久化集成方案

## 摘要
1. 修复 `read_file` / `list_files` / `search_code` 在审计启动阶段“先 MCP 失败再本地回退”的逻辑噪音与误失败感知。  
2. 对所有 MCP 适配器统一加“可用性预检 + 失败熔断 + 回退收敛”，避免同类 bug 在 `filesystem/code_index/memory/sequential/qmd` 重复出现。  
3. 新增 `qmd` 作为 MCP 检索能力，所有 Agent 可用，采用“镜像内安装 + 持久目录 + 懒加载索引”策略，后端与沙箱均支持持久化。  

## 已确认决策
1. `qmd` 索引策略：`懒加载索引`（首次使用时建集合/更新）。  
2. `qmd` 部署方式：`backend/sandbox 镜像内安装 + 持久目录`。  

## 根因结论（基于日志与代码）
1. `/Users/apple/Desktop/agent_audit_logs_error.json` 显示 `mcp_call_failed: [Errno 2] No such file or directory`，随后本地工具成功。  
2. `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py` 中 `can_handle()` 仅按“路由存在”判断，未验证适配器是否存在/可执行。  
3. `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/base.py` 先发出 MCP 失败 `tool_result`，再执行本地成功，前端会出现失败+完成混合观感。  
4. `/Users/apple/Project/AuditTool/backend/Dockerfile` 默认未安装 `node/npx`，而 filesystem/code-index/memory/sequential MCP 默认命令依赖 `npx`。  

## 变更范围
1. MCP 运行时与路由  
`/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py`  
`/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/router.py`  
`/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/catalog.py`  
`/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/virtual_tools.py`  
新增 `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/qmd_index.py`  

2. Agent 执行层  
`/Users/apple/Project/AuditTool/backend/app/services/agent/agents/base.py`  
`/Users/apple/Project/AuditTool/backend/app/services/agent/prompts/system_prompts.py`  
`/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`  

3. 配置与部署  
`/Users/apple/Project/AuditTool/backend/app/core/config.py`  
`/Users/apple/Project/AuditTool/backend/env.example`  
`/Users/apple/Project/AuditTool/backend/Dockerfile`  
`/Users/apple/Project/AuditTool/docker/sandbox/Dockerfile`  
`/Users/apple/Project/AuditTool/docker-compose.yml`  
`/Users/apple/Project/AuditTool/docker-compose.prod.yml`  
`/Users/apple/Project/AuditTool/docker-compose.prod.cn.yml`  

4. 前端 MCP 目录展示  
`/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/mcpCatalog.ts`  
`/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/SkillToolsPanel.tsx`  

5. 测试  
`/Users/apple/Project/AuditTool/backend/tests/test_mcp_tool_routing.py`  
`/Users/apple/Project/AuditTool/backend/tests/test_mcp_catalog.py`  
新增 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_runtime_health_guard.py`  
新增 `/Users/apple/Project/AuditTool/backend/tests/test_qmd_mcp_integration.py`  

## 详细实施设计

## 1) MCP 可用性预检与熔断（全适配器统一）
1. 在 `MCPRuntime` 增加“真实可处理”判定：路由存在 + adapter 存在 + adapter 可用。  
2. `FastMCPStdioAdapter` 增加 `is_available()`：  
- 校验 command 非空。  
- 校验可执行路径或 `shutil.which(command)` 命中。  
- 结果缓存到实例级，避免每次重复探测。  
3. `MCPRuntime` 增加失败熔断状态：  
- 记录每个 adapter 的连续基础设施错误（如 `ENOENT/command not found/adapter_unavailable`）。  
- 达到阈值后本任务内临时禁用该 adapter，直接走本地工具，不再反复尝试。  
4. 熔断与可用性元数据透传：  
- `mcp_skipped=true`  
- `mcp_skip_reason=adapter_unavailable|adapter_disabled_after_failures|command_not_found`  
- `mcp_adapter`  

## 2) BaseAgent 回退收敛（避免“先失败后成功”）
1. 调整 `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/base.py` 的 MCP-first 分支：  
- 当 `mcp_result.success=false` 且 `should_fallback=true` 且本地可回退时，不立即发 failed 终态日志。  
- 继续执行本地工具，并在最终 `tool_result` 的 metadata 标记：`mcp_fallback_used=true`、`mcp_fallback_error=<...>`。  
2. 仅在“无本地回退”或“mcp should_fallback=false”时返回失败。  
3. 预期效果：前端日志只看到一次最终状态，不再出现误导性的失败残留。  

## 3) qmd MCP 集成（所有 Agent 可用）
1. 新增 qmd adapter 配置项：  
- `MCP_QMD_ENABLED`  
- `MCP_QMD_COMMAND`（默认 `qmd`）  
- `MCP_QMD_ARGS`（默认 `mcp`）  
- `QMD_INDEX_GLOB`  
- `QMD_COLLECTION_PREFIX`  
- `QMD_LAZY_INDEX_ENABLED`  
- `QMD_AUTO_EMBED_ON_FIRST_USE`  
- `QMD_DATA_DIR`  
2. 路由新增（`router.py`）：  
- `qmd_query -> qmd/query`  
- `qmd_get -> qmd/get`  
- `qmd_multi_get -> qmd/multi_get`  
- `qmd_status -> qmd/status`  
3. 入参归一化：  
- `qmd_query` 支持简写 `{"query":"..."} ` 自动转换为 `searches=[{"type":"vec","query":"..."}]`。  
- 默认注入 `collections=[<task_project_collection>]`，保证检索限定在当前项目。  
4. 所有 Agent 工具集中加入只读虚拟工具占位（与 MCP 写虚拟工具同模式）：  
- Recon/Analysis/Verification/Orchestrator 均可调用 qmd 工具。  
5. 提示词补充 `qmd_query` 推荐场景：语义上下文检索优先，失败自动回退 `search_code/read_file`。  

## 4) qmd 懒加载索引与持久化
1. 新增 `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/qmd_index.py`：  
- `ensure_project_collection(project_root, project_id)`  
- 规则：若集合不存在则 `qmd collection add <root> --name <collection> --pattern <glob>`；存在则跳过。  
- 首次调用可选 `qmd update --embed`（受 `QMD_AUTO_EMBED_ON_FIRST_USE` 控制）。  
2. 触发时机：  
- 首次调用 qmd 工具时执行 ensure（lazy）。  
- 失败时不阻断任务，降级本地工具。  
3. 持久化目录：  
- backend 使用持久卷（例如 `/app/data/qmd`）承载 `XDG_DATA_HOME/XDG_CACHE_HOME`。  
- sandbox 通过后端挂载可持久路径（例如 `/tmp/deepaudit/qmd-cache`）映射到容器可写目录。  

## 5) 后端与沙箱镜像支持
1. `/Users/apple/Project/AuditTool/backend/Dockerfile` 安装 qmd 运行时依赖并预装 qmd。  
2. `/Users/apple/Project/AuditTool/docker/sandbox/Dockerfile` 同步安装 qmd。  
3. compose 文件增加 qmd 数据卷与环境变量，确保重启后索引和缓存不丢失。  

## 6) MCP 目录与展示同步
1. `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/catalog.py` 新增 `qmd` 条目。  
2. `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/mcpCatalog.ts` 增加默认 `qmd` 展示项。  
3. `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/SkillToolsPanel.tsx` 无需结构变更，仅展示后端下发目录即可。  

## 公共接口 / 类型影响
1. 不新增后端 HTTP 路由。  
2. `GET /api/v1/config/me` 的 `otherConfig.mcpConfig.catalog` 新增 `qmd` 目录项。  
3. `tool_result` metadata 增强（向后兼容）：  
- `mcp_skipped`  
- `mcp_skip_reason`  
- `mcp_fallback_used`  
- `mcp_fallback_error`  
4. 不改变现有任务与 findings 外层响应结构。  

## 测试计划

## 后端单测
1. `test_mcp_runtime_health_guard.py`  
- command 缺失时 `can_handle=false`，直接走本地，不触发 MCP 调用。  
- adapter 连续基础设施失败后熔断生效。  

2. `test_mcp_tool_routing.py`  
- MCP 失败可回退时最终仅返回本地成功路径，并带 `mcp_fallback_used=true`。  
- `qmd_query/qmd_get/qmd_multi_get/qmd_status` 路由正确。  

3. `test_qmd_mcp_integration.py`  
- `qmd_query` 简写参数自动转换为 `searches`。  
- 首次调用触发项目集合 ensure（mock subprocess）。  
- qmd 不可用时回退 `search_code/read_file`。  

4. `test_mcp_catalog.py`  
- catalog 包含 `qmd`，且 `config/me` 返回只读 catalog。  

## 手工验收
1. 启动智能审计后，`read_file/list_files/search_code` 不再先报 MCP 失败再成功。  
2. 关闭或卸载某 MCP 命令后，系统应自动跳过该 MCP 并稳定回退，不重复刷失败。  
3. `qmd` 可被四类 Agent 调用，且检索内容绑定当前项目集合。  
4. 重启 backend/sandbox 后，qmd 索引缓存仍在（持久化生效）。  

## 建议执行命令
1. `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest /Users/apple/Project/AuditTool/backend/tests/test_mcp_runtime_health_guard.py /Users/apple/Project/AuditTool/backend/tests/test_mcp_tool_routing.py /Users/apple/Project/AuditTool/backend/tests/test_qmd_mcp_integration.py /Users/apple/Project/AuditTool/backend/tests/test_mcp_catalog.py`  
2. `cd /Users/apple/Project/AuditTool/frontend && npm run type-check && npm run build`  
3. `cd /Users/apple/Project/AuditTool && docker compose build backend sandbox && docker compose up -d`  

## 假设与默认
1. qmd 使用 MCP stdio 形态接入（`qmd mcp`），不新增独立 HTTP sidecar。  
2. 懒加载索引优先：首次 qmd 调用触发集合初始化；失败不阻断审计主流程。  
3. MCP 失败熔断是任务级临时状态，不写数据库。  
4. 现有“全 Agent 可写但禁止全项目写入”的写入守卫策略保持不变。  

---

# 增量合并计划：缺陷详情代码窗口化 + 验证/PoC Skill 精简

## 摘要
在现有 `code_to_write.md` 方案基础上，追加两项前端收敛改造：
1. 智能审计“潜在缺陷”详情页增加代码窗口渲染（符合人类阅读习惯），用于展示真实命中代码与必要上下文。
2. 删除“漏洞验证与 PoC 规划”分组下 7 个 skill 工具条目，避免工具目录冗余与误导。

## 目标与验收标准
1. 缺陷详情弹窗中，根因段落保持为后端 `description` 的唯一主叙述源。
2. 若存在 `code_snippet/code_context`，以“代码窗口”样式展示，支持滚动、行号、文件与行区间标题，不再用普通文本块展示代码。
3. 审计工具页中不再出现以下 7 个 skill：
- `test_command_injection`
- `test_deserialization`
- `test_path_traversal`
- `test_sql_injection`
- `test_ssti`
- `test_xss`
- `universal_vuln_test`
4. 删除后工具页无空分组残留，“漏洞验证与 PoC 规划”分类不再展示。

## 变更范围
1. 缺陷详情 UI
- `/Users/apple/Project/AuditTool/frontend/src/pages/AgentAudit/components/AuditDetailDialog.tsx`
- `/Users/apple/Project/AuditTool/frontend/src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx`
- 新增（推荐）`/Users/apple/Project/AuditTool/frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`

2. 审计工具目录
- `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/skillToolsCatalog.ts`
- `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/SkillToolsPanel.tsx`
- `/Users/apple/Project/AuditTool/frontend/src/shared/i18n/dom-dictionaries/index.ts`

## 详细实施设计

### 1) 缺陷详情代码窗口化
1. 在详情弹窗增加独立“命中代码”区块（与“漏洞详情（根因）”分离）。
2. 代码区块使用窗口式容器（标题栏 + 内容区）：
- 标题栏显示：相对路径 + 行范围（如 `src/time64.c:168-196`）。
- 内容区显示：等宽字体、深浅对比背景、边框、最大高度、纵向滚动。
- 增加行号渲染（可按 `line_start` 偏移）。
3. 渲染优先级：
- 优先 `code_context`（若存在，信息更完整）。
- 其次 `code_snippet`。
- 均不存在则不渲染代码窗口（不显示占位假数据）。
4. 严格“非虚构”约束：
- 仅展示后端已返回的真实代码字段。
- 前端不拼接、不推断、不生成伪代码。
5. 根因文段保持：
- 继续只展示后端 `description`。
- 删除任何前端对根因文本的推断或补写逻辑。

### 2) 7 个验证/PoC Skill 删除
1. 从 `SKILL_TOOLS_CATALOG` 删除 7 个工具对象：
- `test_command_injection`
- `test_deserialization`
- `test_path_traversal`
- `test_sql_injection`
- `test_ssti`
- `test_xss`
- `universal_vuln_test`
2. 同步更新分类类型与顺序：
- `SkillToolCategory` 中移除 `"漏洞验证与 PoC 规划"`。
- `SKILL_TOOL_CATEGORY_ORDER` 中移除该分类。
- `SkillToolsPanel.tsx` 的 `CATEGORY_DESC` 删除该项，避免空分组。
3. i18n 清理：
- 移除或保留兼容映射均可；若保留，确保前端不会再引用该分类键。

### 3) 兼容与风险控制
1. 不修改后端 API 与数据库结构。
2. `AgentFinding` 类型无需新增字段，复用已有 `code_snippet/code_context/file_path/line_start/line_end`。
3. 代码窗口为“有数据才展示”，避免旧任务历史数据缺失时出现空白噪声。

## 公共接口 / 类型影响
1. 无 HTTP 路由变更。
2. 前端本地类型调整：
- `SkillToolCategory` 枚举值减少 1 项。
- `SKILL_TOOLS_CATALOG` 条目减少 7 项。
3. 缺陷详情 UI 展示语义调整：
- “漏洞详情（根因）”仍唯一使用 `description`。
- 代码展示改为窗口化组件，不影响数据契约。

## 测试与验收

### 前端手工验收
1. 打开任意潜在缺陷“查看详情”：
- 可见“漏洞详情（根因）”段落。
- 若存在代码字段，可见代码窗口（标题栏、行号、滚动区域）。
2. 无代码字段的历史缺陷：
- 不显示代码窗口，不出现伪造占位内容。
3. 打开 `/intelligent-audit` -> `审计工具`：
- 不再出现 7 个验证/PoC skill。
- 不再出现“漏洞验证与 PoC 规划”分组。

### 构建检查
1. `cd /Users/apple/Project/AuditTool/frontend && npm run type-check && npm run build`

## 假设与默认
1. 本次“删除 7 个 skill 工具”限定为审计工具目录展示层（前端 catalog），不直接移除后端真实工具实现。
2. 代码窗口仅为阅读体验增强，不改变审计判定逻辑。
3. 根因文本继续由后端统一生成，前端仅渲染。

---

# 增量合并计划：所有 MCP 支持后端本地启动 + 沙盒启动

## 摘要
补充硬要求：当前涉及的所有 MCP，必须同时支持两种运行域：
1. 后端本地运行域（Backend runtime）
2. 沙盒运行域（Sandbox runtime）

并要求具备可配置切换、健康检查、失败降级与持久化目录，不允许仅在单一运行域可用。

## 覆盖范围（MCP 清单）
以下 MCP 全部纳入“双运行域支持”：
1. `filesystem` MCP
2. `code_index` MCP
3. `memory` MCP
4. `sequentialthinking` MCP
5. `qmd` MCP
6. `codebadger/joern` MCP（HTTP 型，作为 flow 深度验证 MCP）

## 目标与验收标准
1. 任一 MCP 在 `backend` 域不可用时，可按策略切换到 `sandbox` 域执行（或反向）。
2. 任一 MCP 的运行域切换不改外层 API，不影响 Agent 工具调用名称与输入结构。
3. 所有 MCP 都有统一健康检查与熔断逻辑，避免重复“先失败再回退”噪音。
4. MCP 相关缓存/索引（尤其 `qmd/memory/code_index`）在 backend 与 sandbox 均可持久化。

## 变更范围
1. 后端运行时与配置
- `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py`
- `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/router.py`
- `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`
- `/Users/apple/Project/AuditTool/backend/app/core/config.py`
- `/Users/apple/Project/AuditTool/backend/env.example`

2. 部署与镜像
- `/Users/apple/Project/AuditTool/backend/Dockerfile`
- `/Users/apple/Project/AuditTool/docker/sandbox/Dockerfile`
- `/Users/apple/Project/AuditTool/docker-compose.yml`
- `/Users/apple/Project/AuditTool/docker-compose.prod.yml`
- `/Users/apple/Project/AuditTool/docker-compose.prod.cn.yml`

3. 前端配置展示（只读或可调）
- `/Users/apple/Project/AuditTool/frontend/src/components/system/SystemConfig.tsx`
- `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/mcpCatalog.ts`
- `/Users/apple/Project/AuditTool/frontend/src/pages/intelligent-audit/SkillToolsPanel.tsx`

4. 测试
- 新增 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_dual_runtime_policy.py`
- 新增 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_dual_runtime_fallback.py`
- 补充 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_tool_routing.py`
- 补充 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_catalog.py`

## 详细实施设计

### 1) MCP 运行域模型统一
1. 在 MCP 配置中为每个 MCP 增加 `runtime_mode`：
- `backend_only`
- `sandbox_only`
- `prefer_backend`
- `prefer_sandbox`
- `backend_then_sandbox`
- `sandbox_then_backend`
2. 默认策略（建议）：
- `filesystem/code_index/memory/sequentialthinking/qmd`：`backend_then_sandbox`
- `codebadger/joern`：`backend_only`（若已以独立服务部署），或 `backend_then_sandbox`（当沙盒内也部署服务）
3. 运行时决策在 `MCPRuntime` 内统一处理，不分散到各 Agent。

### 2) 双运行域适配器实现
1. 为 stdio MCP 增加 `BackendStdioAdapter` 与 `SandboxStdioAdapter`：
- Backend adapter：直接在后端容器执行命令。
- Sandbox adapter：通过沙盒执行器在 sandbox 容器执行命令。
2. 为 HTTP MCP（如 codebadger）增加可选双端点：
- `MCP_CODEBADGER_BACKEND_URL`
- `MCP_CODEBADGER_SANDBOX_URL`
3. 适配器统一暴露：
- `is_available()`
- `call_tool()`
- `runtime_domain`（`backend|sandbox`）

### 3) 健康检查、熔断与回退
1. 每个 MCP + 运行域维护独立健康状态与失败计数。
2. 熔断粒度：`(mcp_name, runtime_domain)`，避免一个域失败影响另一个域。
3. 回退顺序遵循 `runtime_mode`；若主域失败，自动切换备用域。
4. 事件 metadata 新增：
- `mcp_runtime_domain`
- `mcp_runtime_fallback_used`
- `mcp_runtime_fallback_from`
- `mcp_runtime_fallback_to`

### 4) 持久化策略
1. backend 域：
- MCP 数据根目录统一挂载（例如 `/app/data/mcp`）。
2. sandbox 域：
- 挂载持久化目录（例如 `/tmp/deepaudit/mcp-cache`）至 sandbox。
3. `qmd` 特殊要求：
- `XDG_DATA_HOME/XDG_CACHE_HOME` 在两域分别配置为可持久路径。
- collection/index 元数据持久保留，避免每次冷启动重建。

### 5) 启动与部署要求
1. 后端镜像与沙盒镜像都预装运行所需二进制：
- `node/npx`（filesystem/code_index/memory/sequentialthinking 需要）
- `qmd`（qmd MCP 需要）
2. compose 中明确：
- backend 与 sandbox 的 MCP 数据卷
- MCP 运行域开关与策略环境变量
3. 若某 MCP 在某域未启用，catalog 需要体现域级状态（例如 backend enabled / sandbox disabled）。

### 6) 前端配置与目录展示
1. 在 `SystemConfig` 增加运行域策略展示与可配置项（若允许用户配置）。
2. 在 MCP 目录中展示每个 MCP 的域能力：
- `backend: enabled/disabled`
- `sandbox: enabled/disabled`
- `runtime_mode`
3. 展示仅为配置可观测，不改变前端调用协议。

## 公共接口 / 类型影响
1. 不新增任务路由。
2. `config/me` 的 `otherConfig.mcpConfig` 增加（向后兼容）：
- `runtimePolicy`（按 MCP 维度）
- `runtimePersistence`（目录配置只读返回）
3. `tool_result` metadata 增强（向后兼容）：
- `mcp_runtime_domain`
- `mcp_runtime_fallback_used`
- `mcp_runtime_fallback_from`
- `mcp_runtime_fallback_to`

## 测试与验收

### 后端单测
1. `test_mcp_dual_runtime_policy.py`
- 验证不同 `runtime_mode` 的路由顺序正确。
2. `test_mcp_dual_runtime_fallback.py`
- 主域失败后切换备用域成功。
- 主域熔断不影响备用域。
3. `test_mcp_tool_routing.py` 补充
- 断言 metadata 含 `mcp_runtime_domain` 与 fallback 字段。
4. `test_mcp_catalog.py` 补充
- catalog 能返回每个 MCP 的 backend/sandbox 域状态。

### 手工验收
1. 禁用 backend 域某 MCP，可在 sandbox 域继续执行。
2. 禁用 sandbox 域某 MCP，可在 backend 域继续执行。
3. 两域都可用时，按 `runtime_mode` 选择主域并正常回退。
4. 重启后 qmd/code_index/memory 数据仍存在（两域均验证）。

### 构建检查
1. `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest /Users/apple/Project/AuditTool/backend/tests/test_mcp_dual_runtime_policy.py /Users/apple/Project/AuditTool/backend/tests/test_mcp_dual_runtime_fallback.py /Users/apple/Project/AuditTool/backend/tests/test_mcp_tool_routing.py /Users/apple/Project/AuditTool/backend/tests/test_mcp_catalog.py`
2. `cd /Users/apple/Project/AuditTool/frontend && npm run type-check && npm run build`

## 假设与默认
1. “本地后端启动”定义为 backend 容器/进程内可执行，不依赖宿主机全局环境。
2. “沙盒启动”定义为 sandbox 容器内可执行，且支持持久化目录挂载。
3. MCP 双域支持是运行时增强，不要求新增数据库迁移。

---

# 强约束补充：后端启动或沙盒运行时，MCP 必须全量启动

## 摘要
再次确认并提升为硬约束：
1. 当系统以后端域运行时，所有纳管 MCP 必须全部启动并可健康调用。
2. 当系统以沙盒域运行时，所有纳管 MCP 也必须全部启动并可健康调用。
3. 所有 Agent（Orchestrator / Recon / Analysis / Verification）必须在任一运行域下都能连接并调用全部 MCP。

## 约束清单
1. 不允许“仅启动部分 MCP”进入可执行状态。  
2. 不允许因单个 MCP 未启动而静默降级为“该 MCP 不可见”。  
3. 启动阶段必须执行全量 MCP 健康检查，未全部就绪则任务入口标记为 `not_ready` 并拒绝启动智能审计任务。  
4. `catalog` 必须反映真实运行态：仅当 MCP 进程已就绪且可调用时才标记 `enabled=true`。  
5. 两个运行域都应具备同构 MCP 集合（`filesystem/code_index/memory/sequentialthinking/qmd/codebadger`），避免 Agent 行为在域间漂移。

## 实施补充
1. 在 `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py` 新增 `ensure_all_mcp_ready(runtime_domain)`：
- 启动后主动探测全部 MCP。
- 返回 `ready=false` 时附带未就绪 MCP 列表和原因。
2. 在 `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py` 的任务启动前增加硬门禁：
- 若当前域 `ensure_all_mcp_ready=false`，直接返回可解释错误并阻止任务启动。
3. 在 `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/catalog.py` 增强状态字段：
- `required=true`
- `startup_ready=true|false`
- `startup_error`（若失败）
4. 在 `/Users/apple/Project/AuditTool/frontend/src/components/system/SystemConfig.tsx` 与 MCP 目录中增加就绪提示：
- 显示“全量 MCP 未就绪，任务不可启动”的阻断信息。

## 测试补充
1. 新增 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_startup_all_required.py`：
- 任一 MCP 未启动时，`ensure_all_mcp_ready=false`。
- 任务启动接口被拒绝并返回未就绪清单。
2. 补充 `/Users/apple/Project/AuditTool/backend/tests/test_mcp_dual_runtime_policy.py`：
- backend 域全量就绪可启动；sandbox 域全量就绪可启动。
- 任一域缺失 MCP 时，该域任务启动被拒绝。
3. 手工验收：
- 分别在 backend/sandbox 启动模式下验证“全 MCP 就绪后才能发起审计”。
- 四类 Agent 均可调用全部 MCP（含 qmd/memory/sequentialthinking/code_index/filesystem/codebadger）。
