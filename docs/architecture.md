# Argus 开发者架构指南

> 2026-04-30 更新：本仓库当前是 slim-source 形态，运行主线为 Rust/Axum backend、React/Vite frontend、Opengrep 静态审计。历史 Python/FastAPI、Bandit/Gitleaks/PHPStan/PMD/YASA 等链路若仍出现在归档或兼容测试中，按退役背景处理，不作为新功能入口。
>
> 2026-04-30 实施补充：CodeQL 隔离扫描已进入基础实施阶段：后端已有 `engine="codeql"` 静态任务骨架、`rules_codeql` 查询资产发现、独立 `codeql-runner` 镜像/脚本和 SARIF 解析基础。它仍不是完整首版；五类语言端到端全绿前只能称为里程碑基础能力。
>
> 2026-05-01 CodeQL 编译沙箱切片：当前已新增 C/C++ 专用 compile sandbox 闭环。该切片先运行 `codeql-compile-sandbox` 探索并验证 C/C++ 构建命令，把 accepted build plan / fingerprint / evidence index 持久化为 DB/task-state 真源，再让 `codeql-scan` 在 `database create` 阶段重放该命令。Artifacts/evidence/cache 只作诊断与缓存信号，不替代 CodeQL 捕获；JS/TS、Python、Java、Go 仍是后续里程碑，不阻塞这个 C/C++ 切片。
>
> 2026-05-01 智能审计退役：原 agentflow 实现已完全退役。前端保留路由和菜单项作为占位，显示"在开发中"提示。Codex 将提供新实现。详见 `docs/decisions/2026-05-01-agentflow-retired.md`。

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
- **Database**：PostgreSQL，通过 `sqlx` 访问，主要状态代码在 `backend/src/db/`；CodeQL C/C++ compile-sandbox 的 accepted build plan 由 `rust_codeql_build_plans` 表承载，file/task-state 只作状态投影或 fallback。
- **Runner**：Docker runner 负责隔离执行 Opengrep 和 CodeQL；Compose 服务在 `docker-compose.yml`。

如果只记一句话：**Argus 把一个 ZIP 项目归档成 `Project`，再围绕它启动静态审计，并把结果汇总回前端。**

## 审计模式

### 静态审计

当前稳定静态审计主线仍是 **Opengrep**。CodeQL 隔离扫描已有基础骨架：`StaticTaskRecord.engine` 可分流 `codeql`，查询资产位于 `backend/assets/scan_rule_assets/rules_codeql`，runner 使用 `docker/codeql-runner.Dockerfile` + `docker/codeql-scan.sh`，SARIF 解析映射到现有静态 finding 形态。2026-05-01 的当前可执行切片只承诺 C/C++ compile-sandbox 闭环：先由 `docker/codeql-compile-sandbox.sh` 在隔离 runner 中发现/验证 build recipe 并持久化，再由 CodeQL runner 重放 recipe 建库。该 build recipe 必须是 CodeQL `database create --command` 可按 argv 拆分重放的简单命令（例如 Makefile 路径使用 `make -B -j2`），不要依赖 shell-only `${...}` 默认展开、`||`、`;` 或管道语法；需要 CMake 时由编译沙箱先完成 configure，再持久化 `cmake --build ...` 重放命令。CodeQL 五类语言端到端全绿前，不得标记为完整首版完成。

- 后端路由：`backend/src/routes/static_tasks.rs`
- 前端 API：`frontend/src/shared/api/opengrep.ts`
- 前端结果页：`frontend/src/pages/StaticAnalysis.tsx`
- 任务管理聚合：`frontend/src/features/tasks/services/taskActivities.ts`
- Opengrep runner 脚本：`docker/opengrep-scan.sh`
- Opengrep runner 镜像：`docker/opengrep-runner.Dockerfile`
- CodeQL runner 脚本：`docker/codeql-scan.sh`
- CodeQL C/C++ 编译沙箱脚本：`docker/codeql-compile-sandbox.sh`
- CodeQL 诊断脚本：`docker/test-codeql-diagnostics.sh`
- CodeQL runner 镜像：`docker/codeql-runner.Dockerfile`

历史 Bandit、Gitleaks、PHPStan、PMD 等前端 API 文件仍可能存在，用于迁移、防回归或退役路由测试；不要把它们当作新增静态引擎的当前入口。`backend/tests/opengrep_only_static_tasks.rs` 明确锁定这些退役静态路由不再由 Rust gateway 拥有。CodeQL 是新的隔离例外：它按 `StaticTaskRecord.engine="codeql"`、`rules_codeql`、独立 `codeql-runner` 和 SARIF 到 `StaticFindingRecord` 映射推进，不复活旧多引擎路由。

### 智能审计（已退役）

原 agentflow 实现已于 2026-05-01 完全退役。前端保留路由和菜单项作为占位，显示"在开发中"提示。Codex 将提供新实现。详见 `docs/decisions/2026-05-01-agentflow-retired.md`。

## 核心对象

### `Project`

`Project` 是系统中心对象：项目元数据、ZIP 归档、文件浏览、静态任务、智能任务和聚合统计都挂在它下面。

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

1. 前端入口是 `frontend/src/components/scan/CreateProjectScanDialog.tsx`，静态模式默认仍创建 Opengrep 任务。CodeQL 基础 API 已存在于 `frontend/src/shared/api/opengrep.ts`（CodeQL wrappers）和 `SCAN_ENGINE_TABS`，但产品 UI 全量切换仍需后续里程碑验证。
2. 前端调用 `frontend/src/shared/api/opengrep.ts`。
3. 后端 `backend/src/routes/static_tasks.rs` 创建任务：默认 Opengrep 调度 `docker/opengrep-scan.sh`；`engine="codeql"` 当前先固定为 C/C++ 切片，先调度 `docker/codeql-compile-sandbox.sh` 生成 DB-backed build plan，再调度 `docker/codeql-scan.sh` 重放该 plan 完成 `database create/analyze`。
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
- 静态任务管理页使用 `TaskActivitiesListTable`，表格视觉对齐项目管理表格时不得改变详情路由、取消行为、过滤或分页语义。

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
- `docker/opengrep-scan.sh`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/pages/StaticAnalysis.tsx`

## 退役与兼容边界

- 旧 Python/FastAPI backend 不是当前运行主线。
- 非 Opengrep 静态引擎路由不应重新接入当前 Rust gateway，除非先有新的计划和迁移说明。
- 原 agentflow 智能审计已完全退役，详见 `docs/decisions/2026-05-01-agentflow-retired.md`。
- 归档文档、历史测试和旧前端 API 文件可能保留旧名词；新增代码和新文档应优先使用当前主线术语。
