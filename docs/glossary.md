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

- **是什么**：当前稳定主线由 Opengrep 承担的规则扫描体验，产品层显示为“静态审计”。2026-05-01 CodeQL 隔离扫描已有基础骨架，并新增 C/C++ compile-sandbox 闭环切片；完整五语言 CodeQL 仍不是首版完成能力。
- **不是什么**：历史多引擎静态审计集合；退役兼容、防回归测试或旧前端 API 残留不应重新成为当前入口。CodeQL 计划也不是把旧多引擎路由复活。
- **主要入口**：`backend/src/routes/static_tasks.rs`、`frontend/src/shared/api/opengrep.ts`、`frontend/src/pages/StaticAnalysis.tsx`。


### CodeQL 隔离扫描计划

- **是什么**：`plan/codeql_security/codeql_opengrep_isolated_scan_plan.md` 中规划并已开始落地的静态审计扩展：在静态审计/Opengrep 产品入口下增加 `engine="codeql"`，但使用独立 CodeQL runner、`rules_codeql` 查询资产、SARIF 解析和项目级 build plan 固化机制。
- **不是什么**：Opengrep runner 的增强阶段，也不是旧多引擎静态审计路由复活。当前 C/C++ compile-sandbox 切片不等于完整五语言首版。
- **主要计划入口**：`plan/codeql_security/codeql_opengrep_isolated_scan_plan.md`、`.omx/specs/deep-interview-codeql-opengrep-isolated-scan-plan.md`、`.omx/specs/deep-interview-codeql-compile-sandbox.md`。
- **strict-zero 决策**：完整 CodeQL 首版仍以五语言全绿为总计划口径；当前 compile-sandbox 切片只以 C/C++ 闭环为完成。LLM/自动候选命令必须 validator-gated 且只能在沙箱内执行；build plan、指纹和证据索引以 DB/task-state 为运行时真源；artifacts/evidence/cache 只作诊断与缓存信号，不替代 CodeQL `database create` 捕获。

### CodeQL compile sandbox

- **是什么**：2026-05-01 新增的 CodeQL C/C++ 建库前置沙箱，是双沙箱架构的第一阶段。它运行 `docker/codeql-compile-sandbox.sh`，在隔离 runner 内探索 C/C++ build command，验证命令安全边界，输出 events/summary/plan/evidence，并把 accepted build plan 持久化为 `rust_codeql_build_plans` 表真源。随后 CodeQL 扫描沙箱（`docker/codeql-scan.sh`）从 DB 读取 plan，在 `codeql database create` 阶段重放该命令。真实 CodeQL CLI 会按 argv 拆分 `--command`，因此持久化命令必须避免 shell-only 复合语法；Makefile 自动路径固定为 `make -B -j2`，CMake 路径先 configure 后重放 `cmake --build ...`。
- **不是什么**：通用 CI/CD 构建平台，也不是把完整 build artifacts 直接喂给 CodeQL 的捷径；artifacts/evidence/cache 只能用于诊断和缓存信号。
- **双沙箱数据流**：编译沙箱 → build plan 候选 → 后端验证 → DB 持久化 → CodeQL 扫描沙箱读取 → 重放构建 → 生成数据库 → 扫描。
- **主要入口**：`backend/src/scan/codeql.rs`、`backend/src/routes/static_tasks.rs`、`backend/src/db/codeql_build_plans.rs`、`docker/codeql-compile-sandbox.sh`、`docker/test-codeql-diagnostics.sh`、`SCANNER_CODEQL_COMPILE_SANDBOX_IMAGE`。

### 智能审计

- **是什么**：AI 驱动的安全审计产品方向。
- **当前状态**：占位/重构过渡。Rust gateway 当前不挂载 `/api/v1/agent-tasks`，runtime 不导出 `agentflow`，前端 `/agent-audit/:taskId` 显示 `InDevelopmentPlaceholder`。`vendor/agentflow-src/` 已删除；`backend/agentflow/` 历史 pipeline/schema 资产、`frontend/src/shared/api/agentTasks.ts` 的历史快照类型和 `/api/v1/system-config/agent-preflight` 仍存在，不能写成“所有相关代码已删除”或“执行链已恢复”。
- **维护提示**：如果要恢复或重建智能审计，先定义新的 route/runtime/runner/frontend contract；不要默认复用旧 AgentFlow runner 执行链。

### Rust gateway

- **是什么**：当前后端运行主线，基于 Rust + Axum，入口是 `backend/src/main.rs`，路由聚合在 `backend/src/routes/mod.rs`。
- **不是什么**：旧 Python/FastAPI backend；新功能默认不要再以 `backend/app/...` 作为入口。

## 审计任务术语

### `AgentTask` / `AgentEvent` / `AgentFinding` / AgentFlow runner

- **历史背景**：这些是旧 AgentFlow 智能审计执行链的核心对象。
- **当前状态**：后端主路由不再挂载 `/api/v1/agent-tasks`，runtime 不再导出 `agentflow`；前端任务详情路由占位。代码库仍保留 AgentFlow pipeline/schema 资产、前端历史快照类型和部分兼容/聚合字段，但不再保留 `vendor/` 下的 AgentFlow source，也不再保留前端旧 `/agent-tasks` CRUD/report API 调用。
- **维护提示**：处理相关引用前先确认它是活跃执行入口、兼容数据字段、测试资产还是待清理残留；不要基于记忆直接批量删除。

### Opengrep runner

- **是什么**：执行静态审计规则扫描的隔离 runner；`docker-compose.yml` 中的 `opengrep-runner` 只是 `runner-build` profile 镜像构建目标，默认启动不会保留服务容器。
- **不是什么**：旧多引擎静态审计调度器。
- **主要入口**：`docker/opengrep-runner.Dockerfile`、`docker/opengrep-scan.sh`、`backend/src/scan/opengrep.rs`；backend 按任务动态创建临时 runner 容器，任务结束后删除。

### agent preflight

- **是什么**：`/api/v1/system-config/agent-preflight`，当前仍存在于 `backend/src/routes/system_config.rs`，用于按 LLM 配置优先级做连接测试并检查 runner readiness。
- **当前状态**：保留为智能审计配置门禁。若 LLM 通过但 runner 未配置，响应会以 `runner_missing` 类原因说明智能审计初始化失败。
- **不是什么**：完整 AgentTask 创建或执行 API；当前 Rust gateway 不挂载 `/api/v1/agent-tasks`。

### LLM config set

- **是什么**：系统配置中的 schema v2 多 provider 配置表，公开形态是 `schemaVersion: 2`、`rows[]`、`latestPreflightRun`、`migration`；每行有稳定 id、priority、enabled、provider、baseUrl、model、密钥存在状态、高级参数和 latest preflight 状态。
- **不是什么**：旧版单对象 `llmConfig` 响应，也不是前端本地状态；后端 helper 负责迁移、归一、密钥保留/脱敏和 fallback 分类。
- **维护提示**：公开响应只能暴露 `hasApiKey` 等元数据，不能返回明文 API key；编辑时空 key 表示按 row id 保留旧密钥。设置页顶部"保存并验证"走 `/system-config/test-llm/batch`，只读取已保存配置，批量持久化 passed/failed/missing_fields 状态；创建智能审计仍走 agent preflight。

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
