# Argus 开发者架构指南

> 2026-04-30 更新：本仓库当前是 slim-source 形态，运行主线为 Rust/Axum backend、React/Vite frontend、Opengrep 静态审计。历史 Python/FastAPI 和已退役静态引擎链路若仍出现在归档或兼容测试中，按退役背景处理，不作为新功能入口。
>
> 2026-05-07 CubeSandbox 退役：所有 CubeSandbox 运行时（cubelet/cubemaster/envd Connect-RPC、模板 provisioner、`/sandbox-management` 操作页、`/api/v1/cubesandbox/*` 路由族、`backend/src/runtime/cubesandbox/`、`scripts/cubesandbox-*.sh`、`oci/cubesandbox/` 镜像定义、`third_party/cubesandbox` 子模块）已删除并归档至 `archive/cubesandbox/`。CodeQL 隔离扫描路径暂处于不可用状态（HTTP 路由保留，inner 返回 `codeql_unavailable`）；a3s-box 适配落地后恢复（follow-up F1）。Opengrep 默认走 Dockerfile runner，可选 a3s-box MicroVM。`runtime::shutdown` 模块承接原 `runtime::cubesandbox` 的 `ShutdownGate` / `ActiveScanGuard` / drain 抽象。历史决策与 timeline 见 `archive/cubesandbox/INDEX.md`。

这份文档面向第一次接手 Argus 的开发者：先建立系统主线，再告诉你从哪些文件开始读代码。接口字段逐项说明、数据库逐表说明和未来规划不放在这里。

## 阅读定位

- **文档类型**：以架构解释为主，兼顾高频代码入口索引。
- **目标读者**：第一次接手 Argus 的前端、后端或全栈开发者。
- **建议顺序**：先读“系统主线”，再读“请求如何流动”，最后按“常见开发任务定位”进入代码。
- **术语入口**：如果 `Project`、Opengrep、CodeQL 这些词还不熟，先看 [glossary.md](./glossary.md)。

## 系统主线

Argus 是一个以 `Project` 为中心的代码安全审计工作台。

当前运行时由这些部分组成：

- **Frontend**：`frontend/`，React + Vite + TypeScript，页面路由在 `frontend/src/app/routes.tsx`。
- **Backend**：`backend/`，Rust + Axum，服务入口在 `backend/src/main.rs`，路由聚合在 `backend/src/routes/mod.rs`。
- **Database**：PostgreSQL，通过 `sqlx` 访问，主要状态代码在 `backend/src/db/`；CodeQL C/C++ 的 accepted build plan 由 `rust_codeql_build_plans` 表承载，file/task-state 只作状态投影或 fallback。`rust_cubesandbox_templates` DDL 保留为 no-op（兼容旧库），新代码不再 SELECT；可通过 `scripts/purge-cubesandbox.sh --drop-tables` 显式 opt-in 删表。
- **Runner/Sandbox**：Opengrep 默认使用 Docker runner 动态容器执行；静态审计高级配置可把单次 Opengrep 任务切到 a3s-box MicroVM（`opengrep_sandbox=a3s_box`），但 `dockerfile_container` 仍是默认值。CodeQL 路径目前禁用（cubesandbox 退役后等待 a3s 适配；HTTP 路由保留 `codeql_unavailable` 占位）。Docker runner preflight 只验证默认 Opengrep runner。`docker-compose.yml` 中的 runner service 仅作为 `runner-build` profile 镜像构建目标，默认启动不保留 runner service 容器。历史 AgentFlow runner service 当前不在 compose 主线中。

如果只记一句话：**Argus 把一个 ZIP 项目归档成 `Project`，再围绕它启动静态审计，并把结果汇总回前端；智能审计执行链当前处于占位/重构过渡，仅基础 LLM 配置适配已开始落地。**

## 审计模式

### 静态审计

当前稳定静态审计主线仍是 **Opengrep**，默认执行方式仍是 Dockerfile runner 动态容器。创建静态审计时，Opengrep 高级配置会把 `opengrep_sandbox` 传给后端：`dockerfile_container` 保持原默认路径，`a3s_box` 走 a3s-box MicroVM；公共选择器和生命周期 API 仍命名为 `opengrep`。CodeQL 隔离扫描路径在 cubesandbox 退役后处于不可用占位（HTTP 路由保留，inner 返回 `codeql_unavailable`，等待 a3s 适配落地，参见 follow-up F1）。查询资产仍在 `backend/assets/scan_rule_assets/rules_codeql`（`c`、`cpp`、`python` 来自官方 `github/codeql` 仓库），等待新执行通道接入。

CodeQL 路径目前禁用：`StaticTaskRecord.engine="codeql"` 创建后立即标记 `codeql_unavailable`。前端 `CodeqlScanDetail` / `CodeqlExplorationPanel` 入口保留以避免 404，等待 a3s 后端接入后恢复完整 LLM 探索流程。详细历史见 `archive/cubesandbox/`。

**Opengrep sandbox 选择**：

1. 前端 `StaticEngineConfigDialog` 只在 Opengrep 高级配置里展示两种执行方式：`Dockerfile 容器` 与 `a3s-box 沙箱`。
2. `frontend/src/shared/api/opengrep.ts` 将选择序列化为 `opengrep_sandbox`；后端还兼容旧键 `sandbox` / `sandbox_mode`，未知值回落到 `dockerfile_container`。
3. Dockerfile 默认路径继续使用 `docker/opengrep-runner.Dockerfile` + `docker/opengrep-scan.sh`，按任务创建临时 runner 容器，任务结束删除。
4. a3s-box 路径通过 `backend/src/runtime/a3s_box_runner.rs` 启动 krun-vm MicroVM 执行 `opengrep-scan`，再把 results/summary/log/stdout/stderr 写回与 Docker 路径相同的 workspace 输出文件。
5. 任务状态 `extra.opengrep_sandbox` 记录实际执行选择，便于 UI/日志/排障区分。

- 后端路由：`backend/src/routes/static_tasks.rs`
- 前端 API：`frontend/src/shared/api/opengrep.ts`
- 前端结果页：`frontend/src/pages/StaticAnalysis.tsx`
- 任务管理聚合：`frontend/src/features/tasks/services/taskActivities.ts`
- Opengrep runner 脚本：`docker/opengrep-scan.sh`
- Opengrep runner 镜像：`docker/opengrep-runner.Dockerfile`
- Opengrep a3s-box 执行模块：`backend/src/runtime/a3s_box_runner.rs`
- CodeQL 解析/验证模块（占位）：`backend/src/scan/codeql.rs`

旧多引擎静态审计链路已经从当前前后端主线删除；不要把退役路由或历史兼容数据当作新增静态引擎的当前入口。CodeQL 路径在 a3s 适配恢复前不应作为可用引擎暴露。

### 智能审计（重构过渡）

当前智能审计不是旧 AgentFlow 端到端产品主线。代码状态是：

- 后端 API 主路由 `backend/src/routes/mod.rs` 只挂载 system-config、projects、search、skills 和 static-tasks，不挂载 `/api/v1/agent-tasks`。
- 后端已挂载新的 `/api/v1/intelligent-tasks` 轻量任务接口，用于创建、读取、取消、删除和 SSE 订阅智能审计任务记录。
- 后端 runtime 主导出 `backend/src/runtime/mod.rs` 不包含 `agentflow` 模块；`runtime/intelligent/config.rs` 仅负责把保存的 system-config LLM row 解析成 claw-code 后续 bridge 可消费的安全配置快照。
- 前端 `/agent-audit/:taskId` 路由渲染 `frontend/src/pages/AgentAuditDetail.tsx`，按 CodeQL 详情页样式显示标题右侧概要标签、右侧推理/结果面板、执行进度、原始事件、发现问题和摘要。
- `vendor/agentflow-src/` 删除已提交待推送；`backend/agentflow/` 历史 pipeline/schema 资产和 `/api/v1/system-config/agent-preflight` 仍存在，属于过渡期资产或配置门禁，不代表 AgentFlow 执行链已重新接入。
- `frontend/src/shared/api/agentTasks.ts` 当前只保留 `AgentTask` / `AgentFinding` 等历史快照类型，供项目聚合、统一漏洞详情和历史数据展示继续编译；它不再导出旧 `/agent-tasks` CRUD / report API 调用。

因此，新增功能不要从旧 AgentFlow runner 执行路径开始；如果要恢复或重建完整智能审计，需要沿新的 `runtime/intelligent/` 和 `/intelligent-tasks` 基础继续补齐 claw-code bridge、runner/工具沙箱和更完整的 frontend contract。

## 核心对象

### `Project`

`Project` 是系统中心对象：项目元数据、ZIP 归档、文件浏览、静态任务和聚合统计都挂在它下面。历史/过渡智能任务字段可能仍出现在兼容数据或前端聚合里，但当前后端主路由不提供 AgentTask 执行 API。

关键入口：

- 后端路由与文件操作：`backend/src/routes/projects.rs`
- 后端存储：`backend/src/db/projects.rs`
- 前端 API：`frontend/src/shared/api/database.ts`
- 前端项目页：`frontend/src/pages/Projects.tsx`
- 项目表格：`frontend/src/pages/projects/components/ProjectsTable.tsx`

### 静态审计任务与 finding

Opengrep 静态任务和 finding 由 Rust backend 管理，前端在产品层把它们展示成“静态审计”。

关键入口：

- `backend/src/routes/static_tasks.rs`
- `backend/src/scan/opengrep.rs`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/pages/static-analysis/`
- `frontend/src/features/tasks/components/TaskActivitiesListTable.tsx`

## 请求如何流动

### 创建项目

1. 前端在 `frontend/src/shared/api/database.ts` 调用 `/api/v1/projects` 或 `/api/v1/projects/{id}/zip`。
2. 后端 `backend/src/routes/projects.rs` 保存项目元数据与 ZIP 归档。
3. 文件树、代码浏览、审计任务都基于这份项目归档继续展开。

### 创建静态审计

1. 前端入口是 `frontend/src/components/scan/CreateProjectScanDialog.tsx` 和 `frontend/src/components/scan/CreateScanTaskDialog.tsx`。静态模式当前只暴露 Opengrep 主引擎；CodeQL 路径在 cubesandbox 退役后处于占位禁用状态（任务立即标 `codeql_unavailable`）。
2. 前端调用 `frontend/src/shared/api/opengrep.ts`；Opengrep 高级配置会随创建 payload 传 `opengrep_sandbox`，默认 `dockerfile_container`，可选 `a3s_box`。
3. 后端 `backend/src/routes/static_tasks.rs` 创建任务：默认 Opengrep 调度 `docker/opengrep-scan.sh`；选择 `a3s_box` 时走 `backend/src/runtime/a3s_box_runner.rs` 启动 krun-vm MicroVM 执行同一 `opengrep-scan` 包装器；`engine="codeql"` 任务立即标记 `codeql_unavailable`。
4. 结果回到 `StaticAnalysis` 详情页和任务管理页。

## 前端 UI 共享边界

这些组件属于跨页面共享 UI，修改时要按共享组件处理，不能只补单页：

- `frontend/src/components/data-table/DataTable.tsx`
- `frontend/src/components/data-table/DataTableColumnHeader.tsx`
- `frontend/src/features/tasks/components/TaskActivitiesListTable.tsx`
- `frontend/src/features/dashboard/components/DashboardCommandCenter.tsx`

2026-04-29 的表格/仪表盘 UI 修复锁定了这些边界：

- DataTable 表头筛选触发器必须在共享表头控件内，并且不能用 `preventDefault()` 阻断 Radix Popover / Dropdown 打开。
- Dashboard 图表选择栏属于图表区顶部；右侧任务状态边栏必须继续作为主 grid 的兄弟列存在。
- 静态/智能任务管理页共用 `TaskActivitiesListTable`，表格视觉对齐项目管理表格时不得改变详情路由、中止/删除行为、过滤或分页语义；操作列的“删除”是最右侧文字按钮，静态任务“结果分析”保持文字入口。

相关回归测试：

- `frontend/tests/dataTableHeaderFilters.test.tsx`
- `frontend/tests/dashboardCommandCenter.test.tsx`
- `frontend/tests/dashboardCommandCenterStyling.test.ts`
- `frontend/tests/taskActivitiesListTable.test.tsx`

## 代码从哪里读

### 后端优先入口

1. `backend/src/main.rs`：启动流程、bootstrap 与监听。
2. `backend/src/app.rs`：Axum router 组装。
3. `backend/src/routes/mod.rs`：Rust gateway 当前拥有的 API 域。
4. `backend/src/routes/projects.rs`：项目与 ZIP 文件入口。
5. `backend/src/routes/static_tasks.rs`：Opengrep 静态审计入口。
6. `backend/src/routes/system_config.rs`：系统配置。

### 前端优先入口

1. `frontend/src/app/routes.tsx`：页面和导航边界。
2. `frontend/src/components/scan/CreateProjectScanDialog.tsx`：两种审计模式的创建入口。
3. `frontend/src/shared/api/database.ts`：项目、系统配置等通用 API。
4. `frontend/src/shared/api/opengrep.ts`：静态审计 API。
5. `frontend/src/features/tasks/services/taskActivities.ts`：任务管理聚合口径。

## 常见开发任务定位

### 改扫描创建入口

优先读：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`
- `frontend/src/components/scan/create-project-scan/`
- `frontend/src/shared/api/opengrep.ts`

### 改静态审计

优先读：

- `backend/src/routes/static_tasks.rs`
- `backend/src/scan/opengrep.rs`
- `backend/src/runtime/a3s_box_runner.rs`
- `docker/opengrep-scan.sh`
- `frontend/src/components/scan/create-scan-task/StaticEngineConfigDialog.tsx`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/pages/StaticAnalysis.tsx`

## 退役与兼容边界

- 旧 Python/FastAPI backend 不是当前运行主线。
- 非 Opengrep 静态引擎路由不应重新接入当前 Rust gateway，除非先有新的计划和迁移说明。
- AgentFlow 智能审计执行链当前未挂载在 Rust gateway/runtime/compose 主线中；新的 `/api/v1/intelligent-tasks` 与 `/agent-audit/:taskId` 是重构过渡接口和详情页，不是旧 AgentFlow runner 复活。`vendor/agentflow-src/` 删除已提交待推送；历史 pipeline/schema 资产和前端历史快照类型仍在，ADR 文档位于 `frontend/docs/decisions/2026-05-01-agentflow-retired.md`。
- 归档文档、历史测试和旧前端 API 文件可能保留旧名词；新增代码和新文档应优先使用当前主线术语。
