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

- **是什么**：当前由 Opengrep 承担的规则扫描体验，产品层显示为“静态审计”。
- **不是什么**：Bandit/Gitleaks/PHPStan/PMD/YASA 等历史多引擎集合；这些名称若仍出现，多为退役兼容、防回归测试或旧前端 API 残留。
- **主要入口**：`backend/src/routes/static_tasks.rs`、`frontend/src/shared/api/opengrep.ts`、`frontend/src/pages/StaticAnalysis.tsx`。

### 智能审计

- **是什么**：以 `AgentTask` 为主任务模型，由 AgentFlow runner 完成侦察、分析、验证和报告生成的审计流程。
- **不是什么**：静态审计的包装层，也不是直接复用静态 finding 的候选输入流程。
- **主要入口**：`backend/src/routes/agent_tasks.rs`、`backend/src/runtime/agentflow/`、`frontend/src/pages/AgentAudit/TaskDetailPage.tsx`。

### Rust gateway

- **是什么**：当前后端运行主线，基于 Rust + Axum，入口是 `backend/src/main.rs`，路由聚合在 `backend/src/routes/mod.rs`。
- **不是什么**：旧 Python/FastAPI backend；新功能默认不要再以 `backend/app/...` 作为入口。

## 审计任务术语

### `AgentTask`

- **是什么**：智能审计的主任务实体。
- **不是什么**：某一个子智能体的一次执行，也不是静态审计任务。
- **主要入口**：`backend/src/routes/agent_tasks.rs`、`backend/src/db/task_state.rs`、`frontend/src/shared/api/agentTasks.ts`。

### `AgentEvent`

- **是什么**：智能审计运行过程中的事件记录，用于 REST 回放和前端实时流展示。
- **不是什么**：最终漏洞结论；最终漏洞应看 `AgentFinding`。
- **主要入口**：`backend/src/routes/agent_tasks.rs` 的 events / stream 路由、`frontend/src/shared/api/agentStream.ts`。

### `AgentFinding`

- **是什么**：AgentFlow 输出导入后沉淀的智能审计漏洞结果。
- **不是什么**：Opengrep finding、bootstrap candidate 或未经验证的静态扫描输入。
- **主要入口**：`backend/src/runtime/agentflow/importer.rs`、`frontend/src/shared/api/agentTasks.ts`。

### AgentFlow runner

- **是什么**：执行智能审计 pipeline 的隔离 runner，Compose 服务名是 `agentflow-runner`。
- **不是什么**：前端页面的一部分，也不是后端进程内直接执行的普通函数。
- **主要入口**：`docker/agentflow-runner.Dockerfile`、`docker/agentflow-runner.sh`、`backend/agentflow/pipelines/intelligent_audit.py`。

### Opengrep runner

- **是什么**：执行静态审计规则扫描的隔离 runner，Compose 服务名是 `opengrep-runner`。
- **不是什么**：Bandit/Gitleaks/PHPStan 等多引擎调度器。
- **主要入口**：`docker/opengrep-runner.Dockerfile`、`docker/opengrep-scan.sh`、`backend/src/scan/opengrep.rs`。

### agent preflight

- **是什么**：智能审计创建前的真实预检，检查保存的 LLM 配置、fingerprint、runner readiness 等条件。
- **不是什么**：系统设置页的普通 LLM 连通性测试；创建智能审计时不能只用 `/system-config/test-llm` 代替。
- **主要入口**：`backend/src/routes/system_config.rs`、`frontend/src/shared/api/agentPreflight.ts`、`frontend/src/components/scan/create-project-scan/llmGate.ts`。

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

### `.argus-intelligent-audit.env`

- **是什么**：智能审计启动导入的 LLM / AgentFlow 配置源。
- **不是什么**：前端或系统配置页面会直接写回的文件。
- **维护提示**：启动导入、系统配置保存和 fingerprint 行为必须一起验证。

### repo-local Codex / OMX

- **是什么**：本仓库内的 Codex/OMX 配置和 skills 目录，通常配合 `CODEX_HOME=$PWD/.codex` 使用。
- **不是什么**：全局 `~/.codex` 的替代品；`.codex/` 当前被 `.gitignore` 忽略，跨环境复用 skill 需要重新安装或显式调整版本控制策略。

## 阅读路线建议

- 想先看系统全貌：读 [architecture.md](./architecture.md)。
- 想启动本地环境：读根目录 `README.md` 或 `README_EN.md`。
- 想看后端命令：读 `backend/README.md`。
- 想改 UI 表格：从 `frontend/src/components/data-table/` 和相关 `frontend/tests/` 开始。
