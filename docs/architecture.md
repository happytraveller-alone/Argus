# Argus 开发者架构指南

> 2026-04-30 更新：本仓库当前是 slim-source 形态，运行主线为 Rust/Axum backend、React/Vite frontend、Opengrep 静态审计。历史 Python/FastAPI 和已退役静态引擎链路若仍出现在归档或兼容测试中，按退役背景处理，不作为新功能入口。
>
> 2026-04-30 实施补充：CodeQL 隔离扫描已进入基础实施阶段：后端已有 `engine="codeql"` 静态任务骨架、`rules_codeql` 查询资产发现、CubeSandbox 执行入口和 SARIF 解析基础。它仍不是完整首版；五类语言端到端全绿前只能称为里程碑基础能力。
>
> 2026-05-01/02 CodeQL CubeSandbox 切片：当前 C/C++ CodeQL 任务主路径使用 CubeSandbox 模板执行 CodeQL capture/analyze。后端生成或复用 project-level build plan，在同一个 CubeSandbox CodeQL/glibc 环境内运行 `codeql database create` 与 `database analyze`，并把 accepted build plan / fingerprint / evidence index 持久化为 DB (`rust_codeql_build_plans` 表) 真源。
> 
> Build recipe 必须可被 CubeSandbox 内的 CodeQL capture 观察到（例如 Makefile 使用 `make -B -j2`）。Artifacts/evidence/cache 只作诊断与缓存信号，不替代 CodeQL `database_create` 捕获。
>
> 2026-05-02 CodeQL 语言分流补充：CodeQL 任务现在会读取创建 payload 中的 `languages`。显式 `python`、`javascript-typescript`、`java` 在 CubeSandbox 内走 `build-mode=none`；显式 `go` 走 `build-mode=autobuild`；显式或默认 `cpp` 走 CubeSandbox C/C++ capture + DB-backed build plan。前端创建静态审计时会把项目已识别语言归一化后传给 CodeQL API。
>
> 2026-05-02 CodeQL LLM/编译探索证据补充：C/C++ CodeQL 任务的进度接口现在返回结构化 exploration events，前端仅在 CodeQL-only 静态审计详情页展示构建方案复用检查、CubeSandbox 命令、捕获验证、reset 和 cancel 证据；OpenGrep-only 详情页不展示 `CodeQL 编译探索` 模块。项目级 sticky build plan 只在 CubeSandbox CodeQL 完成 `database_create` 捕获验证后才持久化为 active accepted；普通构建成功不能替代最终 CodeQL 捕获证明。每个项目/语言最多保留一个 active accepted plan，用户可通过显式 reset/re-explore 清除后重新探索。
>
> 2026-05-03 CubeSandbox 模板自动构建与 envd 协议修正：新增 `rust_cubesandbox_templates` 表 + `backend/src/runtime/cubesandbox/template_provisioner.rs` 状态机 + `backend/src/routes/cubesandbox_templates.rs` HTTP 路由（`/api/v1/cubesandbox/templates/codeql-cpp{,/provision,/invalidate,/stream}`）。`CUBESANDBOX_TEMPLATE_ID` 降级为可选覆写：未设置时由后端通过 `scripts/cubesandbox-quickstart.sh provision-codeql-cpp-template` 自动构建（configure-docker-mirror → start-local-registry → build-codeql-cpp-image → create-codeql-cpp-template → watch-template），完成后 template_id 写回数据库供后续扫描复用，前端 CodeqlExplorationPanel 顶部展示「就绪 / 构建中 / 失败 / 未构建」状态卡 + 立即构建/重建模板按钮 + SSE 日志。同时修正 envd 通信：之前的 `POST /process` 路径在 envd 0.2.0 是 404，正确路径是 Connect-RPC `/process.Process/Start`，需要 `Authorization: Basic <base64("root:")>` 头 + framed body（`Content-Type: application/connect+json`），`backend/src/runtime/cubesandbox/client.rs` 重写解析 streamed `ProcessEvent`（start/data/end）。大 payload（multi-MB workspace archive）改为先通过 envd `/files` multipart 上传到 `/tmp/argus-payload-<uuid>.b64`、Python 从文件读，绕过 argv 上限。WSL2 dev 部署下 backend 服务改为 `network_mode: host` 直连 host loopback 上的 QEMU usermode 端口；DATABASE_URL/REDIS_URL/CUBESANDBOX_*_URL 全部走 127.0.0.1，frontend 通过 `host.docker.internal:18000` 命中 backend。
>
> 2026-05-03 CodeQL 查询资产补充：`backend/assets/scan_rule_assets/rules_codeql` 现在为 `c`、`cpp`、`python` 提供真实查询包，不再是占位目录。C/C++ 资产来自官方 `github/codeql` 仓库的 C/C++ security queries；Python 资产来自同一官方仓库的 Python security queries。所有语言 README 都记录镜像来源 `https://v6.gh-proxy.org/https://github.com/github/codeql`、固定 commit 和 MIT license；`codeql.rs` 在请求 `cpp` 时会同时物化 `c` 与 `cpp` 查询资产，以覆盖 CodeQL 的 C/C++ 统一 extractor。
>
> 2026-05-04 OpenGrep CubeSandbox 补充：Opengrep 默认仍走 Dockerfile runner 动态容器；静态审计高级配置新增 `opengrep_sandbox`，可选 `dockerfile_container` 或 `oci_cubesandbox`。选择 OCI CubeSandbox 时，后端使用 `backend/src/scan/opengrep_cubesandbox.rs` 把源码与已物化规则打包进当前 Opengrep CubeSandbox 模板，通过同一 envd Connect-RPC 执行 `opengrep-scan`，并把 results/summary/log/stdout/stderr 写回原有静态任务 workspace。公共模板 API 仍是 `/api/v1/cubesandbox/templates/opengrep/*` 且 JSON `kind` 仍为 `"opengrep"`，但当前 DB 记录 kind 是 `opengrep_dedicated`（响应另有 `recordKind`）；历史 `kind='opengrep'` 记录不迁移、不回填、也不被当前路径复用。模板镜像定义在 `oci/cubesandbox/opengrep.Dockerfile`，使用独立 Debian slim base，不复用 CodeQL 的 `sandbox-code` base；`CUBESANDBOX_OPENGREP_TEMPLATE_ID` 是可选覆写，若设置必须指向该专属镜像构建出的模板。
>
> 2026-05-02 智能审计过渡状态：当前 Rust gateway 不再挂载 `/api/v1/agent-tasks`，`backend/src/runtime/mod.rs` 也不再导出 `runtime/agentflow`；前端 `/agent-audit/:taskId` 已改为 `InDevelopmentPlaceholder` 占位。`vendor/agentflow-src/` 删除已提交但尚未推送；`backend/agentflow/` 仅保留历史 pipeline/schema/fixture 资产，`/api/v1/system-config/agent-preflight` 仍作为 LLM 配置与 runner readiness 门禁存在。`backend/src/runtime/intelligent/config.rs` 现在只提供 claw-code 迁移的基础 LLM 配置适配，不代表智能审计任务执行链已恢复。不要把保留的历史资产写成 AgentFlow 执行链已重新接入。

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
- **Database**：PostgreSQL，通过 `sqlx` 访问，主要状态代码在 `backend/src/db/`；CodeQL C/C++ 的 accepted build plan 由 `rust_codeql_build_plans` 表承载，file/task-state 只作状态投影或 fallback。
- **Runner/Sandbox**：Opengrep 默认使用 Docker runner 动态容器执行；静态审计高级配置可把单次 Opengrep 任务切到 OCI CubeSandbox 模板（`opengrep_sandbox=oci_cubesandbox`），但 `dockerfile_container` 仍是默认值。当前 Opengrep CubeSandbox 模板使用 `opengrep_dedicated` 内部 kind 和独立镜像 base；公共 `/opengrep` API/选择器保持兼容。CodeQL 扫描主路径使用 CubeSandbox CodeQL 模板，通过 envd Connect-RPC `/process.Process/Start`（Basic auth 用户 `root`、framed `application/connect+json`）执行 CodeQL capture/analyze；大 workspace 通过 envd `/files` multipart 上传后引用文件路径，避免 argv 上限。Docker runner preflight 只验证默认 Opengrep runner；CubeSandbox readiness 归 CubeSandbox 配置、模板镜像和 smoke 检查。`docker-compose.yml` 中的 runner service 仅作为 `runner-build` profile 镜像构建目标，默认启动不保留 runner service 容器。历史 AgentFlow runner service 当前不在 compose 主线中。

如果只记一句话：**Argus 把一个 ZIP 项目归档成 `Project`，再围绕它启动静态审计，并把结果汇总回前端；智能审计执行链当前处于占位/重构过渡，仅基础 LLM 配置适配已开始落地。**

## 审计模式

### 静态审计

当前稳定静态审计主线仍是 **Opengrep**，默认执行方式仍是 Dockerfile runner 动态容器。创建静态审计时，Opengrep 高级配置会把 `opengrep_sandbox` 传给后端：`dockerfile_container` 保持原默认路径，`oci_cubesandbox` 使用当前 `opengrep_dedicated` CubeSandbox 模板记录执行同一 `opengrep-scan` 包装器；公共选择器和生命周期 API 仍命名为 `opengrep`。CodeQL 隔离扫描已有基础骨架：`StaticTaskRecord.engine` 可分流 `codeql`，查询资产位于 `backend/assets/scan_rule_assets/rules_codeql`。其中 `c`、`cpp`、`python` 已包含来自官方 `github/codeql` 仓库的真实安全查询文件；README 以 `https://v6.gh-proxy.org/https://github.com/github/codeql` 镜像 URL 记录来源、commit 和 license。

**CodeQL CubeSandbox 架构**（2026-05-02 C/C++ 切片）：

1. 后端为 CodeQL 任务解析语言、物化 `rules_codeql` 查询资产，并生成或读取 project-level sticky build plan。
2. `backend/src/scan/codeql_cubesandbox.rs` 把源码、查询和 build plan 打包后送入 CubeSandbox 模板（>32KB 脚本通过 envd `/files` multipart 预上传），通过 envd Connect-RPC `/process.Process/Start` 运行 CodeQL CLI。
3. CubeSandbox 内执行 `codeql database create` / `database analyze`，输出 events、summary 和 SARIF；后端解析 SARIF 并写回现有 `StaticFindingRecord`。
4. 只有 CubeSandbox CodeQL `database_create` 捕获验证成功后，后端才把 C/C++ build plan 持久化为 `rust_codeql_build_plans` active accepted 运行时真源。

CodeQL C/C++ 任务进度除 legacy logs 外，还会投影 typed exploration events 到 `/static-tasks/codeql/tasks/{task_id}/progress?include_logs=true`。前端只有在详情路由携带显式 `codeqlTaskId`、且没有 `opengrepTaskId` 时，才把 `StaticAnalysis` 判定为 CodeQL-only 并展示 LLM/沙箱/捕获验证时间线；单独的 `engine=codeql` 只作为表格/筛选 URL 状态，不会把 OpenGrep 详情页升级成 CodeQL 编译探索页。`CodeqlScanDetail` 是专用 CodeQL 详情入口。CodeQL-only 详情左侧 6/10 展示漏洞列表，右侧 4/10 展示可自动跟随最新事件且支持手动滚动的编译探索历史，并提供 CodeQL 任务中止和项目级 build plan reset/re-explore 操作。所有 stdout/stderr、LLM response、事件 payload 和展示证据进入 task-state 前会做 token/API-key 形态脱敏。

当前 C/C++ 探索由后端拥有 LLM reasoning contract：有可用 saved system-config LLM 时，后端会调用 LLM 生成结构化 build plan JSON，并用 `backend/src/scan/codeql.rs` 的同一套命令 validator 过滤后再交给 CubeSandbox；每个候选命令都在同一个 CubeSandbox 会话中执行，失败的 stdout/stderr、exit code、dependency signal 和 failure category 会作为 `previous_failures` 进入下一轮 LLM prompt，而不是让静态任务立即失败。无可用 LLM、LLM 请求失败或响应无法解析时，事件流会记录失败原因，并使用 deterministic fallback 候选命令继续进入 CubeSandbox 捕获验证。已存在的项目构建配置优先于逐文件编译：`autogen.sh`/`configure`/CMake/Makefile 会生成项目级 build plan，配置位于子目录时 `working_directory` 固定到该项目根，LLM 不能用逐文件 `cc -c` 计划替换已发现的项目配置；只有无配置时才回退到单文件 `cc -c`。最终 manual capture 仍以全局源码目录作为 CodeQL source root，但 `trace-command --working-dir` 指向项目配置目录，让 CodeQL 观察全局源码中的真实项目构建。源码进入 CubeSandbox 前会在 tar header 中恢复常见构建脚本执行位（如 `autogen.sh`、`configure`、`git-version-gen`），避免上传/解压链路丢失 Unix mode 后让 LLM 绕行猜 chmod。当 CubeSandbox 输出证明缺少依赖且 `CODEQL_ALLOW_NETWORK_DURING_BUILD=true` 时，后端只允许包管理器安装类命令在当前 CubeSandbox 会话中执行；apt/apt-get 命令会先套用 OCI CodeQL 镜像同源的 Debian apt 镜像策略（禁用易超时的 CRAN/R/NodeSource 源，并直接重建 `/etc/apt/sources.list` 到 HTTP Debian/security 源，`apt-get update` 会按 Aliyun、TUNA、USTC、官方源顺序短超时探测，避免单个官方源或镜像不可达/过慢，同时禁用代理、设置 apt 重试/30 秒超时/ForceIPv4），并用 `timeout 300s` 包住单条依赖安装命令，随后重试原构建命令，并把接受的 `dependency_install_commands` 随 sticky build plan evidence 持久化供后续 capture 复用。envd process 请求超时至少 900 秒，与沙箱内构建/依赖安装超时对齐，避免客户端 120 秒提前断开长安装。CubeSandbox 模板会记录每轮 reasoning summary、命令、stdout/stderr、exit code、dependency signal 和 failure category；manual 多命令计划通过 `codeql database init`、一次 shell-wrapped `trace-command`、`finalize` 捕获，让 CodeQL 观察完整 build script，而不是只重放第一条命令。CodeQL interrupt route 会通过 task-id keyed registry 尝试删除 active CubeSandbox，再写入取消/清理证据。

SARIF 解析映射到现有静态 finding 形态。当前可执行能力包括：C/C++ CubeSandbox capture 闭环、以及 Python/JavaScript-TypeScript/Java/Go 的显式语言 payload 到 CubeSandbox CodeQL build-mode 分流。CodeQL 五类语言真实 CLI 样例端到端全绿前，不得标记为完整首版完成。

**Opengrep sandbox 选择**（2026-05-04）：

1. 前端 `StaticEngineConfigDialog` 只在 Opengrep 高级配置里展示两种执行方式：`Dockerfile 容器` 与 `OCI CubeSandbox 沙箱`。
2. `frontend/src/shared/api/opengrep.ts` 将选择序列化为 `opengrep_sandbox`；后端还兼容旧键 `sandbox` / `sandbox_mode`，未知值回落到 `dockerfile_container`。
3. Dockerfile 默认路径继续使用 `docker/opengrep-runner.Dockerfile` + `docker/opengrep-scan.sh`，按任务创建临时 runner 容器，任务结束删除。
4. CubeSandbox 路径通过 `backend/src/scan/opengrep_cubesandbox.rs` 创建当前 `opengrep_dedicated` 模板沙箱（公共 API 仍是 `/opengrep`），上传源码与规则 tarball，执行模板内的 `opengrep-scan`，再把 results/summary/log/stdout/stderr 写回与 Docker 路径相同的 workspace 输出文件。
5. 任务状态 `extra.opengrep_sandbox` 记录实际执行选择，便于 UI/日志/排障区分。

- 后端路由：`backend/src/routes/static_tasks.rs`
- 前端 API：`frontend/src/shared/api/opengrep.ts`
- 前端结果页：`frontend/src/pages/StaticAnalysis.tsx`
- 任务管理聚合：`frontend/src/features/tasks/services/taskActivities.ts`
- Opengrep runner 脚本：`docker/opengrep-scan.sh`
- Opengrep runner 镜像：`docker/opengrep-runner.Dockerfile`
- Opengrep CubeSandbox 执行模块：`backend/src/scan/opengrep_cubesandbox.rs`
- Opengrep CubeSandbox 模板镜像定义：`oci/cubesandbox/opengrep.Dockerfile`
- CodeQL CubeSandbox 执行模块：`backend/src/scan/codeql_cubesandbox.rs`
- CodeQL 解析/验证模块：`backend/src/scan/codeql.rs`
- CubeSandbox envd Connect-RPC 客户端：`backend/src/runtime/cubesandbox/client.rs`
- CubeSandbox 模板自动构建状态机：`backend/src/runtime/cubesandbox/template_provisioner.rs`
- CubeSandbox 模板 DB 持久化：`backend/src/db/cubesandbox_templates.rs`（`rust_cubesandbox_templates` 表）
- CubeSandbox 模板生命周期 HTTP API：`backend/src/routes/cubesandbox_templates.rs`（`/codeql-cpp/*` 与 `/opengrep/*`）
- 前端模板状态卡 + 立即构建/重建按钮：`frontend/src/pages/static-analysis/CodeqlExplorationPanel.tsx`、`frontend/src/hooks/useCodeqlTemplateStatus.ts`、`frontend/src/shared/api/cubesandboxTemplates.ts`
- CodeQL CubeSandbox 模板镜像定义：`oci/cubesandbox/codeql-cpp.Dockerfile`

基于 Docker runner 的 CodeQL sandbox 镜像构建面已经退役：`docker/` 目录不再保留 `codeql-runner.Dockerfile`、`codeql-scan.sh`、`codeql-compile-sandbox.sh` 或对应诊断脚本。CodeQL 模板镜像仍由 `oci/cubesandbox/` 和 `scripts/cubesandbox-quickstart.sh` 管理，只用于 CubeSandbox 模板创建，不作为 Argus Compose/发布流水线中的 CodeQL runner 镜像。

旧多引擎静态审计链路已经从当前前后端主线删除；不要把退役路由或历史兼容数据当作新增静态引擎的当前入口。CodeQL 是新的隔离例外：它按 `StaticTaskRecord.engine="codeql"`、`rules_codeql`、CubeSandbox CodeQL 模板和 SARIF 到 `StaticFindingRecord` 映射推进，不复活旧多引擎路由。

### 智能审计（占位/重构过渡）

当前智能审计不是可运行的端到端产品主线。代码状态是：

- 后端 API 主路由 `backend/src/routes/mod.rs` 只挂载 system-config、projects、search、skills 和 static-tasks，不挂载 `/api/v1/agent-tasks`。
- 后端 runtime 主导出 `backend/src/runtime/mod.rs` 不包含 `agentflow` 模块；`runtime/intelligent/config.rs` 仅负责把保存的 system-config LLM row 解析成 claw-code 后续 bridge 可消费的安全配置快照。
- 前端 `/agent-audit/:taskId` 路由渲染 `frontend/src/shared/components/InDevelopmentPlaceholder.tsx`。
- `vendor/agentflow-src/` 删除已提交待推送；`backend/agentflow/` 历史 pipeline/schema 资产和 `/api/v1/system-config/agent-preflight` 仍存在，属于过渡期资产或配置门禁，不代表 AgentFlow 执行链已重新接入。
- `frontend/src/shared/api/agentTasks.ts` 当前只保留 `AgentTask` / `AgentFinding` 等历史快照类型，供项目聚合、统一漏洞详情和历史数据展示继续编译；它不再导出旧 `/agent-tasks` CRUD / report API 调用。

因此，新增功能不要从旧 AgentFlow runner 执行路径开始；如果要恢复或重建智能审计，需要沿新的 `runtime/intelligent/` 基础继续补齐 backend route、任务状态、claw-code bridge、runner/工具沙箱和 frontend contract。

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

1. 前端入口是 `frontend/src/components/scan/CreateProjectScanDialog.tsx` 和 `frontend/src/components/scan/CreateScanTaskDialog.tsx`。静态模式当前只暴露 Opengrep 与 CodeQL 两个主引擎，二者在创建入口互斥；CodeQL 创建后以 `engine=codeql` 和 `codeqlTaskId` 路由到同一静态审计详情体验。
2. 前端调用 `frontend/src/shared/api/opengrep.ts`；Opengrep 高级配置会随创建 payload 传 `opengrep_sandbox`，默认 `dockerfile_container`，可选 `oci_cubesandbox`。
3. 后端 `backend/src/routes/static_tasks.rs` 创建任务：默认 Opengrep 调度 `docker/opengrep-scan.sh`；选择 `oci_cubesandbox` 时走 `backend/src/scan/opengrep_cubesandbox.rs` 和内部 `opengrep_dedicated` CubeSandbox 模板（对外仍为 `/opengrep`）；`engine="codeql"` 会把源码、查询资产和 build plan 交给 CubeSandbox CodeQL 模板执行 `database create/analyze`。
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
- `backend/src/scan/opengrep_cubesandbox.rs`
- `docker/opengrep-scan.sh`
- `oci/cubesandbox/opengrep.Dockerfile`
- `frontend/src/components/scan/create-scan-task/StaticEngineConfigDialog.tsx`
- `frontend/src/shared/api/opengrep.ts`
- `frontend/src/pages/StaticAnalysis.tsx`

## 退役与兼容边界

- 旧 Python/FastAPI backend 不是当前运行主线。
- 非 Opengrep 静态引擎路由不应重新接入当前 Rust gateway，除非先有新的计划和迁移说明。
- AgentFlow 智能审计执行链当前未挂载在 Rust gateway/runtime/compose 主线中，`vendor/agentflow-src/` 删除已提交待推送；历史 pipeline/schema 资产和前端历史快照类型仍在，ADR 文档位于 `frontend/docs/decisions/2026-05-01-agentflow-retired.md`。
- 归档文档、历史测试和旧前端 API 文件可能保留旧名词；新增代码和新文档应优先使用当前主线术语。
