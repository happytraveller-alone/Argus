# Argus 开发者架构指南

> 2026-04-30 更新：本仓库当前是 slim-source 形态，运行主线为 Rust/Axum backend、React/Vite frontend、Opengrep 静态审计、AgentFlow 智能审计。历史 Python/FastAPI、Bandit/Gitleaks/PHPStan/PMD/YASA 等链路若仍出现在归档或兼容测试中，按退役背景处理，不作为新功能入口。

这份文档面向第一次接手 Argus 的开发者：先建立系统主线，再告诉你从哪些文件开始读代码。接口字段逐项说明、数据库逐表说明和未来规划不放在这里。

## 阅读定位

- **文档类型**：以架构解释为主，兼顾高频代码入口索引。
- **目标读者**：第一次接手 Argus 的前端、后端或全栈开发者。
- **建议顺序**：先读“系统主线”，再读“请求如何流动”，最后按“常见开发任务定位”进入代码。
- **术语入口**：如果 `Project`、`AgentTask`、`AgentFinding`、AgentFlow、Opengrep 这些词还不熟，先看 [glossary.md](./glossary.md)。

## 系统主线

Argus 是一个以 `Project` 为中心的代码安全审计工作台。

当前运行时由这些部分组成：

- **Frontend**：`frontend/`，React + Vite + TypeScript，页面路由在 `frontend/src/app/routes.tsx`。
- **Backend**：`backend/`，Rust + Axum，服务入口在 `backend/src/main.rs`，路由聚合在 `backend/src/routes/mod.rs`。
- **Database**：PostgreSQL，通过 `sqlx` 访问，主要状态代码在 `backend/src/db/`。
- **Runner**：Docker runner 负责隔离执行 Opengrep 和 AgentFlow；Compose 服务在 `docker-compose.yml`。
- **LLM 配置**：智能审计依赖系统配置和 `.argus-intelligent-audit.env` 启动导入链路。

如果只记一句话：**Argus 把一个 ZIP 项目归档成 `Project`，再围绕它启动静态审计或智能审计，并把结果汇总回前端。**

## 两类审计模式

### 静态审计

当前可运行的静态审计主线是 **Opengrep-only**。

- 后端路由：`backend/src/routes/static_tasks.rs`
- 前端 API：`frontend/src/shared/api/opengrep.ts`
- 前端结果页：`frontend/src/pages/StaticAnalysis.tsx`
- 任务管理聚合：`frontend/src/features/tasks/services/taskActivities.ts`
- Runner 脚本：`docker/opengrep-scan.sh`
- Runner 镜像：`docker/opengrep-runner.Dockerfile`

历史 Bandit、Gitleaks、PHPStan、PMD 等前端 API 文件仍可能存在，用于迁移、防回归或退役路由测试；不要把它们当作新增静态引擎的当前入口。`backend/tests/opengrep_only_static_tasks.rs` 明确锁定非 Opengrep 静态路由不再由 Rust gateway 拥有。

### 智能审计

智能审计由 `AgentTask` 主导，并通过 AgentFlow runner 执行。

- 后端路由：`backend/src/routes/agent_tasks.rs`
- 后端 runtime：`backend/src/runtime/agentflow/`
- Runner pipeline：`backend/agentflow/pipelines/intelligent_audit.py`
- Runner 镜像：`docker/agentflow-runner.Dockerfile`
- 前端 API：`frontend/src/shared/api/agentTasks.ts`
- 前端详情页：`frontend/src/pages/AgentAudit/TaskDetailPage.tsx`
- 实时流消费：`frontend/src/shared/api/agentStream.ts`

智能审计创建前必须经过 LLM / runner 预检。创建弹窗走 `frontend/src/components/scan/CreateProjectScanDialog.tsx`，预检接口封装在 `frontend/src/shared/api/agentPreflight.ts` 与 `frontend/src/components/scan/create-project-scan/llmGate.ts`。

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

### `AgentTask` / `AgentEvent` / `AgentFinding`

智能审计的核心对象分别对应：任务、运行事件、最终漏洞发现。

关键入口：

- 路由和业务编排：`backend/src/routes/agent_tasks.rs`
- 持久化状态：`backend/src/db/task_state.rs`
- AgentFlow 输出导入：`backend/src/runtime/agentflow/importer.rs`
- 前端契约：`frontend/src/shared/api/agentTasks.ts`
- 前端事件流：`frontend/src/shared/api/agentStream.ts`
- 智能详情页：`frontend/src/pages/AgentAudit/TaskDetailPage.tsx`

## 请求如何流动

### 创建项目

1. 前端在 `frontend/src/shared/api/database.ts` 调用 `/api/v1/projects` 或 `/api/v1/projects/{id}/zip`。
2. 后端 `backend/src/routes/projects.rs` 保存项目元数据与 ZIP 归档。
3. 文件树、代码浏览、审计任务都基于这份项目归档继续展开。

### 创建静态审计

1. 前端入口是 `frontend/src/components/scan/CreateProjectScanDialog.tsx`，静态模式当前只创建 Opengrep 任务。
2. 前端调用 `frontend/src/shared/api/opengrep.ts`。
3. 后端 `backend/src/routes/static_tasks.rs` 创建任务并调度 `docker/opengrep-scan.sh`。
4. 结果回到 `StaticAnalysis` 详情页和任务管理页。

### 创建智能审计

1. 前端入口仍是 `CreateProjectScanDialog.tsx`。
2. 弹窗打开、手动重试、点击创建前都应走 agent preflight，而不是直接把系统设置页的 LLM test 当创建门禁。
3. 创建成功后前端调用 `createAgentTask`，路由到 `/agent-audit/{taskId}`。
4. 后端 `backend/src/routes/agent_tasks.rs` 创建 `AgentTask`，再启动 AgentFlow runner。
5. AgentFlow 输出经 `backend/src/runtime/agentflow/importer.rs` 导入为事件、finding、计数和报告。
6. 前端详情页通过 REST + SSE 展示运行过程与最终结果。

### 系统配置与 LLM 预检

- 启动导入源：`.argus-intelligent-audit.env`。
- 后端配置路由：`backend/src/routes/system_config.rs`。
- 后端 LLM 测试与 fingerprint：`backend/src/llm/tester.rs`。
- 前端系统配置页：`frontend/src/components/system/SystemConfig.tsx`。
- 创建弹窗预检：`frontend/src/components/scan/create-project-scan/llmGate.ts`。

约定：设置页可以使用 `/system-config/test-llm` 做连接测试；智能审计创建门禁使用 `/system-config/agent-preflight`。

## 前端 UI 共享边界

这些组件属于跨页面共享 UI，修改时要按共享组件处理，不能只补单页：

- `frontend/src/components/data-table/DataTable.tsx`
- `frontend/src/components/data-table/DataTableColumnHeader.tsx`
- `frontend/src/features/tasks/components/TaskActivitiesListTable.tsx`
- `frontend/src/features/dashboard/components/DashboardCommandCenter.tsx`
- `frontend/src/pages/AgentAudit/components/Header.tsx`

2026-04-29 的表格/仪表盘/智能详情 UI 修复锁定了这些边界：

- DataTable 表头筛选触发器必须在共享表头控件内，并且不能用 `preventDefault()` 阻断 Radix Popover / Dropdown 打开。
- Dashboard 图表选择栏属于图表区顶部；右侧任务状态边栏必须继续作为主 grid 的兄弟列存在。
- 智能审计详情标签属于标题行，放在“智能审计详情”右侧；动作按钮仍在右侧按钮组。
- 静态/智能任务管理页共用 `TaskActivitiesListTable`，表格视觉对齐项目管理表格时不得改变详情路由、取消行为、过滤或分页语义。

相关回归测试：

- `frontend/tests/dataTableHeaderFilters.test.tsx`
- `frontend/tests/dashboardCommandCenter.test.tsx`
- `frontend/tests/dashboardCommandCenterStyling.test.ts`
- `frontend/tests/agentAuditHeader.test.tsx`
- `frontend/tests/agentAuditTaskDetailHomeCards.test.ts`
- `frontend/tests/taskActivitiesListTable.test.tsx`

## 代码从哪里读

### 后端优先入口

1. `backend/src/main.rs`：启动流程、bootstrap 与监听。
2. `backend/src/app.rs`：Axum router 组装。
3. `backend/src/routes/mod.rs`：Rust gateway 当前拥有的 API 域。
4. `backend/src/routes/projects.rs`：项目与 ZIP 文件入口。
5. `backend/src/routes/static_tasks.rs`：Opengrep 静态审计入口。
6. `backend/src/routes/agent_tasks.rs`：智能审计任务、事件、finding、报告入口。
7. `backend/src/routes/system_config.rs`：系统配置、LLM 测试、agent preflight。

### 前端优先入口

1. `frontend/src/app/routes.tsx`：页面和导航边界。
2. `frontend/src/components/scan/CreateProjectScanDialog.tsx`：两种审计模式的创建入口。
3. `frontend/src/shared/api/database.ts`：项目、系统配置等通用 API。
4. `frontend/src/shared/api/opengrep.ts`：静态审计 API。
5. `frontend/src/shared/api/agentTasks.ts`：智能审计 API。
6. `frontend/src/features/tasks/services/taskActivities.ts`：任务管理聚合口径。
7. `frontend/src/pages/AgentAudit/TaskDetailPage.tsx`：智能审计详情页主编排。

## 常见开发任务定位

### 改扫描创建入口

优先读：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`
- `frontend/src/components/scan/create-project-scan/`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/shared/api/agentTasks.ts`
- `frontend/src/shared/api/agentPreflight.ts`

### 改静态审计

优先读：

- `backend/src/routes/static_tasks.rs`
- `backend/src/scan/opengrep.rs`
- `docker/opengrep-scan.sh`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/pages/StaticAnalysis.tsx`

### 改智能审计运行过程

优先读：

- `backend/src/routes/agent_tasks.rs`
- `backend/src/runtime/agentflow/`
- `backend/agentflow/pipelines/intelligent_audit.py`
- `docker/agentflow-runner.sh`
- `frontend/src/pages/AgentAudit/TaskDetailPage.tsx`

### 改 Agent 实时流或回放

优先读：

- `backend/src/routes/agent_tasks.rs` 中的 events / stream 路由
- `backend/src/db/task_state.rs`
- `frontend/src/shared/api/agentStream.ts`
- `frontend/src/pages/AgentAudit/hooks/`

### 改表格或列表 UI

优先读：

- `frontend/src/components/data-table/`
- `frontend/src/pages/projects/components/ProjectsTable.tsx`
- `frontend/src/features/tasks/components/TaskActivitiesListTable.tsx`
- 对应的 `frontend/tests/*Table*.test.*`

共享 DataTable 改动会影响多处页面；先写或更新源级/组件级回归测试，再改样式或事件处理。

## 退役与兼容边界

- 旧 Python/FastAPI backend 不是当前运行主线。
- 非 Opengrep 静态引擎路由不应重新接入当前 Rust gateway，除非先有新的计划和迁移说明。
- 智能审计禁止把静态扫描任务或静态 finding 候选作为 P1 输入；相关防线在 `backend/src/routes/agent_tasks.rs`。
- 归档文档、历史测试和旧前端 API 文件可能保留旧名词；新增代码和新文档应优先使用当前主线术语。
