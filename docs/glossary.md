# Argus 文档术语表

## 使用方式

- 这份术语表只收录当前代码和文档中高频、容易混淆的概念。
- 每个术语说明“是什么”和“不是什么”，帮助新人避免把历史链路当成当前入口。
- 第一次进入仓库时，建议先读本文件，再读 [architecture.md](./architecture.md)。

## 系统级对象

### `Project`

- **是什么**：Argus 的中心工作空间，承接项目元数据、ZIP 归档、文件浏览、扫描任务和聚合结果。
- **不是什么**：单次扫描任务本身；静态审计任务和智能审计任务都挂在 `Project` 下。
- **主要入口**：`backend/src/routes/projects.rs`、`backend/src/db/projects.rs`、`frontend/src/shared/api/database.ts`。

### 静态审计

- **是什么**：当前稳定主线由 Opengrep 承担的规则扫描体验，产品层显示为“静态审计”。Opengrep 默认产品路径使用 Dockerfile runner 容器；默认/推荐部署用 rootless Podman 执行该 runner，也可以在高级配置里把单次任务切到 `opengrep_sandbox=a3s_box` 的 a3s MicroVM。Docker Compose/Docker runner 保留为显式本地/dev fallback。CodeQL 隔离扫描路径目前因旧隔离实现退役处于不可用状态（详见归档 follow-up F1）。
- **不是什么**：历史多引擎静态审计集合；退役兼容、防回归测试或旧前端 API 残留不应重新成为当前入口。CodeQL 路径未恢复前不应作为可用引擎暴露。
- **主要入口**：`backend/src/routes/static_tasks.rs`、`frontend/src/shared/api/opengrep.ts`、`frontend/src/pages/StaticAnalysis.tsx`。

> CubeSandbox 路径已于 2026-05-07 归档至 `docs/archive/cubesandbox/`，扫描统一走 a3s sandbox 或 Dockerfile runner。CodeQL 在 a3s 适配落地之前保持禁用占位（HTTP 路由保留，inner 返回 `codeql_unavailable`）。

### 智能审计

- **是什么**：AI 驱动的安全审计产品方向。
- **当前状态**：重构过渡。Rust gateway 当前不挂载旧 `/api/v1/agent-tasks`，runtime 不导出旧 `agentflow`，但已挂载新的 `/api/v1/intelligent-tasks` 轻量任务接口；前端 `/agent-audit/:taskId` 渲染 `AgentAuditDetail.tsx`，展示任务标签、执行进度、LLM 推理思考、获取结果、事件日志、发现问题和摘要。`vendor/agentflow-src/` 已删除；`backend/agentflow/` 历史 pipeline/schema 资产、`frontend/src/shared/api/agentTasks.ts` 的历史快照类型和 `/api/v1/system-config/agent-preflight` 仍存在。`backend/src/runtime/intelligent/config.rs` 已开始承接 claw-code 迁移的基础 LLM 配置适配，但还不是完整 AgentFlow 执行链。
- **维护提示**：如果要恢复或重建智能审计，应继续沿 `runtime/intelligent/` 新边界补齐 route、task state、claw-code bridge、工具沙箱和前端 contract；不要默认复用旧 AgentFlow runner 执行链。

### Rust gateway

- **是什么**：当前后端运行主线，基于 Rust + Axum，入口是 `backend/src/main.rs`，路由聚合在 `backend/src/routes/mod.rs`。
- **不是什么**：旧 Python/FastAPI backend；新功能默认不要再以 `backend/app/...` 作为入口。

## 审计任务术语

### `AgentTask` / `AgentEvent` / `AgentFinding` / AgentFlow runner

- **历史背景**：这些是旧 AgentFlow 智能审计执行链的核心对象。
- **当前状态**：后端主路由不再挂载 `/api/v1/agent-tasks`，runtime 不再导出 `agentflow`；前端任务详情路由占位。代码库仍保留 AgentFlow pipeline/schema 资产、前端历史快照类型和部分兼容/聚合字段，但不再保留 `vendor/` 下的 AgentFlow source，也不再保留前端旧 `/agent-tasks` CRUD/report API 调用。
- **维护提示**：处理相关引用前先确认它是活跃执行入口、兼容数据字段、测试资产还是待清理残留；不要基于记忆直接批量删除。

### Opengrep runner

- **是什么**：执行静态审计规则扫描的隔离 runner。默认产品路径是 `docker/opengrep-runner.Dockerfile` 构建的临时容器；默认/推荐部署用 `OPENGREP_RUNNER_RUNTIME=podman` 走 rootless Podman，不挂宿主 Docker socket。Podman 路径必须记录 rootless proof、no host network、source/rules `ro` / output `rw` mount metadata；Docker Compose/Docker runner 保留为显式本地/dev fallback。静态审计 Opengrep 高级配置也可选择 `a3s-box 沙箱`，通过 `backend/src/runtime/a3s_box_runner.rs` 启动 krun-vm MicroVM 执行同一 `opengrep-scan` 包装器。
- **不是什么**：旧多引擎静态审计调度器，也不是 CodeQL 扫描主路径；a3s-box 选项不是默认值，未传或未知 `opengrep_sandbox` 仍回落到 Dockerfile 容器。
- **主要入口**：`docker/opengrep-runner.Dockerfile`、`docker/opengrep-scan.sh`、`backend/src/scan/opengrep.rs`、`backend/src/runtime/a3s_box_runner.rs`、`frontend/src/components/scan/create-scan-task/StaticEngineConfigDialog.tsx`；backend 按任务动态创建临时 runner 容器或 a3s-box MicroVM，任务结束后清理。

### 沙箱预热池 / Standby pool of one-shot sandboxes

- **是什么**：单次性沙箱预热层，把 microVM 生命周期（创建+连接 ~60s）移出扫描关键路径。后端在启动时按 `OPENGREP_STANDBY_POOL_SIZE` / `A3S_BOX_STANDBY_POOL_SIZE`（默认各 2）预热若干就绪沙箱；扫描分发时 `pool.take()` 拿一个 ready 沙箱直接用，扫完销毁；后台 `refill_in_background` 立即补一个进池。每个沙箱**仍然只服务一次扫描**（cold-start isolation 保留），不存在状态污染。当前活跃池只剩 a3s-box；旧隔离路径已于 2026-05-07 退役。
- **不是什么**：**不是**旧 multi-use warm pool（已在 2026-05-05 commit `63af399f` 删除）。"warm pool" 复用同一沙箱跑多次扫描，状态污染风险大；"standby pool" 每次取出即用即销，纯粹是**latency 优化**，不是 state-sharing。PR 标题 / 注释 / 识别符使用 "standby pool" / "pre-warm"，不要再用 "warm pool"。
- **主要入口**：`backend/src/runtime/sandbox_pool.rs`（generic `SandboxPool<T: Sandbox>` + `Priority::OnDemand|Refill` semaphore + `OnShutdownDestroy` 回调）、`backend/src/runtime/a3s_box/pool.rs`（`A3sBoxHandle` + `A3sBoxFactory`，Option C.β image-cache-only）、`backend/src/main.rs` 启动 + shutdown 串接。
- **维护提示**：a3s-box 受 single-shot CLI 限制走 Option C.β（image-cache-only pre-warm）；完整 ~70s 收益要 upstream a3s-box CLI 加 pause/resume 后才能切 Option C.α。`OPENGREP_STANDBY_POOL_DISABLED` / `A3S_BOX_STANDBY_POOL_DISABLED` env 变量是 kill switch（回滚到纯冷启动，无 503，只是慢）。

### agent preflight

- **是什么**：`/api/v1/system-config/agent-preflight`，当前仍存在于 `backend/src/routes/system_config.rs`，用于按 LLM 配置优先级做连接测试并检查 runner readiness。
- **当前状态**：保留为智能审计配置门禁。若 LLM 通过但 runner 未配置，响应会以 `runner_missing` 类原因说明智能审计初始化失败。
- **不是什么**：完整 AgentTask 创建或执行 API；当前 Rust gateway 不挂载 `/api/v1/agent-tasks`。

### LLM config set

- **是什么**：系统配置中的 schema v2 多 provider 配置表，公开形态是 `schemaVersion: 2`、`rows[]`、`latestPreflightRun`、`migration`；每行有稳定 id、priority、enabled、provider、baseUrl、model、密钥存在状态、高级参数和 latest preflight 状态。
- **不是什么**：旧版单对象 `llmConfig` 响应，也不是前端本地状态；后端 helper 负责迁移、归一、密钥保留/脱敏和 fallback 分类。
- **维护提示**：公开响应只能暴露 `hasApiKey` 等元数据，不能返回明文 API key；编辑时空 key 表示按 row id 保留旧密钥。设置页顶部"保存并验证"走 `/system-config/test-llm/batch`，只读取已保存配置，批量持久化 passed/failed/missing_fields 状态；创建智能审计仍走 agent preflight。新的 `runtime/intelligent/config.rs` 只把 saved row 转成 claw-code 后续 bridge 的内部配置快照，并跳过明文密钥序列化。

## 前端 UI 术语

### Shared DataTable

- **是什么**：前端共享表格层，主要位于 `frontend/src/components/data-table/`，负责列头、排序、筛选、分页等通用行为。
- **不是什么**：某个页面私有表格；共享表头事件处理会影响所有使用 DataTable 的页面。
- **维护提示**：列头筛选触发器不能调用 `preventDefault()` 阻断 Radix Popover / Dropdown 打开。

### Dashboard chart area

- **是什么**：仪表盘中统计卡片下方的图表选择栏和图表内容区域，实现在 `DashboardCommandCenter`。
- **不是什么**：右侧任务状态边栏；任务边栏应继续作为主 grid 的兄弟列。

### Task activities table

- **是什么**：静态审计和智能审计任务管理页共用的任务列表组件。
- **不是什么**：项目管理表格本身；它可以视觉对齐项目管理表格，但不能因此改变详情路由、取消行为、过滤或分页语义。
- **主要入口**：`frontend/src/features/tasks/components/TaskActivitiesListTable.tsx`。

## 配置与运行术语

### `.env`

- **是什么**：根目录运行时环境文件。`argus-bootstrap.sh` 首次运行会从根目录 `env.example` 复制生成它并自动写入 `SECRET_KEY`；后续启动前会校验其中的 LLM 配置，并在 backend 启动后导入 system-config。
- **不是什么**：UI 写回目标；前端保存配置只写 system-config，不直接修改这个文件。

### repo-local Codex / OMX

- **是什么**：本仓库内的 Codex/OMX 配置和 skills 目录，通常配合 `CODEX_HOME=$PWD/.codex` 使用。
- **不是什么**：全局 `~/.codex` 的替代品；`.codex/` 当前被 `.gitignore` 忽略，跨环境复用 skill 需要重新安装或显式调整版本控制策略。

## 阅读路线建议

- 想先看系统全貌：读 [architecture.md](./architecture.md)。
- 想启动本地环境：读根目录 `README.md` 或 `README_EN.md`。
- 想看后端命令：读 `backend/README.md`。
- 想改 UI 表格：从 `frontend/src/components/data-table/` 和相关 `frontend/tests/` 开始。
