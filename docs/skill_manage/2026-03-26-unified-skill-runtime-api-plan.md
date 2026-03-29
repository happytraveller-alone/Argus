# Unified Skill Runtime API 开发拆解

## 文档定位

- 类型：Implementation plan
- 日期：2026-03-26
- 主题：将当前可用 skill 与 skill 调用流程接口化，替代“模型直接读 skill 文件”的模式
- 目标读者：后续负责落地后端 runtime、skills API、prompt 注入、前端兼容、部署发布的开发者

## 摘要

本次改造把当前 skill 获取与使用方式统一收敛为 API 驱动协议，覆盖三类能力：

1. `scan-core` 工具型 skill
2. registry mirror 的 workflow skill
3. 按 `agent_key` 聚合后的 effective prompt skill

运行时从“模型自行读文件决定该用什么 skill”切换为“宿主先给 catalog 摘要，模型显式选择 skill，宿主再加载对应 detail 文档”。整体目标是强化 skill 指向性、减少 prompt 膨胀、统一 skill 真相源，并把 skill 加载状态变成显式 runtime 状态。

本版拆解额外完成三件事：

- 把前端、后端、部署运维三条线的隐藏前提全部改成显式契约。
- 把“兼容旧接口/旧前端/旧部署”改成可验证的 rollout gate，而不是口头承诺。
- 对原计划中仍然依赖“默认已存在能力”的部分，统一改成先实现、先定义、先约束。

## 已锁定决策

- 本轮先补最小可用 runtime session 能力，不把它作为外部已完成前提。
- v1 继续复用 `/skills/*`，但只允许单选 skill，不支持一次选择多个 skill。
- workflow skill 继续以 registry manifest + mirrored skill dir 作为 canonical source。
- prompt-effective 只能在 DB ready 后按用户/任务实时计算，不能在启动前预构建。
- scan-core 工具硬门禁同轮严格上线，不做先告警后拦截。
- `/config.skillAvailability` 为避免破坏旧客户端，保留旧字段语义；新增 `unifiedSkillAvailability` 作为统一新视图。
- 当前默认开发 compose 不是 unified workflow runtime 的验收环境。
- 生产/发布环境禁止“启动时从 GitHub `main` 安装 skill”作为正式方案。
- v1 中 `ReportAgent` 与其他非五个 prompt-agent 不支持 prompt-effective；prompt-effective 的 `agent_key` 闭集固定为 `recon | business_logic_recon | analysis | business_logic_analysis | verification`。
- v1 中 `/skills/prompt-skills*` 继续作为可编辑管理 API；`prompt-<agent_key>@effective` 只读，不可直接编辑。

## 支持范围矩阵

### 部署模式

| 模式 | workflow registry 默认状态 | prompt-effective 默认状态 | 是否可作为本计划验收环境 |
| --- | --- | --- | --- |
| `docker-compose.yml` 开发态 | 默认关闭，仅 `scan-core only` | 支持，按 DB/用户实时计算 | 否 |
| `docker-compose.full.yml` 全量本地构建 | 仅在提供预生成 registry 或显式 source roots 时支持 | 支持，按 DB/用户实时计算 | 有条件可用 |
| release artifact / 正式部署 | 必须使用预生成 registry | 支持，按 DB/用户实时计算 | 是 |

### 结论

- 默认开发 compose 仅作为 scan-core / prompt CRUD / agent 行为开发环境，不作为 workflow skill runtime 验收环境。
- 正式验收环境必须满足：
  - 存在有效 registry manifest、aliases、mirrored skills
  - `CODEX_SKILLS_AUTO_INSTALL=false`
  - `SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP=false`
  - DB ready 后可按用户解析 prompt-effective

## 目标与边界

### 目标

- 让模型只能通过接口获得可用 skill 概览，而不是直接读 skill 文件。
- 让模型在需要 skill 时先显式选择一个 skill，再获取该 skill 的使用文档。
- 统一 `/skills/catalog`、`/skills/{id}`、`/config` 中 unified skill 视图、runtime prompt 注入、prompt skill 投影之间的口径。
- 引入显式 runtime session 技能加载状态，记录已加载 skill、active workflow/prompt state 和 detail cache。
- 对 scan-core 工具建立硬门禁：未先完成 skill 选择与 detail 加载时，不允许直接调用工具。
- 在不破坏现有前端和 scan-core 详情页/测试页的前提下完成增量迁移。

### 非目标

- 不在本轮完成 Phase 1 全量 session/history 重构。
- 不在本轮完成 checkpoint/recovery。
- 不在本轮做多选 skill 协议。
- 不在本轮把 `docs/agent-tools` 变成 canonical source。
- 不在本轮重写 `build_skill_registry.py` 镜像生成流程，只复用其输出。
- 不在本轮删除旧 prompt skill CRUD、builtin toggle、旧 scan-core 详情页测试能力。

## 当前现状

当前仓库里与本次改造直接相关的事实如下：

### 后端现有实现

**API Endpoints** (`backend/app/api/v1/endpoints/skills.py`):
- `/skills/catalog` 与 `/skills/{id}` 当前只服务 `scan-core`
- 已有基础模型：`SkillCatalogItem`, `SkillCatalogResponse`, `SkillDetailResponse`
- 已实现测试接口：`/skills/{id}/test` 和 `/skills/{id}/tool-test`
- **现状**：仅支持 scan-core，不支持 workflow 和 prompt-effective

**Scan-Core Skills** (`backend/app/services/agent/skills/scan_core.py`):
- 定义了 `_SCAN_CORE_SKILLS` 列表（17个工具）
- 实现了 `get_scan_core_skill_detail()` 和 `search_scan_core_skills()`
- 定义了 `SCAN_CORE_STRUCTURED_TOOL_PRESETS` 用于结构化测试
- **现状**：元数据完整，但展示字段（display_type等）需补充到 API 响应

**Prompt Skills** (`backend/app/services/agent/skills/prompt_skills.py`):
- 实现了 builtin template 和 custom prompt skill 管理
- 定义了 `PROMPT_SKILL_AGENT_KEYS`：`['recon', 'business_logic_recon', 'analysis', 'business_logic_analysis', 'verification']`
- 实现了 scope 解析和 effective 计算逻辑
- **现状**：已有基础能力，但未暴露为 unified skill catalog

**配置** (`backend/app/core/config.py`):
- ✅ 已有：`SCAN_WORKSPACE_ROOT`, `TOOL_RUNTIME_*` 系列配置
- ❌ 缺失：`SKILL_REGISTRY_ROOT`, `SKILL_SOURCE_ROOTS`, `SKILL_REGISTRY_MODE`, `SKILL_REGISTRY_ENABLED`, `SKILL_REGISTRY_REQUIRED`, `CODEX_HOME`

**工具 Runtime** (`backend/app/services/agent/tool_runtime/`):
- 已有 tool runtime 框架和基础抽象
- **现状**：存在但与 skill runtime 未深度集成

### 待实施组件（完全缺失）

**Runtime Session**:
- `backend/app/services/agent/runtime/session.py` - **需新建**
- `backend/app/services/agent/runtime/state.py` - **需新建**
- `backend/app/services/agent/runtime/message_builder.py` - **需新建**

**Unified Skill Services**:
- `backend/app/services/agent/skills/catalog.py` - **需新建**
- `backend/app/services/agent/skills/loader.py` - **需新建**
- `backend/app/services/agent/skills/registry_source.py` - **需新建**
- `backend/app/services/agent/skills/enforcement.py` - **需新建**

**Workflow Registry**:
- `backend/scripts/build_skill_registry.py` - **文档提到但实际不存在**
- ⚠️ **关键问题**：需先确认是否实现 workflow registry，或调整文档移除此依赖

**工具门禁**:
- `BaseAgent.execute_tool(...)` - **无 skill load guard**
- `ReportAgent._execute_tool()` - **私有路径未统一**

**ReAct 解析器** (`react_parser.py`):
- **现状**：只解析 `Thought / Action / Action Input / Final Answer`
- **需扩展**：支持 `<skill_selection>` 解析

### 前端现状

**本地静态 Catalog**:
- `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts` - 定义 `SKILL_TOOLS_CATALOG`
- 被 `SkillToolsPanel.tsx` 和 `ScanConfigExternalToolDetail.tsx` 使用
- **需迁移**：改为从后端 unified API 获取

**Skill 相关组件**:
- `SkillToolsPanel` - 展示 scan-core 工具
- `PromptSkillsPanel` - 管理 prompt skills
- `ScanConfigExternalToolDetail` - 工具详情页
- `useSkillTestStream.ts` - skill 测试流处理
- **需适配**：新的 unified skill API 响应格式

### 现有 Runtime Prompt 行为

- 当前 runtime prompt 仍带入 `skills.md` 与 `shared.md` 的摘要内容
- prompt skill 按 `agent_key` 自动拼接，非统一选择机制
- **需实现**：`build_runtime_messages()` 和 prompt-safe memory loader

## 总体设计

### 核心协议

统一 skill runtime 采用两步式协议：

1. 宿主调用 `/skills/catalog`，向模型注入 summary-only skill digest。
2. 模型输出结构化 `skill_selection`，只包含一个 `skill_id`。
3. 宿主调用 `/skills/{skill_id}` 获取标准化 detail 文档。
4. 宿主把 detail 注入上下文，并把该 skill 标记为已加载。
5. 模型随后才能使用该 skill 对应的流程文档或工具能力。

### 单选协议

模型输出格式固定为：

```xml
<skill_selection>
{"skill_id":"search_code"}
</skill_selection>
```

宿主只接受 `skill_id`，不依赖自然语言技能名解析。

若单轮回复中同时出现以下任一组合，宿主一律视为协议错误，不执行工具，也不接受最终答案：

- `skill_selection` + `Action`
- `skill_selection` + `Final Answer`
- 多个 `skill_selection`

## Skill 分类与统一 ID 规则

### 1. tool skill

- 来源：`scan-core`
- `kind=tool`
- 使用 bare `skill_id`
- 示例：`search_code`、`dataflow_analysis`

### 2. workflow skill

- 来源：registry manifest + mirrored skill dir
- `kind=workflow`
- 使用 namespaced `skill_id`
- 示例：`using-superpowers@agents`

### 3. prompt skill

- 来源：builtin prompt skill + custom prompt skill 的 effective projection
- `kind=prompt`
- 不按每条 DB row 暴露，而是按 `agent_key` 暴露 effective 视图
- 固定 `skill_id`：`prompt-<agent_key>@effective`
- 示例：`prompt-analysis@effective`

## 数据源与所有权

### 数据源优先级

统一 skill catalog 固定由三类数据源合并：

1. `scan_core`
2. `registry_manifest`
3. `prompt_effective`

优先级与规则如下：

1. `registry_manifest` 决定 workflow skill 的 canonical `skill_id`、`namespace`、`entrypoint`、`aliases`
2. `scan_core` 决定工具型 skill 的 canonical 元数据
3. `prompt_effective` 负责生成 prompt skill 的 effective 视图
4. `skills.md` 与 `shared.md` 只保留 memory/debug 价值，不再作为 canonical source
5. `docs/agent-tools` 本轮不参与 canonical 字段覆盖，不允许改写 `skill_id`、`namespace`、`entrypoint`

### build-time 与 runtime 分工

- workflow registry：
  - 正式环境默认使用“预生成 registry”
  - 开发/管理环境才允许“启动期重新构建 registry”
- prompt-effective：
  - 只能在 DB ready 后按用户/任务实时计算
  - 不能写入启动前静态 registry

## 部署与发布契约

### 环境变量与路径

本计划落地时必须显式新增并使用以下配置：

- `SKILL_REGISTRY_ENABLED: bool`
- `SKILL_REGISTRY_ROOT: str`
- `SKILL_SOURCE_ROOTS: list[str]`
- `SKILL_REGISTRY_MODE: "prebuilt_only" | "startup_build"`
- `SKILL_REGISTRY_REQUIRED: bool`
- `CODEX_HOME: str`

这些配置必须同步落到以下入口：

- `backend/app/core/config.py`
- `backend/.env` 与发布环境变量模板
- `docker-compose.yml`
- `docker-compose.full.yml`
- release / deploy 脚本

固定运行时目录约束：

- registry root 默认：`/app/data/runtime/skill-registry`
- codex-home 默认：`/app/data/runtime/codex-home`
- runtime loader 只允许按 `registry_root + mirror_dir/entrypoint` 解析文件
- 禁止 runtime 依赖 `source_root` / `source_dir` / `source_skill_md`

### 正式环境默认策略

正式部署默认采用以下唯一策略：

1. workflow registry 作为预生成发布产物随版本发布
2. `SKILL_REGISTRY_MODE="prebuilt_only"`
3. `CODEX_SKILLS_AUTO_INSTALL=false`
4. `SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP=false`
5. 如 registry 不存在或无效，readiness 失败，不进入“静默继续”
6. 正式发布只能消费以下其中一种受支持产物：
   - 预构建镜像 + 预生成 `skill-registry` 快照
   - 固定镜像摘要 + 固定版本的 `skill-registry` / `codex-home` 快照
7. 正式部署禁止 `docker compose ... up -d --build`
8. 正式部署禁止依赖目标机 `SKILL_SOURCE_ROOTS`

### 开发态默认策略

开发 compose 默认采用：

1. `SKILL_REGISTRY_REQUIRED=false`
2. 未提供 registry 时自动降级为 `scan-core only`
3. prompt-effective 仍按用户/任务实时计算
4. workflow runtime 不作为默认开发验收能力

### liveness / readiness 语义

- `liveness`：仅表示进程存活
- `readiness`：必须覆盖
  - DB migration 已完成
  - registry 模式校验通过
  - registry 完整性满足当前部署模式要求
  - 若发生降级，降级状态必须对 readiness 可见

正式环境约束：

- registry 异常时，entrypoint 必须非零退出或 readiness fail-close
- 不允许“`/health` 返回 ok，但 registry 已失效且系统静默降级”
- `GET /health` 只作为 liveness
- 必须新增或复用独立 readiness path，例如 `GET /ready`

### registry 发布与降级规则

发布新 registry 前必须校验：

- `source_roots` 非空
- 必需 namespace 存在
- skill 数量达到最小阈值
- `manifest.json`、`aliases.json`、mirrored `skills/` 完整

校验失败时必须：

- 保留旧 registry
- 不得覆盖为新的空 manifest
- 明确返回 reason code，而不是静默降级为“成功但无 skill”

稳定失败原因至少包括：

- `registry_manifest_missing`
- `registry_aliases_missing`
- `registry_mirror_missing`
- `registry_skill_md_missing`
- `alias_ambiguous`
- `registry_not_built`
- `registry_invalid`

### 升级 / 回滚 / 持久化卷策略

本计划默认把 `/app/data/runtime` 视为版本化持久化目录，必须补齐：

- registry schema/version 校验
- codex-home skill snapshot 版本戳
- 升级策略：保留卷直接复用、强制重建、自动迁移三者选一
- 回滚策略：是否清理 `skill-registry` 与 `codex-home/skills`

本轮默认选择：

- release 升级时执行 registry version 校验，不匹配则强制重建或回滚失败
- 回滚时必须清理新版本 registry，再恢复旧版本预生成 registry
- last-known-good registry 必须有独立目录，不允许在原目录上原地覆盖后再尝试回退

### 文档冲突优先级

注意：MCP 相关命名已全部重命名为中性的 tool_runtime 命名。原 mcp/ 目录已重命名为 tool_runtime/，所有相关类和方法都已更新。

## Runtime 状态模型

### 设计结论

不能把所有 loaded state 放到单一“任务级全局 session”里，否则会和当前并行 worker 模型冲突。

### 两层状态

#### 1. TaskHostSkillCache

任务级、只读缓存，供 orchestrator 和 worker 共享：

- `catalog_digest`
- `catalog_entries_by_id`
- `detail_cache_by_skill_id`

职责：

- 缓存 catalog / detail
- 不承载 loaded-state
- 可被 worker 复制为只读视图
- 由 task runtime context 持有，创建于 `agent_tasks_execution.py`
- `detail_cache_by_skill_id` 存储不可变快照；worker 只能读取，不能回写共享对象

#### 2. AgentOrWorkerSkillSession

agent / worker 级 runtime state：

- `session_id`
- `loaded_skill_ids`
- `active_workflow_skill_id`
- `active_prompt_skill_by_agent_key`
- `last_protocol_error`

职责：

- 记录当前 agent/worker 已加载的 skill
- 记录当前 agent 可见的 active prompt/workflow state
- 不和其他 worker 共享 loaded-state
- 绑定到单个 agent 实例或单个 worker runtime bootstrap
- worker 启动时由宿主显式注入初始 active state，不允许隐式继承其他 worker 的运行时状态

### 显式删除的模糊状态

本轮删除原文中的 `active_skill_ids`，因为它没有明确是任务级、agent 级还是 worker 级。

替代字段固定为：

- `active_workflow_skill_id`
- `active_prompt_skill_by_agent_key`

### worker spawn 规则

- worker 默认继承 task-level `TaskHostSkillCache`
- worker 不继承其他 worker 的 `loaded_skill_ids`
- worker 只允许继承自身启动时宿主明确下发的 active workflow / prompt state

## Runtime Session 最小实现

### 需要新增的最小模块

- `backend/app/services/agent/runtime/session.py`
- `backend/app/services/agent/runtime/state.py`
- `backend/app/services/agent/runtime/message_builder.py`

### 最小方法集

#### TaskHostSkillCache

- `get_catalog_entry(skill_id: str) -> dict | None`
- `get_cached_detail(skill_id: str) -> dict | None`
- `cache_detail(skill_id: str, detail: dict) -> None`
- `snapshot_for_worker() -> dict`

#### AgentOrWorkerSkillSession

- `is_skill_loaded(skill_id: str) -> bool`
- `mark_skill_loaded(skill_id: str, detail: dict) -> None`
- `get_active_workflow_skill_id() -> str | None`
- `set_active_workflow_skill(skill_id: str | None) -> None`
- `get_active_prompt_skill(agent_key: str) -> dict | None`
- `set_active_prompt_skill(agent_key: str, detail: dict | None) -> None`
- `record_protocol_error(error_code: str, detail: str) -> None`

## 统一 resolver / loader 契约

### 统一服务

新增：

- `backend/app/services/agent/skills/catalog.py`
- `backend/app/services/agent/skills/loader.py`
- `backend/app/services/agent/skills/registry_source.py`
- `backend/app/services/agent/skills/enforcement.py`

### 必须显式定义的接口

- `build_unified_catalog(*, db, user_id, namespace, q, limit, offset) -> UnifiedSkillCatalogResponse`
- `load_unified_skill_detail(*, db, user_id, skill_id, include_workflow) -> UnifiedSkillDetail`
- `load_registry_snapshot(settings) -> RegistrySnapshot`
- `build_prompt_effective_detail(*, db, user_id, agent_key) -> UnifiedSkillDetail`

### 失败语义

上述接口必须返回稳定 reason code，不能用自由文本代替 machine-readable 状态。

### 结构体硬约束

#### UnifiedSkillCatalogResponse

- `enabled: bool`
- `total: int`
- `limit: int`
- `offset: int`
- `items: list[UnifiedSkillCatalogEntry]`
- `error: str | null`

#### UnifiedSkillCatalogEntry

- `skill_id: str`
- `name: str`
- `display_name: str`
- `kind: "tool" | "workflow" | "prompt"`
- `namespace: str`
- `source: "scan_core" | "registry_manifest" | "prompt_effective"`
- `summary: str`
- `selection_label: str`
- `entrypoint: str`
- `runtime_ready: bool`
- `reason: str`
- `load_mode: "summary_only"`
- `deferred_tools: list[str]`
- `aliases: list[str]`
- `has_scripts: bool`
- `has_bin: bool`
- `has_assets: bool`

#### UnifiedSkillDetail

- 继承 catalog 公共字段
- `when_to_use: list[str]`
- `how_to_apply: list[str]`
- `constraints: list[str]`
- `resources: list[ResourceRef]`
- `resource_refs: list[ResourceRef]`
- `prompt_sources: list[PromptSourceRef]`
- `input_constraints: list[str]`
- `usage_examples: list[str]`
- `raw_content: str | null`
- `effective_content: str | null`

#### RegistrySnapshot

- `registry_root: str`
- `manifest_path: str`
- `aliases_path: str`
- `skills_dir: str`
- `generated_at: str | null`
- `schema_version: str | null`
- `skills: list[dict]`
- `aliases: dict[str, list[str]]`
- `reason: str | null`

#### GuardDecision

- `allowed: bool`
- `error_code: str | null`
- `required_skill_id: str | null`
- `caller: str`
- `message: str`

#### UnifiedSkillAvailabilityItem

- `enabled: bool`
- `startup_ready: bool`
- `runtime_ready: bool`
- `reason: str`
- `source: "scan_core" | "registry_manifest" | "prompt_effective"`
- `kind: "tool" | "workflow" | "prompt"`
- `load_mode: "summary_only" | "detail_loaded" | "load_failed"`

#### ResourceRef

- `type: str`
- `path: str`
- `label: str`
- `optional: bool`

#### PromptSourceRef

- `source_type: "builtin" | "custom_global" | "custom_agent"`
- `label: str`
- `active: bool`

#### 默认值

- `deferred_tools/resources/resource_refs/prompt_sources/input_constraints/usage_examples` 默认为空数组
- 所有可选文本字段默认 `null`，不允许用缺字段表达
- `reason` 必须总是返回稳定枚举值，不允许为空字符串

## 公共接口设计

### GET /skills/catalog

保留查询参数：

- `q`
- `namespace`
- `limit`
- `offset`

### Unified catalog 公共字段

- `skill_id`
- `name`
- `display_name`
- `kind`
- `namespace`
- `source`
- `summary`
- `selection_label`
- `entrypoint`
- `runtime_ready`
- `reason`
- `load_mode`
- `deferred_tools`
- `aliases`
- `has_scripts`
- `has_bin`
- `has_assets`

### scan-core 展示字段

为去掉前端本地静态 catalog 依赖，`namespace=scan-core` 的 catalog/detail 必须稳定返回：

- `display_type`
- `category`
- `goal`
- `task_list`
- `input_checklist`
- `example_input`
- `pitfalls`
- `sample_prompts`
- `phase_bindings`
- `mode_bindings`
- `evidence_view_support`
- `evidence_render_type`
- `legacy_visible`

这些字段在 `namespace=scan-core` 时的默认值固定为：

- `display_type`: `"PROMPT" | "CLI"`
- `category`: 非空字符串
- `goal`: 非空字符串
- `task_list`: `list[str]`，默认 `[]`
- `input_checklist`: `list[str]`，默认 `[]`
- `example_input`: 字符串，默认 `""`
- `pitfalls`: `list[str]`，默认 `[]`
- `sample_prompts`: `list[str]`，默认 `[]`
- `phase_bindings`: `list[str]`，默认 `[]`
- `mode_bindings`: `list[str]`，默认 `[]`
- `evidence_view_support`: `bool`
- `evidence_render_type`: `str | null`
- `legacy_visible`: `bool`

结论：

- 本计划包含“从后端提供 scan-core 展示 metadata”
- 不允许实现后继续默认依赖前端本地 `SKILL_TOOLS_CATALOG`
- `display_type` 在前端迁移完成后成为唯一真相源，不再允许前端用 `has_scripts/has_bin` + 本地硬编码推断

### GET /skills/{skill_id}

detail 返回标准化 usage 文档，但必须保留旧客户端仍在消费的字段。

### detail 公共字段

- `skill_id`
- `name`
- `display_name`
- `kind`
- `namespace`
- `source`
- `summary`
- `entrypoint`
- `runtime_ready`
- `reason`
- `load_mode`
- `when_to_use`
- `how_to_apply`
- `constraints`
- `deferred_tools`
- `resources`

### 按类型补充字段

- workflow skill：
  - `resource_refs`
  - `raw_content`
- prompt skill：
  - `agent_key`
  - `prompt_sources`
  - `effective_content`
- tool skill：
  - `input_constraints`
  - `usage_examples`
  - 当前 test metadata
  - scan-core 展示字段

### 旧 detail 字段兼容矩阵

以下旧字段必须继续返回：

- `enabled`
- `mirror_dir`
- `source_root`
- `source_dir`
- `source_skill_md`
- `aliases`
- `has_scripts`
- `has_bin`
- `has_assets`
- `files_count`
- `workflow_content`
- `workflow_truncated`
- `workflow_error`
- `test_supported`
- `test_mode`
- `test_reason`
- `default_test_project_name`
- `tool_test_preset`

默认值规则：

- workflow skill：
  - `enabled=true`
  - `aliases` 来自 registry manifest
  - `has_scripts/has_bin/has_assets/files_count` 来自 mirror 实际内容
  - `workflow_content` 仅在 `include_workflow=true` 时返回
  - `workflow_truncated=false`
  - `workflow_error=null`
  - `test_supported=false`
  - `test_mode="disabled"`
  - `test_reason=null`
  - `default_test_project_name="libplist"`
  - `tool_test_preset=null`
- prompt skill：
  - `enabled=true`
  - `mirror_dir=""`
  - `source_root=""`
  - `source_dir=""`
  - `source_skill_md=""`
  - `aliases=[]`
  - `has_scripts=false`
  - `has_bin=false`
  - `has_assets=false`
  - `files_count=0`
  - `workflow_content=null`
  - `workflow_truncated=false`
  - `workflow_error=null`
  - `test_supported=false`
  - `test_mode="disabled"`
  - `test_reason=null`
  - `default_test_project_name="libplist"`
  - `tool_test_preset=null`
- tool skill：
  - `enabled=true`
  - `mirror_dir=""`
  - `source_root=""`
  - `source_dir=""`
  - `source_skill_md=""`
  - `aliases=[]`
  - `has_scripts=false`
  - `has_bin=false`
  - `has_assets=false`
  - `files_count=0`
  - `workflow_content=null`
  - `workflow_truncated=false`
  - `workflow_error="scan_core_static_catalog"`
  - 其余 test metadata 保持 scan-core 当前兼容语义

### test metadata 闭集

在前端类型放宽前，以下值不允许扩展：

- `test_mode`: `"single_skill_strict" | "structured_tool" | "disabled"`
- `default_test_project_name`: `"libplist"`
- `tool_test_preset.project_name`: `"libplist"`

### /skills/{id}/test 与 /skills/{id}/tool-test

本轮明确约束：

- 仅 `kind=tool` 支持
- `kind=workflow` / `kind=prompt` 请求命中时返回 `409`
- 错误码固定为：
  - `unsupported_skill_kind`
  - `skill_not_runnable`
  - `skill_not_found`

`runtime_ready=false` 的 tool skill 不允许测试，返回 `409 skill_not_runnable`。

### 流式事件与结果载荷契约

`/skills/{id}/test` 与 `/skills/{id}/tool-test` 的 SSE envelope 本轮继续保持现有结构，并明确固定为：

- 通用 envelope：
  - `type: str`
  - `message: str | null`
  - `tool_name: str | null`
  - `tool_input: object | null`
  - `tool_output: object | str | null`
  - `metadata: object | null`
  - `data: object | null`

- 允许的 `event.type` 至少包括：
  - `llm_thought`
  - `llm_action`
  - `tool_call`
  - `tool_result`
  - `project_cleanup`
  - `result`
  - `error`

- `result.data` 必须继续兼容当前 `SkillTestResult`
- `project_cleanup.metadata` 必须继续包含：
  - `temp_dir`
  - `cleanup_success`

- tool evidence metadata key 集合至少继续兼容：
  - `render_type`
  - `display_command`
  - `command_chain`
  - `entries`

## /config 兼容策略

### 保留旧字段

保留原有：

- `skillAvailability`

旧字段继续保持 scan-core-only 兼容语义，避免破坏旧客户端和现有测试。

### 新增统一字段

新增：

- `unifiedSkillAvailability`

该字段使用 canonical `skill_id` 作为 key，覆盖：

- tool
- workflow
- prompt-effective

每个条目至少包含：

- `enabled`
- `startup_ready`
- `runtime_ready`
- `reason`
- `source`
- `kind`

`reason` 枚举闭集至少包括：

- `ready`
- `no_active_prompt_sources`
- `registry_not_built`
- `registry_manifest_missing`
- `registry_aliases_missing`
- `registry_mirror_missing`
- `registry_invalid`
- `disabled_by_mode`

### 结论

- 旧客户端继续读 `skillAvailability`
- 新 runtime / 新前端读 `unifiedSkillAvailability`
- 不允许本轮直接把旧字段 silent flip 为 unified keyspace

## Prompt-effective 设计

### 数据来源

每个 `agent_key` 暴露一个 effective prompt skill：

- `prompt-recon@effective`
- `prompt-business_logic_recon@effective`
- `prompt-analysis@effective`
- `prompt-business_logic_analysis@effective`
- `prompt-verification@effective`

合成顺序固定：

1. builtin template
2. global custom prompt skill
3. agent-specific custom prompt skill

### 解析前提

prompt-effective 必须通过 `db + user_id` 解析，不能被当作纯静态 registry source。

### 非五个 prompt-agent 的边界

- `ReportAgent` 在 v1 接入统一 message builder，但不分配 prompt-effective
- 其他不在五个 `agent_key` 闭集内的 agent 也不分配 prompt-effective
- `markdown_memory` 的 `report.md` / 其他 memory key 不因为本计划扩展新的 prompt-effective keyspace

### 空来源行为

当某个 effective prompt skill 没有任何 active source 时：

- `/skills/catalog` 仍返回该 skill
- `runtime_ready=false`
- `reason="no_active_prompt_sources"`
- `/skills/{id}` 仍可查询，但 `effective_content=""`
- 不能被激活到 runtime preamble

### use_prompt_skills 兼容语义

`AgentTaskCreate.use_prompt_skills` 继续保留请求兼容，但语义固定为：

- v1：仅用于兼容旧任务 payload / 旧 UI
- 不再决定 prompt-effective 是否进入 unified catalog
- 在旧注入路径完全删除前，可作为 legacy prompt injection 开关
- 当旧注入路径删除后，该字段被忽略但继续接受

不得出现“有时控制 catalog，有时控制 prompt 注入”的混合语义。

额外约束：

- 旧请求继续允许发送 `use_prompt_skills=true`
- 旧字段被忽略时，不允许 silent behavior flip；必须产生稳定日志或 telemetry 标记
- 兼容期结束前，不移除该字段的请求 schema

### PromptSkillsPanel 边界

- `/skills/prompt-skills*` 继续作为 CRUD/builtin toggle 管理 API
- `prompt-<agent_key>@effective` 只读，不可编辑
- v1 的 `agent_key` 闭集固定就是当前五个值
- `PromptSkillsPanel` 在前端迁移前继续消费旧管理 API，不切到 unified skill detail

## 统一 prompt 注入与 memory 迁移

### 结论

不能只在 `BaseAgent.stream_llm_call()` 前临时加 preamble，因为 `ReportAgent` 还有独立 LLM 路径，且多个 agent 仍在手工拼接 `skills.md` / `shared.md` / `Prompt Skill`。

### 新增统一入口

新增：

- `build_runtime_messages(agent_key, conversation_history, session_view, prompt_safe_memory) -> list[dict]`

该入口同时服务：

- `BaseAgent.stream_llm_call()`
- `ReportAgent._call_llm()`

### 必删旧路径

以下行为必须从 agent 初始消息中删除：

- `skills.md（规范摘要）` 整段拼接
- `shared.md（节选）` 工具目录大段拼接
- `## Prompt Skill（agent_key）` 手工拼接块

涉及文件至少包括：

- `recon.py`
- `analysis.py`
- `orchestrator.py`
- `verification.py`
- `business_logic_recon.py`
- `business_logic_analysis.py`
- `report.py`

### prompt-safe memory loader

必须新增 prompt-safe memory 读取路径，满足：

- 不再把 `skills.md` 头部当默认技能来源
- 不再把 `shared.md` 中 `tool_catalog_sync` 大段正文整段搬进 prompt
- `skills.md` / `shared.md` 继续保留给 debug、排障、历史回放

### 旧 runtime input contract

在旧注入路径删除前：

- `config.prompt_skills` 与 `config.markdown_memory` 仍可保留在输入 contract 中
- 但只能二选一：
  - legacy path 生效，new builder 关闭
  - new builder 生效，legacy path 完全忽略

不允许双注入并存。

## skill_selection 解析与 turn 处理

### 统一解析位置

`skill_selection` 必须在共享 ReAct 解析器 `react_parser.py` 中统一解析。

`ParsedReactResponse` 新增：

- `selected_skill_id: str | None`
- `protocol_error_code: str | None`
- `protocol_error_detail: str | None`

### 接入范围

所有直接或间接调用 `parse_react_response()` 的路径都必须迁移，至少覆盖：

- orchestrator
- recon
- analysis
- verification
- report
- business_logic_recon
- business_logic_analysis
- business_logic_scan
- skill_test

若无法逐个迁移，则必须引入统一 BaseAgent turn-handler 收敛。

## 系统 Prompt 合同

### 结论

agent-specific system prompt 与 `TOOL_USAGE_GUIDE` 继续保留领域指导作用，但不再作为 skill discovery / skill loading / tool gating 的真相源。

### 明确要求

- 新协议落地同轮，必须同步更新：
  - `VERIFICATION_SYSTEM_PROMPT`
  - 其他 agent system prompts
  - `TOOL_USAGE_GUIDE`
  - 对应 prompt contract 测试

- 若系统 prompt 中仍保留工具使用示例，只能表达领域策略，不能与 unified runtime protocol 冲突。

## 工具门禁与统一 enforcement contract

### 设计结论

不能再写成“把硬门禁挂在 `BaseAgent.execute_tool()` 就全覆盖”，因为 `ReportAgent` 有私有工具路径，复合工具也可能二次调度。

### 新增统一守卫

新增：

- `SkillEnforcementGuard.check_tool_access(resolved_tool_name, caller, session_view) -> GuardDecision`

必须接入的调用点：

- `BaseAgent.execute_tool()`
- `ReportAgent._execute_tool()`
- 所有复合工具内部二次调度点

### scan-core 硬门禁

执行顺序固定为：

1. 先做 alias / virtual tool 归一化
2. 得到 canonical `resolved_tool_name`
3. 若其属于 scan-core canonical skill，则进入 guard
4. 若当前 agent/worker session 未加载该 skill，则拒绝执行

稳定错误元信息至少包含：

- `error_code="skill_not_loaded"`
- `required_skill_id=<canonical skill id>`
- `caller=<agent or internal>`

### 复合工具规则

对 `verify_reachability` 这类复合工具，必须明确二选一：

1. 作为 host/internal-only tool，对模型不可见，内部调用可带 `caller=internal_host` 豁免
2. 作为可见 tool，对其内部依赖的 scan-core skill 做前置校验

本轮默认采用方案 1：host/internal-only，不纳入 unified skill catalog。

### model-visible / host-internal 分类

必须新增一份权威分类表：

- `model_visible_tool_skill_ids`
- `host_internal_tool_names`

所有 guard、parser、tool routing、测试均以这份表为准，避免 virtual tool / 递归执行路径出现误拦或漏拦。

## 前端兼容与展示迁移

### 兼容目标

本轮不仅要保证 API 不崩，还要消除“前端自己适配”前提。

### 必须覆盖的前端消费面

- `SkillToolsPanel`
- `externalToolsViewModel`
- `ScanConfigExternalToolDetail`
- `PromptSkillsPanel`
- skill test 页面
- 创建任务相关对话框中 `use_prompt_skills` 请求兼容

### 明确要求

- 对 `namespace=scan-core`，后端必须直接提供前端展示 metadata
- prompt-effective catalog/detail 必须返回：
  - `agent_key`
  - `display_name`
- 前端不得通过解析 `prompt-analysis@effective` 自行猜测 agent 归属
- 在满足以下条件前，不得删除前端 `SKILL_TOOLS_CATALOG` fallback：
  - 后端已返回完整 scan-core 展示字段
  - `display_type` 已成为唯一真相源
  - 列表/详情/视图模型相关前端测试已改为以后端字段断言

### 错误体契约

以下接口在失败时必须统一返回 JSON：

- `GET /skills/{id}`
- `POST /skills/{id}/test`
- `POST /skills/{id}/tool-test`

结构固定为：

- `error_code: str`
- `detail: str`
- `skill_id: str | null`
- `kind: str | null`

状态码矩阵至少包括：

- `404 skill_not_found`
- `409 unsupported_skill_kind`
- `409 skill_not_runnable`
- `409 skill_not_loaded`
- `400 invalid_structured_test_payload`

## 实施路线图与代码示例

### 前置决策：Workflow Registry 策略

⚠️ **关键问题**：文档多处提到 `backend/scripts/build_skill_registry.py`，但该文件**实际不存在**。

**两种处理方案**：

1. **方案 A（推荐）**：Phase 1 暂不实现 workflow skill registry
   - 专注于 scan-core 和 prompt-effective 的统一
   - 将 workflow registry 作为独立后续任务
   - 修改本文档，移除对 `build_skill_registry.py` 的强依赖

2. **方案 B**：先实现 workflow registry
   - 参考已有的 scanner runner 模式
   - 实现 `build_skill_registry.py` 脚本
   - 定义 manifest.json / aliases.json 格式
   - 但会显著增加 Phase 1 工作量

**建议**：采用方案 A，Phase 1 实现 "scan-core + prompt-effective" unified runtime，workflow registry 作为 Phase 2。

---

### 迁移顺序（调整版）

### Phase A：配置与基础设施准备

**1. 扩展配置项** (`backend/app/core/config.py`):

```python
# 在 Settings 类中添加（参考现有 TOOL_RUNTIME_ 配置模式）
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Skill Registry 配置（Phase 1 可选）
    SKILL_REGISTRY_ENABLED: bool = False  # Phase 1 默认关闭
    SKILL_REGISTRY_ROOT: str = "/app/data/runtime/skill-registry"
    SKILL_REGISTRY_MODE: Literal["prebuilt_only", "startup_build"] = "prebuilt_only"
    SKILL_REGISTRY_REQUIRED: bool = False
    CODEX_HOME: str = "/app/data/runtime/codex-home"

    # Skill Runtime 配置
    SKILL_RUNTIME_ENABLED: bool = True
    SKILL_RUNTIME_STRICT_MODE: bool = False  # Phase 1 宽松模式
    SKILL_LOAD_GUARD_ENABLED: bool = True
```

**2. 创建 Runtime 目录结构** (`backend/app/services/agent/runtime/`):

```bash
mkdir -p backend/app/services/agent/runtime
touch backend/app/services/agent/runtime/__init__.py
touch backend/app/services/agent/runtime/session.py
touch backend/app/services/agent/runtime/state.py
touch backend/app/services/agent/runtime/message_builder.py
```

**3. 创建 Skills 服务目录** (`backend/app/services/agent/skills/`):

```bash
# 目录已存在，新增文件
touch backend/app/services/agent/skills/catalog.py
touch backend/app/services/agent/skills/loader.py
touch backend/app/services/agent/skills/enforcement.py
# registry_source.py 在 Phase 1 可选
```

### Phase B：实现 Runtime State

**4. 实现 `TaskHostSkillCache`** (`runtime/state.py`):

```python
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

@dataclass
class TaskHostSkillCache:
    """任务级只读技能缓存，供 orchestrator 和 worker 共享"""

    catalog_digest: str = ""
    catalog_entries_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    detail_cache_by_skill_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_catalog_entry(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self.catalog_entries_by_id.get(skill_id)

    def get_cached_detail(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self.detail_cache_by_skill_id.get(skill_id)

    def cache_detail(self, skill_id: str, detail: Dict[str, Any]) -> None:
        # 只读快照，不可变
        self.detail_cache_by_skill_id[skill_id] = detail.copy()

    def snapshot_for_worker(self) -> Dict[str, Any]:
        """为 worker 创建只读快照"""
        return {
            "catalog_digest": self.catalog_digest,
            "catalog_entries": dict(self.catalog_entries_by_id),
            "detail_cache": dict(self.detail_cache_by_skill_id),
        }
```

**5. 实现 `AgentOrWorkerSkillSession`** (`runtime/session.py`):

```python
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

@dataclass
class AgentOrWorkerSkillSession:
    """Agent/Worker 级 runtime state"""

    session_id: str
    loaded_skill_ids: Set[str] = field(default_factory=set)
    active_workflow_skill_id: Optional[str] = None
    active_prompt_skill_by_agent_key: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_protocol_error: Optional[str] = None

    def is_skill_loaded(self, skill_id: str) -> bool:
        return skill_id in self.loaded_skill_ids

    def mark_skill_loaded(self, skill_id: str, detail: Dict[str, Any]) -> None:
        self.loaded_skill_ids.add(skill_id)

    def get_active_workflow_skill_id(self) -> Optional[str]:
        return self.active_workflow_skill_id

    def set_active_workflow_skill(self, skill_id: Optional[str]) -> None:
        self.active_workflow_skill_id = skill_id

    def get_active_prompt_skill(self, agent_key: str) -> Optional[Dict[str, Any]]:
        return self.active_prompt_skill_by_agent_key.get(agent_key)

    def set_active_prompt_skill(self, agent_key: str, detail: Optional[Dict[str, Any]]) -> None:
        if detail is None:
            self.active_prompt_skill_by_agent_key.pop(agent_key, None)
        else:
            self.active_prompt_skill_by_agent_key[agent_key] = detail

    def record_protocol_error(self, error_code: str, detail: str) -> None:
        self.last_protocol_error = f"{error_code}: {detail}"
```

### Phase C：实现 Unified Catalog（Scan-Core + Prompt）

**6. 实现 Catalog Builder** (`skills/catalog.py`):

参考现有 `skills.py` 中的实现，重构为统一服务：

```python
from typing import List, Optional
from app.services.agent.skills.scan_core import search_scan_core_skills, SCAN_CORE_SKILL_IDS
from app.services.agent.skills.prompt_skills import PROMPT_SKILL_AGENT_KEYS

async def build_unified_catalog(
    *,
    db,
    user_id: Optional[int] = None,
    namespace: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """构建统一 skill catalog（Phase 1: scan-core + prompt-effective）"""

    items = []

    # 1. Scan-Core Skills
    if namespace is None or namespace == "scan-core":
        scan_core_items = search_scan_core_skills(q=q, limit=limit, offset=offset)
        for item in scan_core_items:
            items.append({
                "skill_id": item["skill_id"],
                "name": item["name"],
                "display_name": item.get("display_name", item["name"]),
                "kind": "tool",
                "namespace": "scan-core",
                "source": "scan_core",
                "summary": item["summary"],
                "selection_label": f"[scan-core] {item['name']}",
                "entrypoint": item["skill_id"],
                "runtime_ready": True,
                "reason": "ready",
                "load_mode": "summary_only",
                # ... 其他字段
            })

    # 2. Prompt-Effective Skills (需数据库)
    if (namespace is None or namespace == "prompt") and db is not None and user_id is not None:
        from app.services.agent.skills.prompt_skills import build_effective_prompt_skill_for_agent

        for agent_key in PROMPT_SKILL_AGENT_KEYS:
            effective_detail = await build_effective_prompt_skill_for_agent(
                db=db, user_id=user_id, agent_key=agent_key
            )

            skill_id = f"prompt-{agent_key}@effective"
            items.append({
                "skill_id": skill_id,
                "name": skill_id,
                "display_name": f"Prompt Strategy - {agent_key.replace('_', ' ').title()}",
                "kind": "prompt",
                "namespace": "prompt",
                "source": "prompt_effective",
                "summary": f"Effective prompt skill for {agent_key} agent",
                "selection_label": f"[prompt] {agent_key}",
                "entrypoint": skill_id,
                "runtime_ready": effective_detail.get("has_content", False),
                "reason": "ready" if effective_detail.get("has_content") else "no_active_prompt_sources",
                "load_mode": "summary_only",
            })

    # 3. Workflow Skills (Phase 1 跳过)
    # TODO: Phase 2 实现

    return {
        "enabled": True,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "items": items,
        "error": None,
    }
```

**7. 实现 Detail Loader** (`skills/loader.py`):

```python
async def load_unified_skill_detail(
    *,
    db,
    user_id: Optional[int],
    skill_id: str,
    include_workflow: bool = False,
) -> Dict[str, Any]:
    """加载统一 skill detail"""

    # 1. Scan-Core
    if skill_id in SCAN_CORE_SKILL_IDS:
        from app.services.agent.skills.scan_core import get_scan_core_skill_detail
        detail = get_scan_core_skill_detail(skill_id)
        # 补充展示字段
        detail["kind"] = "tool"
        detail["namespace"] = "scan-core"
        detail["source"] = "scan_core"
        # ... 添加 display_type, category, goal等
        return detail

    # 2. Prompt-Effective
    if skill_id.startswith("prompt-") and skill_id.endswith("@effective"):
        agent_key = skill_id.replace("prompt-", "").replace("@effective", "")
        if agent_key in PROMPT_SKILL_AGENT_KEYS:
            effective = await build_effective_prompt_skill_for_agent(
                db=db, user_id=user_id, agent_key=agent_key
            )
            return {
                "skill_id": skill_id,
                "agent_key": agent_key,
                "kind": "prompt",
                "namespace": "prompt",
                "source": "prompt_effective",
                "effective_content": effective.get("content", ""),
                "prompt_sources": effective.get("sources", []),
                # ... 其他字段
            }

    # 3. Workflow (Phase 1 不支持)
    raise HTTPException(status_code=404, detail="skill_not_found")
```

### Phase D：实现工具门禁

**8. 实现 SkillEnforcementGuard** (`skills/enforcement.py`):

```python
from dataclasses import dataclass
from typing import Optional
from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS

@dataclass
class GuardDecision:
    allowed: bool
    error_code: Optional[str] = None
    required_skill_id: Optional[str] = None
    caller: str = ""
    message: str = ""

class SkillEnforcementGuard:
    """统一技能门禁"""

    @staticmethod
    def check_tool_access(
        resolved_tool_name: str,
        caller: str,
        session: "AgentOrWorkerSkillSession",
    ) -> GuardDecision:
        """检查工具访问权限"""

        # 1. 非 scan-core 工具，放行
        if resolved_tool_name not in SCAN_CORE_SKILL_IDS:
            return GuardDecision(
                allowed=True,
                caller=caller,
                message=f"Tool {resolved_tool_name} is not gated (non scan-core)"
            )

        # 2. Scan-core 工具，检查是否已加载
        if session.is_skill_loaded(resolved_tool_name):
            return GuardDecision(
                allowed=True,
                caller=caller,
                message=f"Skill {resolved_tool_name} is loaded"
            )

        # 3. 未加载，拒绝访问
        return GuardDecision(
            allowed=False,
            error_code="skill_not_loaded",
            required_skill_id=resolved_tool_name,
            caller=caller,
            message=f"Skill {resolved_tool_name} must be loaded before use. Use <skill_selection> first."
        )
```

### Phase E：扩展 ReAct Parser

**9. 扩展 react_parser.py**:

在现有 `ParsedReactResponse` 中添加字段：

```python
@dataclass
class ParsedReactResponse:
    # 现有字段
    thought: Optional[str] = None
    action: Optional[str] = None
    action_input: Optional[str] = None
    final_answer: Optional[str] = None

    # 新增字段
    selected_skill_id: Optional[str] = None
    protocol_error_code: Optional[str] = None
    protocol_error_detail: Optional[str] = None

def parse_react_response(text: str) -> ParsedReactResponse:
    """解析 ReAct 响应，支持 skill_selection"""

    result = ParsedReactResponse()

    # 现有解析逻辑...

    # 新增：解析 <skill_selection>
    skill_selection_pattern = r'<skill_selection>\s*({[^}]+})\s*</skill_selection>'
    skill_match = re.search(skill_selection_pattern, text, re.DOTALL)

    if skill_match:
        try:
            skill_data = json.loads(skill_match.group(1))
            result.selected_skill_id = skill_data.get("skill_id")

            # 协议检查：skill_selection 不能与 Action/Final Answer 并存
            if result.action or result.final_answer:
                result.protocol_error_code = "mixed_skill_selection_with_action_or_answer"
                result.protocol_error_detail = "skill_selection cannot appear with Action or Final Answer"
        except json.JSONDecodeError:
            result.protocol_error_code = "invalid_skill_selection_json"
            result.protocol_error_detail = "skill_selection must be valid JSON"

    return result
```

### Phase F：API Endpoint 增量更新

**10. 更新 /skills/catalog** (`api/v1/endpoints/skills.py`):

```python
@router.get("/catalog", response_model=SkillCatalogResponse)
async def get_skills_catalog(
    namespace: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取统一 skill catalog（scan-core + prompt-effective）"""

    from app.services.agent.skills.catalog import build_unified_catalog

    result = await build_unified_catalog(
        db=db,
        user_id=current_user.id,
        namespace=namespace,
        q=q,
        limit=limit,
        offset=offset,
    )

    return result
```

**11. 更新 /skills/{skill_id}**:

```python
@router.get("/{skill_id}", response_model=SkillDetailResponse)
async def get_skill_detail(
    skill_id: str,
    include_workflow: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 skill 详情（支持 scan-core 和 prompt-effective）"""

    from app.services.agent.skills.loader import load_unified_skill_detail

    try:
        detail = await load_unified_skill_detail(
            db=db,
            user_id=current_user.id,
            skill_id=skill_id,
            include_workflow=include_workflow,
        )
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "load_failed", "detail": str(e)}
        )
```

### Phase G：前端适配

**12. 前端迁移** (`frontend/src/pages/intelligent-scan/`):

```typescript
// 移除本地 SKILL_TOOLS_CATALOG 依赖
// 改为从 API 获取

import { api } from '@/shared/api';

const useSkillCatalog = () => {
  const [catalog, setCatalog] = useState([]);

  useEffect(() => {
    api.get('/api/v1/skills/catalog', {
      params: { namespace: 'scan-core' }
    }).then(res => {
      setCatalog(res.data.items);
    });
  }, []);

  return catalog;
};
```

### Phase H：测试与验收

**13. 新增测试**:

```bash
# 创建测试文件
touch backend/tests/test_skill_runtime_state.py
touch backend/tests/test_skill_catalog_unified.py
touch backend/tests/test_skill_enforcement.py
touch backend/tests/test_react_parser_skill_selection.py
```

**14. 运行测试**:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_skill_runtime_state.py \
  tests/test_skill_catalog_unified.py \
  tests/test_skill_enforcement.py \
  tests/test_react_parser_skill_selection.py \
  -v
```

## 禁止的半成品

- API 已切 unified，但 agent 仍然整段注入 `skills.md`。
- 只收敛了 `skills.md`，却继续把 `shared.md` 中 `tool_catalog_sync` 的正文整段塞进 prompt。
- `/config.skillAvailability` 被 silent flip 为 unified keyspace。
- `loaded_skill_ids` 仍作为任务级全局状态在并行 worker 间共享。
- 门禁只挂在 `BaseAgent.execute_tool()`，遗漏 `ReportAgent` 和复合工具。
- 只有主线 agent 接入了 `skill_selection`，`business_logic_scan` / `skill_test` 仍走旧解析。
- prompt-effective 被当作启动期静态 registry 产物。
- scan-core 展示字段仍依赖前端本地静态 catalog。
- 旧测试页仍默认 workflow/prompt skill 可调用 `/test` / `/tool-test`。
- 旧 `config.prompt_skills` 与新 runtime message builder 同时生效造成双注入。
- 系统 prompt / `TOOL_USAGE_GUIDE` 仍被当作 skill runtime 真相源。
- 正式发布仍通过源码 + `docker compose up -d --build` 现场构建 workflow registry。
- readiness 仍只检查 `/health` 且 registry 异常继续启动。

## 测试计划

### 接口测试

- `/skills/catalog` 同时返回 tool、workflow、prompt 三类 skill
- `namespace=scan-core` 时返回 scan-core 展示字段
- `/skills/{id}` 返回统一 detail 与完整旧字段兼容矩阵
- `/config.skillAvailability` 保持旧语义
- `/config.unifiedSkillAvailability` 返回统一新视图
- `/skills/{id}` 失败时返回统一错误 JSON

### prompt-effective 测试

- builtin 全开时，五个 effective prompt skill 都可见
- builtin 部分关闭时，对应 effective detail 正确降级
- 仅 global custom 时，所有 agent 的 effective detail 都包含 global custom
- 仅 agent-specific custom 时，只影响对应 `agent_key`
- 无 active source 时，catalog 仍可见但 `runtime_ready=false`
- user-scoped 查询不会串用户数据
- `PromptSkillsPanel` 继续走旧 CRUD API，effective 视图保持只读

### runtime / session / worker 测试

- 任务启动后创建 `TaskHostSkillCache`
- worker 继承只读 catalog/detail cache，不继承其他 worker 的 `loaded_skill_ids`
- `loaded_skill_ids` 只在 agent/worker 级有效
- 重复选择同一 skill 走 host detail cache
- `TaskHostSkillCache` 由 task runtime context 持有，worker 只拿快照

### parser / protocol 测试

- `react_parser.py` 能解析单个 `skill_selection`
- `skill_selection` + `Action` 返回协议错误
- `skill_selection` + `Final Answer` 返回协议错误
- 所有 parser 调用面行为一致
- `test_agent_react_parser_action_precedes_final.py` 在迁移后继续通过

### enforcement 测试

- 未加载 detail 时，scan-core 工具被拒绝
- 已加载 detail 后，scan-core 工具可执行
- `ReportAgent` 私有工具路径也受 guard 控制
- 复合工具不会绕过 guard
- 非 scan-core 内部工具不被误拦截
- `model_visible_tool_skill_ids` / `host_internal_tool_names` 分类表有测试守护

### 前端兼容测试

- `SkillToolsPanel` 不再依赖本地静态 catalog 才能正确展示 scan-core
- `ScanConfigExternalToolDetail` 可消费 unified detail + 旧字段兼容 shape
- `PromptSkillsPanel` 可消费 prompt-effective `display_name/agent_key`
- 任务创建请求继续允许发送 `use_prompt_skills`
- 详情页 skill test SSE 消费无需修改就能继续运行

### 部署 / 发布测试

- 预生成 registry 缺失时，正式环境 readiness 失败
- 开发 compose 缺失 registry 时，系统降级为 `scan-core only`
- 空 source roots 不会覆盖掉旧 registry
- 升级 / 回滚时 registry version 校验生效
- 生产环境禁用从 `main` 自动安装 skill
- 正式发布脚本不再使用 `docker compose ... --build`
- readiness 与 liveness 分离，registry 异常时 readiness fail

### 系统 Prompt 合同测试

- `test_agent_prompt_contracts.py` 与 unified runtime contract 同轮迁移
- 新 contract 明确系统 prompt 不是 skill discovery 真相源
- 迁移完成前，该测试失败视为“提示词合同仍未收口”

## 验收标准

- 模型无法再依靠直接读 skill 文件完成 skill 发现。
- 宿主能够通过 `/skills/catalog -> skill_selection -> /skills/{id}` 完成完整 skill 选择与加载闭环。
- scan-core 门禁覆盖 `BaseAgent`、`ReportAgent` 和复合工具。
- worker 间不共享 loaded-state。
- prompt-effective 只在 DB ready 后按用户实时计算。
- scan-core 页面不再依赖前端本地静态 catalog 才能正确展示。
- 旧 `skillAvailability`、scan-core detail 页、skill test 页不被破坏。
- 正式发布环境不依赖启动时联网拉取 `main` 分支 skill。
- 正式发布环境的产物、registry、readiness、回滚流程均有唯一规定，不再依赖人工约定。

---

## 实施检查清单

### Phase 1: 基础设施（预计 2-3 天）

- [ ] **配置准备**
  - [ ] 在 `backend/app/core/config.py` 添加 `SKILL_REGISTRY_*`, `SKILL_RUNTIME_*` 配置
  - [ ] 更新 `docker/env/backend/.env` 模板
  - [ ] 更新 `docker-compose.yml` 环境变量映射

- [ ] **目录结构**
  - [ ] 创建 `backend/app/services/agent/runtime/` 目录
  - [ ] 创建 `backend/app/services/agent/skills/` 下的新文件
  - [ ] 创建对应的测试目录

### Phase 2: Runtime State（预计 2 天）

- [ ] **实现状态模型**
  - [ ] 实现 `TaskHostSkillCache` （`runtime/state.py`）
  - [ ] 实现 `AgentOrWorkerSkillSession` （`runtime/session.py`）
  - [ ] 编写单元测试（`tests/test_skill_runtime_state.py`）

- [ ] **验证**
  - [ ] 测试 cache 的只读快照机制
  - [ ] 测试 session 的隔离性

### Phase 3: Unified Catalog（预计 3-4 天）

- [ ] **Scan-Core 集成**
  - [ ] 实现 `build_unified_catalog()` 的 scan-core 部分
  - [ ] 补充 scan-core 展示字段到 API 响应
  - [ ] 测试 `/skills/catalog?namespace=scan-core`

- [ ] **Prompt-Effective 集成**
  - [ ] 实现 `build_effective_prompt_skill_for_agent()`
  - [ ] 实现 prompt-effective 的 catalog entry 生成
  - [ ] 测试 user-scoped 查询不串数据

- [ ] **Detail Loader**
  - [ ] 实现 `load_unified_skill_detail()`
  - [ ] 处理 scan-core 和 prompt-effective 两种类型
  - [ ] 保持旧字段兼容矩阵

### Phase 4: 工具门禁（预计 2 天）

- [ ] **实现 Enforcement**
  - [ ] 实现 `SkillEnforcementGuard` （`skills/enforcement.py`）
  - [ ] 定义 `model_visible_tool_skill_ids` 和 `host_internal_tool_names`
  - [ ] 编写门禁测试

- [ ] **接入 BaseAgent**
  - [ ] 在 `BaseAgent.execute_tool()` 添加 guard 检查
  - [ ] 在 `ReportAgent._execute_tool()` 添加 guard 检查
  - [ ] 测试未加载 skill 时拒绝访问

### Phase 5: ReAct Parser（预计 1-2 天）

- [ ] **扩展 Parser**
  - [ ] 在 `ParsedReactResponse` 添加 `selected_skill_id` 字段
  - [ ] 实现 `<skill_selection>` XML 标签解析
  - [ ] 实现协议错误检测（skill_selection + Action/Final Answer）

- [ ] **测试**
  - [ ] 测试正常 skill_selection 解析
  - [ ] 测试混合协议错误检测
  - [ ] 测试 JSON 格式验证

### Phase 6: API Endpoints（预计 2 天）

- [ ] **更新 /skills/catalog**
  - [ ] 调用 `build_unified_catalog()`
  - [ ] 支持 namespace 过滤
  - [ ] 返回 unified 字段

- [ ] **更新 /skills/{id}**
  - [ ] 调用 `load_unified_skill_detail()`
  - [ ] 返回完整旧字段兼容矩阵
  - [ ] 错误处理（404, 409）

- [ ] **更新 /config**
  - [ ] 保留 `skillAvailability`（旧字段）
  - [ ] 新增 `unifiedSkillAvailability`
  - [ ] 测试两者共存

### Phase 7: 前端适配（预计 2-3 天）

- [ ] **移除本地 Catalog**
  - [ ] 创建 `useSkillCatalog` hook 从 API 获取
  - [ ] 更新 `SkillToolsPanel.tsx`
  - [ ] 更新 `ScanConfigExternalToolDetail.tsx`

- [ ] **Prompt Skills**
  - [ ] 适配 `prompt-{agent_key}@effective` 格式
  - [ ] 更新 `PromptSkillsPanel.tsx`
  - [ ] 测试 display_name 和 agent_key 显示

### Phase 8: 测试与文档（预计 2 天）

- [ ] **集成测试**
  - [ ] 端到端 catalog -> detail 流程测试
  - [ ] skill_selection 到 tool execution 闭环测试
  - [ ] 前后端联调测试

- [ ] **文档更新**
  - [ ] 更新 API 文档（OpenAPI spec）
  - [ ] 更新开发者指南
  - [ ] 记录已知限制和 Phase 2 计划

### 关键风险点

⚠️ **必须注意**：

1. **Workflow Registry 缺失**：
   - `build_skill_registry.py` 不存在
   - Phase 1 建议跳过 workflow，只做 scan-core + prompt
   - 或先实现 registry 构建脚本

2. **ReportAgent 私有路径**：
   - `_execute_tool()` 需单独接入 guard
   - 不能只改 `BaseAgent`

3. **前端静态 Catalog**：
   - 必须测试后端字段完整后才能移除
   - 保留降级策略

4. **配置项传播**：
   - 确保所有环境（dev, docker, deploy）都更新配置
   - 测试缺失配置时的降级行为

### 估算总工时

- **最小实施（仅 scan-core + prompt）**：12-15 天
- **包含 workflow registry**：增加 3-5 天
- **包含完整测试和文档**：增加 2-3 天

**总计**：15-23 工作日（取决于范围）

## 默认假设

本文件只保留以下显式默认值，不再依赖隐含前提：

- 正式环境默认使用预生成 workflow registry，而不是启动时构建。
- 默认开发 compose 不作为 unified workflow runtime 验收环境。
- `use_prompt_skills` 仅保留请求兼容，不再控制 prompt-effective 是否进入 unified catalog。
- `unifiedSkillAvailability` 是本轮新增字段，旧 `skillAvailability` 保持兼容。
- host 只共享 catalog/detail cache，不共享 loaded-state。
