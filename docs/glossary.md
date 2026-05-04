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

- **是什么**：当前稳定主线由 Opengrep 承担的规则扫描体验，产品层显示为“静态审计”。Opengrep 默认使用 Dockerfile runner 容器，也可以在高级配置里把单次任务切到 `opengrep_sandbox=oci_cubesandbox` 的 OCI CubeSandbox 模板。CodeQL 隔离扫描已有基础骨架：C/C++ 使用 CubeSandbox CodeQL capture 闭环，Python/JavaScript-TypeScript/Java 可通过显式 `languages` payload 在 CubeSandbox 内进入 `build-mode=none`，Go 进入 `build-mode=autobuild`。
- **不是什么**：历史多引擎静态审计集合；退役兼容、防回归测试或旧前端 API 残留不应重新成为当前入口。CodeQL 计划也不是把旧多引擎路由复活。
- **主要入口**：`backend/src/routes/static_tasks.rs`、`frontend/src/shared/api/opengrep.ts`、`frontend/src/pages/StaticAnalysis.tsx`。


### CodeQL 隔离扫描计划

- **是什么**：`plan/codeql_security/codeql_opengrep_isolated_scan_plan.md` 中规划并已开始落地的静态审计扩展：在静态审计/Opengrep 产品入口下增加 `engine="codeql"`，但使用 CubeSandbox CodeQL 模板、`rules_codeql` 查询资产、SARIF 解析和项目级 build plan 固化机制。C/C++ 走 CubeSandbox capture + DB-backed build plan；Python/JavaScript-TypeScript/Java 走 `build-mode=none`；Go 走 `build-mode=autobuild`。
- **不是什么**：Opengrep runner 的增强阶段，也不是旧多引擎静态审计路由复活。当前语言分流和 C/C++ CubeSandbox 切片不等于完整五语言首版。
- **主要计划入口**：`plan/codeql_security/codeql_opengrep_isolated_scan_plan.md`、`.omx/specs/deep-interview-codeql-opengrep-isolated-scan-plan.md`、`.omx/specs/deep-interview-codeql-compile-sandbox.md`。
- **strict-zero 决策**：完整 CodeQL 首版仍以五语言全绿为总计划口径；当前 CubeSandbox 切片只以 C/C++ 闭环为完成。LLM/自动候选命令必须 validator-gated 且只能在沙箱内执行；build plan、指纹和证据索引以 DB/task-state 为运行时真源；artifacts/evidence/cache 只作诊断与缓存信号，不替代 CodeQL `database create` 捕获。
- **查询资产来源**：`backend/assets/scan_rule_assets/rules_codeql/{c,cpp,python}` 已包含真实 `.ql` / `.qll` 查询文件，不再是占位目录。三类资产均来自官方 `github/codeql` 仓库，并在各语言 README 中记录 `https://v6.gh-proxy.org/https://github.com/github/codeql` 镜像 URL、source commit、MIT license 和上游路径；请求 CodeQL `cpp` 语言时后端会同时物化 `c` 与 `cpp` 查询包以覆盖 C/C++ 统一 extractor。

### CodeQL CubeSandbox

- **是什么**：CodeQL 扫描的当前主执行沙箱。后端通过 `backend/src/scan/codeql_cubesandbox.rs` 把源码、查询资产和 build plan 打包送入 CubeSandbox CodeQL 模板，在 envd Connect-RPC `/process.Process/Start`（Basic auth `root`、framed `application/connect+json`）中执行 `codeql database create` / `database analyze`；workspace archive 等大 payload 先通过 envd `/files` multipart 写入 `/tmp/argus-payload-<uuid>.b64` 再被 Python 读取，绕过 `/bin/sh -c` 的 argv 上限。只有该捕获验证完成后，后端才把 accepted build plan 持久化为 `rust_codeql_build_plans` 表 active accepted 真源。项目已有 `autogen.sh`、`configure`、CMake 或 Makefile 时优先生成项目级 build plan；配置位于子目录时 build plan 的 `working_directory` 固定到该项目根，LLM 不能用逐文件编译替换已发现的项目配置，manual capture 以全局源码目录作为 CodeQL source root、以项目配置目录作为 `trace-command --working-dir`。Makefile 自动路径固定为 `make -B -j2`。源码归档会在 tar header 中恢复常见构建脚本执行位，避免沙箱解包后 `autogen.sh` / `git-version-gen` 权限丢失。缺依赖时，后端只在 `CODEQL_ALLOW_NETWORK_DURING_BUILD=true` 且安装命令通过 allowlist validator 后，在当前 CubeSandbox 中执行安装并把 `dependency_install_commands` 固化到 sticky plan evidence。apt/apt-get 安装会先按 `oci/cubesandbox/codeql-cpp.Dockerfile` 的运行时镜像策略直接重建 `/etc/apt/sources.list` 到 HTTP Debian/security 源，`apt-get update` 会按 Aliyun、TUNA、USTC、官方源顺序短超时探测，并禁代理、设置 apt 重试/30 秒超时/ForceIPv4，且用 `timeout 300s` 包住单条安装命令，避免官方源不可达或过慢导致依赖安装卡住；envd process 请求至少允许 900 秒，避免长安装被客户端提前断开。
- **不是什么**：通用 CI/CD 构建平台，也不是把完整 build artifacts 直接喂给 CodeQL 的捷径；artifacts/evidence/cache 只能用于诊断和缓存信号。
- **数据流**：源码/查询/build plan 打包 → CubeSandbox CodeQL 模板 → `database_create` 捕获验证 → `database_analyze` → SARIF → DB sticky plan 持久化/复用 → findings。
- **前端证据**：CodeQL 进度接口返回 typed exploration events，仅 CodeQL-only 静态审计详情页的 `CodeQL 编译探索` 模块展示复用检查、LLM reasoning summary、沙箱命令、stdout/stderr、exit code、dependency signal、dependency install、捕获验证、reset/cancel 和脱敏状态；OpenGrep-only 详情页不展示 `CodeQL 编译探索` 模块。CodeQL 专用详情页不再额外渲染独立的 `执行进度` 或 `LLM 推理过程` SSE 面板，漏洞列表表格在自身模块内提供横向滚动来查看右侧列。后端会在 saved system-config LLM 可用时请求结构化 build plan JSON，并在 validator 通过后交给 CubeSandbox；候选命令失败时，CubeSandbox 输出会脱敏后作为 `previous_failures` 输入下一轮 LLM prompt。无配置、请求失败或解析失败会记录原因并使用 deterministic fallback 候选继续捕获验证。多命令 manual plan 通过 `database init` + shell-wrapped `trace-command` + `finalize` 捕获完整 build script。
- **主要入口**：`backend/src/scan/codeql_cubesandbox.rs`、`backend/src/scan/codeql.rs`、`backend/src/routes/static_tasks.rs`、`backend/src/db/codeql_build_plans.rs`、`oci/cubesandbox/codeql-cpp.Dockerfile`、`scripts/cubesandbox-quickstart.sh`。

### CubeSandbox 模板自动构建（template provisioner）

- **是什么**：2026-05-03 引入的后端状态机，最初为 CodeQL C/C++ 扫描自动构建可复用的 CubeSandbox 模板，2026-05-04 扩展到 Opengrep 模板。`CUBESANDBOX_TEMPLATE_ID` 仍是 CodeQL 可选覆写；Opengrep 使用独立的 `CUBESANDBOX_OPENGREP_TEMPLATE_ID` 可选覆写。未设置时后端分别调用 `scripts/cubesandbox-quickstart.sh provision-codeql-cpp-template` 或 `provision-opengrep-template`，串接 `configure-docker-mirror → start-local-registry → build-*image → create-*template → watch-template`，watch 终态后将 `template_id`、`artifact_id`、`status`、`build_log_tail` 写入 `rust_cubesandbox_templates` 表；后续扫描按 template kind 取 DB active ready 记录。当前 Opengrep 路径使用内部 kind `opengrep_dedicated`，公共 `/opengrep` JSON 仍保留 `kind: "opengrep"` 并用 `recordKind` 暴露存储 kind；历史 `kind='opengrep'` 行保留但不作为当前模板来源。状态机生命周期：`pending → building → ready / failed / invalidated`，同 kind 同时只允许一条 active（部分唯一索引保证）。
- **不是什么**：CubeSandbox 控制面 / VM 自身的安装器（VM/QEMU 仍由 host 的 `cube-sandbox-oneclick` systemd unit 拉起），也不是替代 `oci/cubesandbox/codeql-cpp.Dockerfile` 或 `oci/cubesandbox/opengrep.Dockerfile`：provisioner 只是把镜像构建 + 模板注册的串行 helper 调用纳入后端编排和状态反馈。
- **HTTP API**：`GET /api/v1/cubesandbox/templates/codeql-cpp` 与 `GET /api/v1/cubesandbox/templates/opengrep`（状态）、`POST .../provision`（触发）、`POST .../invalidate`（标记失效以便重建）、`GET .../stream`（SSE 推送状态变更和 build log）。`/opengrep` 是兼容路由族，不代表当前 DB kind 仍是历史 `opengrep`。
- **前端入口**：CodeQL 模板有 `frontend/src/pages/static-analysis/CodeqlExplorationPanel.tsx` 顶部状态卡（就绪 / 构建中 / 失败 / 未构建）+ 立即构建 / 重建模板（带二次确认）/ 查看日志按钮；模板未就绪时禁用「重置并重新探索」。Opengrep 模板由后端在用户选择 `OCI CubeSandbox 沙箱` 时按需确保，目前前端只在 `StaticEngineConfigDialog` 暴露执行方式选择，不展示独立模板状态卡。Hook 与 API 客户端：`frontend/src/hooks/useCodeqlTemplateStatus.ts`、`frontend/src/shared/api/cubesandboxTemplates.ts`。
- **运维约束**：自动构建仅在 `CUBESANDBOX_API_BASE_URL` / `CUBESANDBOX_DATA_PLANE_BASE_URL` 指向 `localhost`/`127.0.0.1`/`::1`/`host.docker.internal` 之一时启用（其它远端 URL 由 `should_run_local_lifecycle` 拒绝）；helper SSH 用 `CUBE_SSH_HOST=host.docker.internal` 当 URL 走 docker host gateway。
- **主要入口**：`backend/src/runtime/cubesandbox/template_provisioner.rs`、`backend/src/db/cubesandbox_templates.rs`、`backend/src/routes/cubesandbox_templates.rs`、`backend/src/runtime/cubesandbox/client.rs`、`backend/src/runtime/cubesandbox/helper.rs`、`oci/cubesandbox/{codeql-cpp,opengrep}.Dockerfile`、`scripts/cubesandbox-quickstart.sh`。

### 沙箱管理页

- **是什么**：开发测试导航组里的 `/sandbox-management` 页面，用项目管理页的共享 `DataTable` 视觉查看 CubeSandbox 模板记录和 `cubesandbox-tasks` 状态。模板数据来自 `GET /api/v1/cubesandbox/templates`，沙箱状态来自只读的 `/api/v1/cubesandbox-tasks?limit=50`。
- **不是什么**：通用沙箱实例控制台、项目/扫描清理页或 containerd 垃圾回收入口。它不删除运行中 sandbox 实例、不删除 task 记录、不删除项目/扫描结果，也不对泛 containerd 内容做清理。
- **操作边界**：删除与清空只作用于 `status='failed'` 的模板记录及其 CubeMaster template_id；直接删除非 FAILED 记录应返回 HTTP 409。页面上的“重置 CodeQL / 重置 OpenGrep”只调用既有 `/invalidate` 路由标记 active 模板记录失效，以便后续重建，不是 READY 模板删除。
- **主要入口**：`frontend/src/pages/SandboxManagement.tsx`、`frontend/src/pages/sandbox-management/SandboxTemplatesTable.tsx`、`frontend/src/shared/api/cubesandboxTemplates.ts`、`frontend/src/shared/api/cubesandboxTasks.ts`、`backend/src/routes/cubesandbox_templates.rs`、`backend/src/db/cubesandbox_templates.rs`。

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

- **是什么**：执行静态审计规则扫描的隔离 runner。默认路径是 `docker/opengrep-runner.Dockerfile` 构建的临时 Docker 容器；静态审计 Opengrep 高级配置也可选择 `OCI CubeSandbox 沙箱`，由独立 Debian slim base 的 `oci/cubesandbox/opengrep.Dockerfile` 构建专属模板并通过 `backend/src/scan/opengrep_cubesandbox.rs` 执行同一 `opengrep-scan` 包装器。当前 CubeSandbox 模板记录 kind 为 `opengrep_dedicated`，不复用 CodeQL/sandbox-code 镜像或历史 `opengrep` 行。
- **不是什么**：旧多引擎静态审计调度器，也不是 CodeQL 扫描主路径；CubeSandbox 选项不是默认值，未传或未知 `opengrep_sandbox` 仍回落到 Dockerfile 容器。
- **主要入口**：`docker/opengrep-runner.Dockerfile`、`docker/opengrep-scan.sh`、`backend/src/scan/opengrep.rs`、`backend/src/scan/opengrep_cubesandbox.rs`、`oci/cubesandbox/opengrep.Dockerfile`、`frontend/src/components/scan/create-scan-task/StaticEngineConfigDialog.tsx`；backend 按任务动态创建临时 runner 容器或 CubeSandbox sandbox，任务结束后清理。

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
