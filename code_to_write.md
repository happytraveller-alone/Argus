# 两周落地清单（P0 -> P1）：智能审计可用性与吞吐优化（不改业务规则）

## 摘要
- 目标：两周内先解决“任务起不来/工具不可用”（P0），再提升“工具利用率与运行效率”（P1）。
- 约束：不改审计业务规则，不改 required 语义，不放松严格门禁，不改漏洞判定口径。
- 范围：仅改运行时编排、MCP 探针与路由、工具暴露与性能护栏。

---

## 公共接口 / 配置变更（向后兼容）
1. 后端配置新增（可选）
   - `AGENT_EVENT_QUEUE_MAXSIZE`（默认 1500）
   - `AGENT_EVENT_MAX_PAYLOAD_CHARS`（默认 300000）
   - `AGENT_EVENT_DB_SKIP_TYPES`（默认扩展到高频非关键事件）
2. 后端配置清理（破坏性变更）
   - 删除 `MCP_QMD_*` 系列配置项（`config.py` 与 `env.example` 同步移除）
3. 不改现有 API 路径；仅增强内部行为：
   - `POST /api/v1/config/mcp/tools/list` 继续可用，用于上线后巡检
   - `POST /api/v1/config/qmd/cli/test` 继续作为 QMD CLI 健康检查
4. Smart audit 运行策略保持：
   - 仍 `mcp_only_enforced=true`
   - 仍 required MCP 严格门禁（`filesystem + code_index`）

---

## Week 1（P0：可用性，先消除阻断）

### D1：基线与失败矩阵固化
- 建立 3 类基线：启动门禁通过率、任务启动成功率、QMD 查询成功率。
- 记录当前失败签名（required gate、mcp_adapter_unavailable、probe_failed）。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py`

### D2：修复 required probe 语义错配（核心）
- 改 `_probe_required_mcp_runtime`，让 `filesystem` probe 真实走 filesystem 读能力，不再借道 code_index 语义。
- `code_index` probe 使用 code_index 真实检索能力（pattern/query 路径）。
- probe 输入改为任务目录绝对路径优先，避免 cwd 漂移。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/protocol_verify.py`
- DoD：
  - required gate 失败日志中不再出现“filesystem 用 code_index 探针”的错配现象。

### D3：QMD 全量切本地执行并移除 QMD MCP（核心）
- 目标：`qmd_query/qmd_get/qmd_multi_get/qmd_status` 在 strict 模式始终稳定执行，且仅走本地 CLI tool。
- 方案：
  - 从任务运行时彻底移除 QMD MCP adapter / route / config 依赖（不再保留 QMD MCP 执行链路）。
  - 清理范围覆盖：`runtime/router` 以及 `daemon_manager.py`、`probe_specs.py`、`protocol_verify.py` 中 qmd 分支。
  - BaseAgent 中对 `qmd_*` 增加前置本地直调；单次失败自动重试 1 次，再失败报错返回；不做 `search_code/read_file` fallback。
  - 保留 `POST /api/v1/config/qmd/cli/test` 作为 QMD 唯一健康检查入口。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/router.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/base.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/daemon_manager.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/probe_specs.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/protocol_verify.py`
  - `/Users/apple/Project/AuditTool/backend/app/core/config.py`
  - `/Users/apple/Project/AuditTool/backend/env.example`
- DoD：
  - 在 `QMD_TASK_KB_ENABLED=true` 下，`qmd_query` 稳定返回结果，且 metadata 标识 `qmd_direct_call=true`。

### D4：门禁诊断可读化（不改门禁规则）
- 保持阻断语义不变，只增强故障定位：
  - 将 not_ready 明细标准化（mcp、domain、reason、probe tool、attempt）。
  - 统一 `mcp_adapter_unavailable:*` 与 `mcp_call_failed:*` 分类字段。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/catalog.py`

### D5：P0 回归 + 容器端到端验收
- 验证路径：
  1) 起容器  
  2) 调 `/api/v1/config/qmd/cli/test`  
  3) 启智能审计任务  
  4) 验证 required gate、QMD 查询、任务启动成功  
- 脚本化巡检（一次命令完成）并产出报告。

---

## Week 2（P1：吞吐与效率，保持规则不变）

### D6：扩展 code_index 高价值工具暴露
- 在智能审计工具集里将 code_index 能力作为一等工具暴露（非仅 `locate_enclosing_function`）：
  - `get_symbol_body`
  - `get_file_summary`
  - `get_settings_info`
  - `create_temp_directory`
- 暴露范围：
  - `get_symbol_body/get_file_summary/get_settings_info`：全阶段（recon/analysis/verification/orchestrator）
  - `create_temp_directory`：仅 analysis/verification
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/api/v1/endpoints/agent_tasks.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/router.py`
- DoD：
  - `tools/list` 能看到上述工具，且可在审计流程被实际调用。

### D7：提示词与工具策略对齐（减少低效 search/read 循环）
- 将“symbol-first”策略写入系统提示词：
  - 先 `get_file_summary/get_symbol_body`，后 `read_file` 窗口化取证；
  - `search_code` 仅用于精确定位。
  - 强度定义为“软规则”：优先推荐，不做硬阻断；失败时可直接走 `read_file/search_code`。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/prompts/system_prompts.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/analysis.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/recon.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/verification.py`

### D8：MCP 检索缓存与重复调用抑制增强
- 扩展 runtime retrieval cache 覆盖工具：
  - 新增 `get_symbol_body/get_file_summary/get_settings_info`
- 强化重复失败短路策略，减少无效 retries。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/mcp/runtime.py`
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/agents/base.py`

### D9：事件管道背压优化（不改业务事件）
- 降低单事件 payload 与队列深度（可配置），并扩展 DB 跳过高频噪声事件。
- 文件：
  - `/Users/apple/Project/AuditTool/backend/app/services/agent/event_manager.py`
  - `/Users/apple/Project/AuditTool/backend/app/core/config.py`
  - `/Users/apple/Project/AuditTool/backend/env.example`
- DoD：
  - 长任务下 UI 事件延迟下降，DB 写入压力明显下降。

### D10：P1 回归 + 性能验收
- 验收指标（与 D1 基线对比）：
  - 任务启动成功率
  - required gate 通过率
  - 平均任务耗时（P50/P90）
  - 单任务 tool call 数与重复率
  - 事件入库条数与平均 payload
- 产出上线清单与回滚方案。

---

## 测试用例与验收场景

### 新增/调整后端测试
- `/Users/apple/Project/AuditTool/backend/tests/test_mcp_startup_probe_mapping.py`
  - 断言 required probe 的 filesystem/code_index 工具语义正确；副作用工具兜底时直接失败
- `/Users/apple/Project/AuditTool/backend/tests/test_mcp_tool_routing.py`
  - 断言 strict 模式下 `qmd_*` 强制本地直调，失败自动重试 1 次，且不再尝试 QMD MCP 路由
- `/Users/apple/Project/AuditTool/backend/tests/test_qmd_cli_tools.py`
  - `qmd_query/get/multi_get/status` 在任务 KB 上可执行
- `/Users/apple/Project/AuditTool/backend/tests/test_agent_task_runtime_tools.py`
  - code_index 新增工具被暴露并可路由；`create_temp_directory` 仅 analysis/verification 可见
- `/Users/apple/Project/AuditTool/backend/tests/test_event_manager_backpressure.py`
  - 队列/payload/DB skip 策略生效；队列满时优先丢噪声事件，关键事件不丢

### 建议回归命令
- `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest tests/test_mcp_tool_routing.py`
- `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest tests/test_mcp_verify_endpoint.py`
- `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest tests/test_qmd_cli_tools.py`
- `cd /Users/apple/Project/AuditTool/backend && .venv/bin/pytest tests/test_mcp_catalog.py`

---

## 风险与回滚
- 风险1：QMD MCP 链路移除后，历史依赖 QMD MCP 的脚本/配置会失效。  
  - 回滚：通过 `QMD_AGENT_DIRECT_CALL_ENABLED` 降级为“禁用 qmd_* 调用”并快速止血（不恢复 QMD MCP）。
- 风险2：事件降噪导致前端细节不足。  
  - 回滚：恢复原 `MAX_EVENT_PAYLOAD_CHARS` 与 `queue maxsize`。
- 风险3：code_index 新工具暴露后调用激增。  
  - 护栏：保留重复调用短路与缓存上限，超限自动退回原策略。

---

## 假设与默认
- 默认维持：QMD MCP 适配器/路由/配置全部移除，仅 CLI 本地运行。
- 默认维持：required MCP 仍是 `filesystem + code_index`，严格阻断不变。
- 默认维持：不改漏洞判定规则、不改最终报告字段契约，只改运行时可用性与效率路径。

## 计划补丁段落（可直接粘贴到 `code_to_write.md`）

### 附录A：实施细化补丁（10项决策已锁定）

#### 1) required 探针矩阵（动态，不写死工具名）
- 不再硬编码 `filesystem/code_index` 的固定 probe tool 映射。
- required MCP 门禁流程统一为：
  1. `tools/list`（失败即 fail-fast）  
  2. 从可见 tool 中动态选 1 个“可读/无副作用”工具执行 `tools/call`。
- 工具选择规则（按顺序）：
  - 优先非内部工具（继续隐藏 `set_project_path/configure_file_watcher/refresh_index/build_deep_index`）。
  - 优先名称命中：`list*`, `read*`, `search*`, `get*summary*`, `get*info*`。
  - 若无命中，退化为列表第一个可调用工具。
- 参数构造继续复用 `protocol_verify.build_tool_args(...)` 自动生成，不再为某 MCP 固定写死参数模板。

#### 2) 门禁失败与重试策略（required）
- `tools/list`：失败直接 fail-fast（不重试）。
- `tools/call`：任何失败都重试 2 次，固定退避 300ms（attempt 间隔）。
- 运行形态口径：
  - MCP 服务启动方式统一采用源码启动链路（Docker 与本地源码运行均一致）。
  - Docker 运行：required MCP 在 backend+sandbox 双域均需完成 `tools/list + tools/call` 并成功。
  - 本地源码运行：required MCP 仅校验 backend，可不因 sandbox 未就绪而阻断任务。
- 诊断字段强制统一：`mcp`, `runtime_domain`, `step`, `tool`, `attempt`, `error_code`, `raw_error`。

#### 3) QMD 执行路径（Agent层直调）
- `qmd_query/qmd_get/qmd_multi_get/qmd_status` 在 BaseAgent 中前置直调本地工具（不依赖 qmd MCP adapter）。
- 直调失败策略：自动重试 1 次，再失败报错返回，不做 `search_code/read_file` fallback。
- QMD MCP 清理策略：删除 QMD MCP adapter / route / env 配置（含 `daemon_manager.py`、`probe_specs.py`、`protocol_verify.py` 的 qmd 分支），不保留“可切回 QMD MCP”的执行路径。
- strict 语义保持：qmd_* 不参与 MCP strict 路由判定，其余工具仍走 MCP strict 门禁。
- 事件 metadata 新增统一标识：`qmd_direct_call=true`、`qmd_direct_error=<...>`。

#### 4) code_index 新工具暴露与入参方针（显式白名单）
- 在 `_initialize_tools` 显式注入：`get_symbol_body`, `get_file_summary`, `get_settings_info`, `create_temp_directory`。
- 暴露范围：
  - `get_symbol_body/get_file_summary/get_settings_info`：recon/analysis/verification/orchestrator 全阶段可用。
  - `create_temp_directory`：仅 analysis/verification 可用。
- 路由与别名映射明确：
  - `extract_function -> get_symbol_body`
  - `locate_enclosing_function -> get_file_summary`
  - 长期保留旧别名兼容（含 `extract_function` 等），新工具原名同时直达。
- 入参冲突优先级固定：显式目标字段 > 兼容别名字段 > 默认值自动补齐。

#### 5) 提示词改造范围（全局）
- 覆盖文件：
  - `system_prompts.py`
  - `analysis.py` / `recon.py` / `verification.py` 各自 system prompt
- 统一策略：
  - “symbol-first”（软规则）：先推荐 `get_file_summary/get_symbol_body`，后 `read_file` 窗口化取证。
  - `search_code` 降级为精确匹配工具，但在 symbol 工具失败时允许直接使用。
- 清理旧冲突指令（尤其与 qmd/search_code 旧优先级冲突项）。

#### 6) 缓存策略（量化：平衡档）
- MCP runtime retrieval cache：
  - `LRU=3000`
  - `TTL=15min`
  - 覆盖工具：`read_file, search_code, get_symbol_body, get_file_summary, get_settings_info`
- Agent 成功结果缓存：
  - `LRU=800`
  - `TTL=10min`
- cache key 统一：`project_root + runtime_domain + tool_name + normalized_args + adapter_name`
- 失效规则：
  - `refresh_index/build_deep_index` 后立即失效对应项目 code_index 缓存；
  - 任务切换（task_id 变化）不共享 agent 缓存。

#### 7) 事件背压与截断策略
- 配置默认值：
  - `AGENT_EVENT_QUEUE_MAXSIZE=1500`
  - `AGENT_EVENT_MAX_PAYLOAD_CHARS=300000`
- 队列满时丢弃策略：
  - 优先丢弃噪声事件；
  - 关键事件永不丢：`task_error`, `task_complete`, `finding_new`, `finding_update`, `finding_verified`, `tool_call`, `tool_result`。
- DB 跳过事件（最小跳过）：
  - `thinking_token`, `llm_thought`, `llm_decision`, `todo_update`
- 永不跳过：
  - `task_error`, `task_complete`, `finding_new`, `finding_update`, `finding_verified`, `tool_call`, `tool_result`
- 截断要求：
  - 所有被截断 payload 必写 `truncated=true`（tool_output 与 metadata 两处一致可见）。

#### 8) D10 验收硬阈值（必须达标）
- 启动成功率 `>=95%`
- required gate 通过率 `>=98%`
- 任务 P90 时延较基线下降 `>=20%`
- 事件入库条数较基线下降 `>=35%`
- `qmd_*` 直调成功率 `>=95%`（启用 QMD_TASK_KB 的任务样本）

#### 9) 灰度与回滚开关（建议纳入实现）
- 新增独立开关（默认开启）：
  - `MCP_REQUIRED_DYNAMIC_PROBE_ENABLED`
  - `QMD_AGENT_DIRECT_CALL_ENABLED`
  - `CODE_INDEX_SYMBOL_FIRST_ENABLED`
  - `AGENT_EVENT_BACKPRESSURE_ENABLED`
- 开关语义补充：
  - `QMD_AGENT_DIRECT_CALL_ENABLED=false` 时，`qmd_*` 直接阻断（不回退到 QMD MCP）。
- 回滚顺序：
  1. 关 symbol-first  
  2. 关 dynamic probe  
  3. 关 qmd direct call  
  4. 关 event backpressure

#### 10) 测试夹具与样本固定
- 固定两类项目样本：
  - 小项目（<50 文件）
  - 中型项目（200~800 文件）
- 故障注入场景固定：
  - `tools/list` 失败（adapter_unavailable）
  - `tools/call` 失败（mcp_call_failed）
  - Docker 模式 `runtime_domain=all` 单域失败（整体失败）/双域成功（整体通过）
  - 本地源码模式 backend 成功 + sandbox 缺失（不阻断）
- 新增/补强测试文件（与主计划一致）：
  - `test_mcp_startup_probe_mapping.py`
  - `test_mcp_tool_routing.py`
  - `test_qmd_cli_tools.py`
  - `test_agent_task_runtime_tools.py`
  - `test_event_manager_backpressure.py`

---

### 附录B：已确认的决策记录（追溯）
- required 探针矩阵：不写死，按动态工具能力执行。
- `tools/list` 失败：fail-fast。
- `tools/call` 重试：任何失败都重试 2 次，300ms 退避。
- 门禁部署口径：Docker 双域全量校验；本地源码运行仅校验 backend，不因 sandbox 缺失阻断。
- MCP 启动方式：统一按源码启动链路管理（Docker/本地模式一致）。
- QMD：Agent 层强制本地直调，QMD MCP 适配器/路由/配置全部移除。
- QMD 失败策略：本地直调失败自动重试 1 次，再报错。
- 提示词：全局覆盖（`system_prompts.py + analysis/recon/verification`）。
- symbol-first：软规则，不做硬阻断。
- 缓存：量化采用“平衡档”。
- 截断：统一写 `truncated=true`。
- 新工具暴露：前三个全阶段可用；`create_temp_directory` 仅 analysis/verification；旧别名长期兼容。
- 测试策略：新增测试文件并同步补旧测试。
- 灰度开关：4 个开关全部落地且默认开启。

### 假设与默认
- 若 MCP 返回工具描述缺失，仍允许调用（基于 schema 自动补参）。
- 不改变 required MCP 范围（仍 `filesystem + code_index`）。
- 不改变业务审计判定逻辑，仅改运行时可用性与性能路径。

### 附录C：本轮确认结果（2026-02-27）
- QMD 方案：`qmd_*` 全部强制本地执行，QMD MCP 相关执行链路与配置项彻底删除。
- QMD 清理边界：`daemon_manager.py`、`probe_specs.py`、`protocol_verify.py` 的 qmd 分支一并删除。
- QMD 旧配置：`MCP_QMD_*` 全部删除。
- required 探针：采用“自动挑工具”策略，不再写死 probe 工具名。
- `tools/call` 重试范围：任何失败都重试。
- `qmd_*` 失败策略：本地直调失败自动重试 1 次。
- `runtime_domain` 口径：Docker 双域全量校验；本地源码运行按 backend 校验，不强制 sandbox。
- MCP 启动方式：Docker 与本地源码运行都按源码启动链路拉起。
- code_index 新工具：保留旧别名长期兼容；`create_temp_directory` 仅 analysis/verification 可用。
- 提示词范围：全局覆盖（`system_prompts.py + analysis.py + recon.py + verification.py`）。
- symbol-first 强度：软规则（优先建议，失败可直接 read/search）。
- 事件背压：按默认值落地（队列 1500、payload 300000、DB 跳过高频噪声事件）；队列满优先丢噪声，关键事件永不丢。
- 测试策略：按计划新增测试文件，同时补齐受影响旧测试。
- 灰度开关：`MCP_REQUIRED_DYNAMIC_PROBE_ENABLED`、`QMD_AGENT_DIRECT_CALL_ENABLED`、`CODE_INDEX_SYMBOL_FIRST_ENABLED`、`AGENT_EVENT_BACKPRESSURE_ENABLED` 全部实现且默认开启。
