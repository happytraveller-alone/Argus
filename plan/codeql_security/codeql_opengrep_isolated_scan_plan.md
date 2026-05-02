# CodeQL 隔离扫描纳入静态审计/Opengrep 入口实施计划（CubeSandbox 架构）

> 文档定位：这是新的 Argus CodeQL 扫描实施计划，面向当前 Rust/Axum 后端、React/Vite 前端、Opengrep Docker runner + CodeQL CubeSandbox 静态审计架构。旧文档 `plan/codeql_security/codeql_platform_deploy.md` 包含过时的 AuditTool/Python/FastAPI 表述，仅作为历史背景，不作为本计划的实现依据。

## CubeSandbox 架构概述

**核心创新**：CodeQL 扫描不走 Docker runner 主路径，而是由 CubeSandbox CodeQL 模板执行 capture/analyze：

1. 后端解析语言、查询资产和 project-level build plan。
2. 后端把源码、查询资产和 build plan 打包发送到 CubeSandbox。
3. CubeSandbox 内使用 CodeQL CLI 执行 `database create` 和 `database analyze`。
4. 后端读取 events/SARIF，并且只在 `database_create` 捕获验证成功后持久化 active accepted build plan。

**关键原则**：
- 数据库是通过 CodeQL 捕获验证后的 build plan、指纹和证据索引的**唯一运行时真源**
- 文件（artifacts、evidence、cache）仅用于诊断和缓存信号
- 构建命令必须是 CodeQL `database create --command` 可按 argv 拆分重放的简单命令
- 不依赖 shell-only 语法（`${...}` 展开、`||`、`;`、管道）

## 1. 结论先行（CubeSandbox 架构）

首版采用 **”静态审计/Opengrep 入口下的新扫描类型 + 后端 engine 完全隔离 + CubeSandbox 执行架构”**：

- 前端仍在当前静态审计/Opengrep 相关入口中创建和查看扫描，满足”放在 Opengrep 中”的产品体验。
- 后端使用独立 `engine=”codeql”`、独立 scan module、CubeSandbox CodeQL 模板、独立规则/查询根目录，满足”与 Opengrep 扫描隔离”。
- 结果、任务进度、finding 状态、AI 分析入口尽量复用现有静态审计体验，避免为首版重做一套并行 UI。
- CodeQL 构建复杂性通过 **CubeSandbox CodeQL capture** 解决：后端生成或复用 DB-backed build plan，把源码/查询/build plan 打包送入 CubeSandbox，在同一 CodeQL/glibc 环境内执行 `database_create` 和 `database_analyze`。
- Build plan、指纹和证据索引的运行时真源是**数据库**，但只有 CubeSandbox CodeQL 完成 `database_create` 捕获验证后才写入 active accepted；文件只作诊断和缓存信号。

## 2. 背景与动机

现有静态审计主线以 Opengrep 为核心，适合无需完整项目编译即可运行的规则扫描。但 CodeQL 的优势在于语义建库与数据流查询，尤其适合需要跨函数、跨文件、跨编译单元分析的漏洞类型。

用户需求的关键点是：

1. CodeQL 要进入当前静态审计体系，而不是外部 CI 示例。
2. CodeQL 必须与 Opengrep 扫描隔离，不能破坏现有 Opengrep 任务、规则、runner 和结果展示。
3. CodeQL 扫描主路径必须通过 **CubeSandbox CodeQL 模板**完成，不经过 Docker runner。
4. CodeQL 查询库/规则加载逻辑要与 Opengrep 规则加载方式一致。
5. 难点不是简单执行 `codeql database analyze`，而是 `database create` 对编译流程敏感，需要：
   - **CubeSandbox CodeQL 模板**：探索项目构建系统、验证候选命令、执行 CodeQL capture/analyze、输出 build plan 候选和 SARIF
   - **后端验证与持久化**：将 accepted build plan、指纹和证据索引持久化到数据库（运行时真源）
   - **CodeQL capture/analyze**：读取 DB-backed build plan、用 CodeQL 编译器重放构建、生成查询数据库、执行扫描

## 3. 当前代码依据

### 3.1 静态任务与结果主线

- `backend/src/routes/static_tasks.rs` 当前暴露 Opengrep 规则、任务、进度、finding、AI 分析相关路由。
- `task_state::StaticTaskRecord` 已包含 `engine` 字段，现有任务创建时写入 `engine: "opengrep"`。
- `task_state::StaticFindingRecord` 承载 finding payload，适合作为 CodeQL SARIF 结果的统一展示格式。
- `update_scan_progress(...)` 已支持 progress、stage、message、logs，可承接 CodeQL 更多阶段。

### 3.2 Opengrep 规则加载模式

- `backend/src/scan/opengrep.rs` 使用 `OPENGREP_ENGINE = "opengrep"`。
- 规则资产通过 `scan_rule_assets::load_assets_by_engine(state, OPENGREP_ENGINE, ...)` 加载。
- `materialize_rule_assets(...)` 将 DB/assets 中的规则写到 runner workspace，再由 runner 脚本加载。
- `backend/src/db/scan_rule_assets.rs` 当前只发现 `backend/assets/scan_rule_assets/rules_opengrep`，并分类为 `engine="opengrep"` / `source_kind="internal_rule"`。

### 3.3 Docker runner 模式

- `docker/opengrep-runner.Dockerfile` 构建独立 Opengrep runner 镜像。
- `docker/opengrep-scan.sh` 是 runner 入口，负责规则目录准备、扫描、JSON 输出、summary 输出和自检。
- `backend/src/runtime/runner.rs` 通过 `RunnerSpec` 创建容器，挂载共享 workspace，捕获 stdout/stderr，等待 completion summary，并写入 `meta/runner.json`。

### 3.4 当前缺口（CubeSandbox 架构需求）

- 没有 `engine="codeql"` 的规则资产发现与加载。
- 没有 CodeQL CubeSandbox 模板执行链路。
- 没有 SARIF 到 `StaticFindingRecord` 的解析器。
- 现有 Docker runner 只服务 Opengrep；CodeQL CubeSandbox 需要结构化事件流。
- 没有项目级 CodeQL build plan 的数据库存储、指纹和复用机制。
- 没有 CubeSandbox scan result、build plan 与后端持久化之间的闭环。

## 4. 外部 CodeQL 事实约束

根据 GitHub CodeQL CLI 文档与本轮 strict-zero deep-interview 决策：

- `codeql database create` 支持 `--build-mode=none|autobuild|manual`。其中 `none` 适用于部分无需构建语言；`autobuild` 和 `manual` 适用于需要构建或可自动构建的语言；传入 `--command` 时即代表手动构建命令。
- `codeql database analyze` 可输出 SARIF，适合作为平台统一解析入口。
- CodeQL SARIF 输出字段可能随版本增加，解析器必须对可选字段保持宽容。
- 自定义 CodeQL 查询应作为 query pack/query suite 管理，并通过 CLI 分析数据库。
- 本计划首版验收必须覆盖 JavaScript/TypeScript、Python、Java、C/C++、Go 五类语言；可按语言分里程碑推进，但五类语言未全绿前不得声明首版完成。

这些事实决定了 Argus 不能只设计“单命令扫描”，而必须设计建库、构建、分析、日志反馈与 build plan 固化的完整闭环。

## 5. 目标架构（CubeSandbox）

```text
Frontend Static Audit / Opengrep Surface
        |
        | create task: engine=codeql
        v
backend/src/routes/static_tasks.rs
        |
        | dispatch by engine
        v
backend/src/scan/codeql.rs + backend/src/scan/codeql_cubesandbox.rs
        |
        | package source/query/build plan
        v
CubeSandbox CodeQL template
        |
        | codeql database create
        | codeql database analyze -> results.sarif
        v
rust_codeql_build_plans table (runtime truth after capture)
        v
Backend scan watcher + SARIF parser
        |
        v
StaticTaskRecord + StaticFindingRecord
        |
        v
Frontend task/finding display consistent with Opengrep
```

**关键数据流**：
1. CubeSandbox → `build-plan.json` 候选和 CodeQL capture 事件 → 后端验证 → DB 持久化
2. DB → 后续 CubeSandbox scan input → 重放构建 → SARIF → findings

## 6. 产品/API 边界

### 6.1 推荐边界

首版不要把 CodeQL 做成 Opengrep 的后处理，也不要把 CodeQL 做成完全脱离静态审计的新顶级系统。推荐边界：

- 用户在静态审计创建入口选择扫描引擎：`Opengrep` 或 `CodeQL`。
- 前端任务列表、任务详情、finding 表格保留一致布局。
- 后端 task record 用 `engine` 区分：`opengrep` 与 `codeql`。
- CodeQL 规则、CubeSandbox 执行、配置、build plan、SARIF 解析完全独立。

### 6.1.1 前端首版验收边界

当前静态审计前端首版只保留两个主引擎：`Opengrep` 与 `CodeQL`。被删除或退休的静态引擎不得重新出现在创建入口、静态审计详情页、finding 详情路由或本轮相关测试契约中。

前端验收要求：

- 创建静态审计时必须展示 Opengrep 与 CodeQL 选择项。
- Opengrep 与 CodeQL 是互斥选项；点选任一引擎时，另一引擎必须自动取消。
- 选择 Opengrep 时调用 Opengrep 静态任务创建 API，并路由到 `/static-analysis/:taskId?opengrepTaskId=...`。
- 选择 CodeQL 时调用 CodeQL 静态任务创建 API，并路由到 `/static-analysis/:taskId?codeqlTaskId=...&engine=codeql`。
- `/static-analysis/:taskId` 必须按 query 中的 `engine=codeql` 和 `codeqlTaskId` 加载 CodeQL 任务与 findings；没有显式 task id 时，路径 task id 可作为对应 engine 的兼容兜底。
- CodeQL finding 详情页复用 Opengrep 的静态 finding 详情布局、状态切换、代码定位、全文查看与追踪信息展示模型；差异只体现在来源标签为 `静态审计 · CodeQL` 以及 CodeQL API 路由。

### 6.2 路由策略

可选两种实现，优先推荐 A：

#### A. 保持现有静态任务路径，按 engine 参数分流（推荐）

- `POST /static-tasks/tasks` 支持 `engine: "opengrep" | "codeql"`。
- `GET /static-tasks/tasks?engine=codeql` 获取 CodeQL 任务。
- `GET /static-tasks/tasks/{task_id}/findings` 继续复用。
- 规则接口新增 engine 过滤或 CodeQL 子路由。

优点：前端改动较小，结果展示一致，符合现有 `StaticTaskRecord.engine`。

#### B. 新增 `/static-tasks/codeql/*` 子路由

- 可读性更强，但容易复制一套 Opengrep 路由。
- 若采用 B，应将共享逻辑抽成 engine-neutral helper，避免重复。

## 7. 规则/查询加载设计

### 7.1 目录约定

新增目录：

```text
backend/assets/scan_rule_assets/
  rules_opengrep/        # 现有 Opengrep 规则
  rules_codeql/          # 新增 CodeQL 查询与套件
    javascript-typescript/
      qlpack.yml
      argus-security.qls
      queries/*.ql
    python/
      qlpack.yml
      argus-security.qls
      queries/*.ql
    cpp/
      qlpack.yml
      argus-security.qls
      queries/*.ql
```

### 7.2 DB 分类

扩展 `scan_rule_assets::classify_rule_asset(...)`：

| 顶层目录 | engine | source_kind | 说明 |
| --- | --- | --- | --- |
| `rules_opengrep` | `opengrep` | `internal_rule` | 现有规则 |
| `rules_codeql` | `codeql` | `internal_query_pack` | 内置 CodeQL query pack/query suite |

后续用户上传 CodeQL query pack 时可用 `source_kind="user_query_pack"`。

### 7.3 Materialize 规则

新增 `backend/src/scan/codeql.rs`：

- `CODEQL_ENGINE = "codeql"`
- `load_query_assets(state, languages)`
- `materialize_query_pack(workspace_dir, assets)`
- `build_database_create_command(...)`
- `build_database_analyze_command(...)`
- `parse_sarif_output(...) -> Vec<StaticFindingRecord>`

保持与 `opengrep.rs` 同样的资产加载思想：DB/assets 是唯一规则来源，临时 scan workspace 是 materialized copy。

## 8. CodeQL CubeSandbox 架构

### 8.1 架构原则

CodeQL 采用 **CubeSandbox CodeQL 模板**实现隔离扫描：

1. 后端负责 C/C++ build plan 生成、复用、reset 和持久化。
2. CubeSandbox 负责在隔离 glibc/CodeQL 环境内创建数据库并执行扫描。
3. Docker CodeQL 脚本仅作为历史诊断或模板构建参考，不是 CodeQL 任务主路径。

### 8.2 CubeSandbox CodeQL 模板

**镜像定义**：`oci/cubesandbox/codeql-cpp.Dockerfile`

**职责**：
- 探索 C/C++ 项目的构建系统（Makefile、CMake、autotools 等）
- 验证候选构建命令的安全性和可执行性
- 在沙箱内执行验证通过的构建命令
- 输出结构化事件流、构建证据、依赖观察和 accepted build plan
- 将 accepted build plan、指纹和证据索引持久化到数据库

**关键约束**：
- 构建命令必须是 CodeQL `database create --command` 可按 argv 拆分重放的简单命令
- 不依赖 shell-only 语法（`${...}` 展开、`||`、`;`、管道）
- Makefile 路径固定为 `make -B -j2`
- CMake 路径先 configure，再持久化 `cmake --build ...` 重放命令

**输出**：
- `events.jsonl`：结构化事件流
- `summary.json`：执行摘要
- `build-plan.json`：accepted build plan（候选）
- `evidence/`：构建证据和诊断信息

### 8.3 CodeQL capture/analyze 执行

**执行位置**：CubeSandbox CodeQL 模板（`oci/cubesandbox/codeql-cpp.Dockerfile`）。

**职责**：
- 从后端接收数据库中已固化的 build plan
- 使用 CodeQL 编译器替代原构建命令，在 `codeql database create` 阶段重放构建过程
- 生成项目的 CodeQL 查询数据库
- 使用 CodeQL 规则对数据库执行扫描
- 输出 SARIF 格式的扫描结果、事件流和摘要

**关键约束**：
- CubeSandbox 模板基础环境使用 Debian/Ubuntu/glibc，不使用 Alpine/musl
- 安装 CodeQL bundle/CLI 到 `/opt/codeql/codeql`
- 安装必要的构建工具集：`bash`, `git`, `python3`, `nodejs/npm`, `make`, `gcc/g++`, `openjdk`, `maven/gradle`
- 工作目录由 CubeSandbox 模板控制
- 内置 self-test：`codeql version`、`codeql resolve languages`

**输出**：
- `results.sarif`：CodeQL 扫描结果
- `summary.json`：扫描摘要
- `events.jsonl`：扫描事件流

新增配置：

```env
CODEQL_MAX_BUILD_INFERENCE_ROUNDS=3
CODEQL_ALLOW_NETWORK_DURING_BUILD=true
CODEQL_LLM_ALLOW_SOURCE_SNIPPETS=true

# CubeSandbox CodeQL scan 配置
CODEQL_SCAN_TIMEOUT_SECONDS=0
CODEQL_RUNNER_MEMORY_LIMIT_MB=8192
CODEQL_RUNNER_CPU_LIMIT=0
CODEQL_THREADS=0
CODEQL_RAM_MB=6144
```

### 8.4 CubeSandbox command contract

后端通过 CubeSandbox envd `/process` 执行封装脚本，向模板传入源码、查询资产、build plan、资源配置和输出路径。模板职责：

1. 探索项目构建系统（检测 Makefile、CMakeLists.txt、configure 等）。
2. 生成或接收候选构建命令并通过验证器。
3. 执行 `codeql database create --command=<validated-command>`。
4. 执行 `codeql database analyze --format=sarifv2.1.0 --output=...`。
5. 记录 `events.jsonl`：探索、数据库创建、分析阶段的事件流。
6. 输出 `build-plan.json`：accepted build plan 候选。
7. 输出 `summary.json`、`results.sarif` 和必要 evidence。
8. 不直接调用 LLM；LLM 推理由后端根据 CubeSandbox 事件驱动。

## 9. CubeSandbox 事件流与 LLM 构建方案推理

### 9.1 为什么需要事件流

CodeQL 建库失败通常不是”扫描规则错误”，而是项目构建失败、依赖缺失、构建系统识别错误、语言选择错误或 monorepo 子目录错误。后端如果只能在执行结束后拿到一坨 stderr，大模型无法稳定迭代构建方案。因此 **CubeSandbox CodeQL 模板**需要输出结构化事件流供后端 watcher 消费。

**职责分离**：
- **CubeSandbox CodeQL 模板**：输出事件流、生成/验证候选 build plan、执行 CodeQL capture/analyze。
- **后端 watcher**：根据事件触发 LLM 推理、持久化 DB-backed build plan、解析 SARIF。

### 9.2 事件文件格式

**CubeSandbox CodeQL 模板**写入：`events.jsonl`（探索、验证、数据库创建和分析阶段）。

每行 JSON：

```json
{
  "ts": "2026-04-30T14:25:00Z",
  "task_id": "...",
  "engine": "codeql",
  "stage": "database_create",
  "event": "command_exit",
  "command_id": "create-db-1",
  "exit_code": 1,
  "message": "mvn: command not found",
  "log_excerpt": "...",
  "artifact": null
}
```

阶段建议：

**CubeSandbox 探索/验证阶段**：
- `extracting`
- `detecting_language`
- `detecting_build_system`
- `validating_candidate_commands`
- `executing_build_attempt`
- `build_failure_observed`
- `llm_inference_requested`
- `build_plan_candidate_written`
- `build_plan_accepted`
- `compile_sandbox_completed` / `compile_sandbox_failed`

**CodeQL capture/analyze 阶段**：
- `loading_build_plan`
- `preparing_queries`
- `database_create`
- `database_analyze`
- `parsing_sarif`
- `scan_completed` / `scan_failed`

### 9.3 后端 watcher（CubeSandbox 协调）

**CodeQL CubeSandbox watcher**（在 `run_codeql_scan_inner(...)` 中）：

- 从数据库读取 build plan 或生成候选 build plan，并传递给 CubeSandbox CodeQL 模板。
- 读取 CubeSandbox 返回的 `events.jsonl`。
- 监控数据库创建和分析进度。
- 解析 SARIF 输出并写入 findings。
- 只有 `database_create` 捕获验证成功后才持久化 accepted build plan。

### 9.4 LLM 推理边界（后端驱动，CubeSandbox 执行）

**重要**：LLM 推理由后端驱动，只用于生成结构化 build plan 候选；CubeSandbox 只执行通过校验的命令，不直接调用 LLM。

LLM 输入：

- 项目语言、文件树摘要、构建文件摘要。
- 当前 build plan 候选。
- CubeSandbox 构建失败事件。
- stdout/stderr 安全摘要。
- 已尝试命令与退出码。

LLM 输出必须是结构化 JSON，禁止自由文本直接执行；结构化候选命令通过校验后可自动在 **CubeSandbox** 内执行：

```json
{
  "decision": "retry_with_manual_build",
  "reason": "detected Maven project and missing dependency cache",
  "commands": [
    "mvn -B -DskipTests package"
  ],
  "working_directory": ".",
  "requires_network": true,
  "confidence": "medium",
  "stop_if_fails": true
}
```

执行前校验（后端/CubeSandbox）：

- 命令数量上限。
- 禁止写 workspace 外路径。
- 禁止 Docker-in-Docker、宿主机挂载、凭据读取。
- 网络首版允许开启，用于依赖安装；仍必须记录网络使用证据。
- LLM 可接收必要源码片段、构建文件和日志；不得发送无关完整仓库。
- 最多 `CODEQL_MAX_BUILD_INFERENCE_ROUNDS` 轮。
- 候选命令必须是 CodeQL `database create --command` 可按 argv 拆分重放的简单命令（不依赖 shell 复合语法）。

## 10. 项目级 CodeQL build plan 固化（CubeSandbox 核心）

### 10.1 存储对象与真源原则

必须新增 `CodeqlBuildPlanRecord` 或等价数据库结构。**数据库是 build plan、指纹和证据索引的唯一运行时真源**；CubeSandbox 产生的文件只能作为临时 artifact 或诊断/缓存信号，不能作为复用依据。

**CubeSandbox 数据流**：
1. CubeSandbox 输出 `build-plan.json` 候选与 capture 事件 → 后端验证 → 持久化到 DB
2. 后续扫描从 DB 读取 build plan → 传入 CubeSandbox → 重放构建

字段建议：

| 字段 | 说明 |
| --- | --- |
| `id` | build plan id |
| `project_id` | 项目 |
| `language` | CodeQL language |
| `target_path` | 扫描子路径 |
| `source_fingerprint` | 源码/构建文件指纹 |
| `dependency_fingerprint` | lockfile/buildfile 指纹 |
| `build_mode` | `none` / `autobuild` / `manual` |
| `commands_json` | manual build commands |
| `working_directory` | 构建工作目录 |
| `query_suite` | 默认 query suite |
| `status` | `candidate` / `verified` / `failed` / `stale` |
| `llm_model` | 生成模型 |
| `evidence_json` | 成功/失败事件摘要，运行时真源在 DB |
| `created_at` / `updated_at` | 时间 |

### 10.2 指纹规则

指纹应覆盖：

- 项目源码 archive id 或 hash。
- 语言集合。
- 构建文件：`pom.xml`, `build.gradle`, `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `Cargo.toml`, `go.mod`, `CMakeLists.txt`, `Makefile` 等。
- 用户选择的 target path。
- CodeQL bundle version。
- query pack sha256。

当指纹不变时直接复用数据库中的 verified build plan；指纹变化时标记 stale 并重新推理。文件 artifact 不参与运行时真源判断。

## 11. SARIF 到 Argus finding 映射

CodeQL `database analyze` 输出 SARIF。后端新增 `parse_sarif_output(...)`：

| Argus 字段 | SARIF 来源 |
| --- | --- |
| `rule.id` / `rule_name` | `runs[].tool.driver.rules[]` 或 result `ruleId` |
| `description` | result `message.text` / `message.markdown` |
| `file_path` | result `locations[].physicalLocation.artifactLocation.uri` |
| `start_line` | region `startLine` |
| `end_line` | region `endLine` |
| `severity` | rule properties `problem.severity` / `security-severity` 映射 |
| `confidence` | 默认 `MEDIUM`，可从 rule metadata 扩展 |
| `cwe` | rule tags 中的 CWE |
| `raw_payload` | 原始 result + rule metadata |

解析器必须：

- 支持 SARIF 可选字段缺失。
- 支持 URI 到项目相对路径的规范化。
- 保留 raw payload 供 AI 分析。
- 对多 run、多 language 聚合。

## 12. 前端体验

### 12.1 创建扫描

在现有静态扫描创建入口增加 engine 选择：

- `Opengrep`：保持当前行为。
- `CodeQL`：显示语言、构建策略、是否允许自动推理、是否允许联网构建、query suite/pack 选择。

默认策略：

- interpreted/no-build 语言优先 `build_mode=none`。
- 编译型语言优先尝试已验证 build plan；没有 plan 时进入推理模式。
- 首版允许 runner 联网安装依赖，并允许 LLM 接收必要源码片段、构建文件和日志；UI/任务详情必须展示该策略。

### 12.2 任务展示

现有任务列表增加 engine badge：

- `Opengrep`
- `CodeQL`

CodeQL 任务进度应显示阶段：

- 准备查询库
- 推理构建方案
- 创建 CodeQL 数据库
- 执行查询
- 解析 SARIF

### 12.3 Finding 展示

沿用 Opengrep finding 表格：

- 严重级别、文件路径、行号、规则、状态、AI 分析入口保持一致。
- CodeQL 特有字段（query id、security severity、precision、tags）放入详情抽屉或 metadata 区。

## 13. 实施阶段（CubeSandbox 架构）

### Phase 0：计划评审与验收边界确认

产物：

- 本计划文档。
- `.omx/specs/deep-interview-codeql-opengrep-isolated-scan-plan.md`（总体规划）。
- `.omx/specs/deep-interview-codeql-compile-sandbox.md`（历史 C/C++ 编译沙箱切片；当前主路径已收敛到 CubeSandbox）。
- 后续 `$ralplan` 生成 PRD 和 test spec。

确认项：

- 是否允许 CubeSandbox 联网（用于依赖安装）。
- LLM 是否可接收源码片段/日志摘要（用于构建方案推理）。
- 首版语言排序（当前 C/C++ 优先，其他语言为后续里程碑）。
- 是否需要人工批准 LLM 生成命令（当前：验证器自动校验后可在沙箱内自动执行）。

### Phase 0.5：C/C++ CubeSandbox 切片（当前实施中）

**目标**：实现 C/C++ 编译探索与 CodeQL 扫描的 CubeSandbox 闭环。

**范围**：
- C/C++ CubeSandbox CodeQL 模板
- DB-backed build plan、指纹和证据索引
- CubeSandbox 事件流与后端 watcher
- CubeSandbox 读取 DB plan 并重放构建
- SARIF 解析到现有静态 finding 流程

**验收**：
- CubeSandbox 成功探索并固化 C/C++ 构建方案
- CubeSandbox 成功重放构建并生成 SARIF
- DB 是 build plan 的运行时真源（文件删除不影响重放）
- Opengrep 行为不回退

**后续语言**：JavaScript/TypeScript、Python、Java、Go 为独立里程碑，不阻塞 C/C++ 切片验收。

### Phase 1：规则资产与 engine 骨架

目标：CodeQL engine 能被平台识别，但不影响 Opengrep。

工作：

- 扩展 `scan_rule_assets` 支持 `rules_codeql`。
- 新增 `backend/src/scan/codeql.rs` 空骨架与单元测试。
- 新增最小 query pack fixture。
- 保证现有 Opengrep asset tests 继续通过，并新增 CodeQL asset tests。

验收：

- `rules_opengrep` 行为不变。
- `rules_codeql` 能导入为 `engine="codeql"`。

### Phase 2：CubeSandbox CodeQL 模板与最小扫描

目标：CubeSandbox CodeQL 模板能对样例项目输出 SARIF。

工作：

- 新增/维护 `oci/cubesandbox/codeql-cpp.Dockerfile`。
- 后端通过 CubeSandbox envd `/process` 执行 CodeQL capture/analyze。
- 后端配置保留资源/超时参数，不把 CodeQL 任务接入 Docker runner preflight。

验收：

- CubeSandbox CodeQL 模板构建成功。
- CubeSandbox 最小自检成功。
- 最小样例生成 `results.sarif` 与 `summary.json`。

### Phase 3：后端 CodeQL task 执行链路

目标：可创建 CodeQL 任务、执行 CubeSandbox、解析 SARIF、保存 findings。

工作：

- 静态任务创建按 `engine` 分流。
- 新增 `run_codeql_scan_inner(...)`。
- 新增 SARIF parser。
- 复用 `StaticTaskRecord`/`StaticFindingRecord`。
- 任务 progress 增加 CodeQL 阶段。

验收：

- Opengrep 任务回归通过。
- CodeQL no-build 样例任务完成并展示 findings。

### Phase 4：事件流与 LLM build plan 推理

目标：编译失败时能把证据传回后端并让 LLM 生成候选 build plan。

工作：

- CubeSandbox 输出 `events.jsonl`。
- 后端 watcher 增量读取事件并写 progress logs。
- 新增 LLM build plan prompt/schema。
- 增加命令安全校验与推理轮次上限。
- 失败时保留 evidence，成功时保存 verified build plan。

验收：

- 人为制造缺失构建命令的项目，任务进入 `build_plan_inference`。
- progress 可见失败日志摘要。
- LLM 输出结构化候选方案。
- 受控重试成功后保存 build plan。

### Phase 5：前端集成与结果一致性

目标：用户可以从静态审计入口创建 CodeQL 扫描并查看结果。

工作：

- `frontend/src/shared/api/opengrep.ts` 评估是否重命名为 engine-neutral API，或新增 `codeql.ts`。
- 创建弹窗增加 engine/codeql 参数。
- 任务列表、详情、finding 表格增加 engine 标识。
- CodeQL metadata 在详情中展示。

验收：

- Opengrep UI 不回退。
- CodeQL task/finding 与 Opengrep 使用一致表格与状态操作。

### Phase 6：文档、运维与回归矩阵

目标：把 CodeQL 从实验能力固化为可维护平台能力。

工作：

- 更新 `docs/architecture.md`，把 “Opengrep-only” 改成 “静态审计支持 Opengrep + 隔离 CodeQL engine”。
- 增加运维文档：镜像构建、CodeQL bundle 版本、离线部署、资源配置。
- 增加测试矩阵与 troubleshooting。

验收：

- 新人可按文档构建 runner、执行样例、理解 build plan 机制。

## 14. 测试矩阵

### 14.1 后端单元测试

- `scan_rule_assets`：发现 `rules_opengrep` + `rules_codeql`，分类正确。
- `codeql::parse_sarif_output`：解析最小 SARIF、缺失字段 SARIF、多 run SARIF。
- build plan fingerprint：构建文件变化会使 plan stale。
- command validator：拒绝 workspace 外写入、Docker 命令、凭据读取等危险命令。

### 14.2 CubeSandbox 测试

- CubeSandbox CodeQL 模板自检。
- Python/JS no-build 样例。
- 一个需要 manual build 的最小 Java/C++ 样例。
- 故意失败构建，验证 `events.jsonl` 和 `summary.json`。

### 14.3 集成测试

- 创建 Opengrep 任务仍成功。
- 创建 CodeQL 任务成功。
- CodeQL SARIF findings 入库并能通过现有 findings API 读取。
- progress API 能看到 CodeQL 阶段日志。

### 14.4 前端测试

- 创建弹窗 engine 切换不破坏 Opengrep 默认路径。
- CodeQL 任务列表 badge/阶段显示。
- CodeQL finding 表格与状态更新。

### 14.5 安全测试

- LLM 生成危险命令被拒绝。
- 网络关闭时，`requires_network=true` 计划不会执行。
- runner 资源超限/超时能失败并保留日志。

## 15. 安全与隔离要求

1. CodeQL 扫描主路径必须使用 CubeSandbox；Opengrep 继续使用 Docker runner。
2. CodeQL build 命令只在 CubeSandbox workspace 内执行。
3. 默认禁用网络构建；允许联网必须是显式配置。
4. 不向 LLM 发送完整源码，默认发送文件树摘要、构建文件摘要、错误日志摘要；如要发送源码片段必须由配置控制。
5. build plan 中保存命令和证据，方便审计。
6. CubeSandbox 不挂载宿主敏感目录，不读取后端环境凭据。
7. 任务失败时保留必要日志，但避免长期保留完整源码副本。

## 16. 严格 0% Deep-interview 决策固化

本计划已经过 2026-04-30 strict-zero deep-interview 回访，以下边界不得在后续规划或实施中重新模糊化：

1. **完成门槛**：ambiguity 必须为 0%；非目标、决策边界、验收标准、压力回访不得留残余风险。
2. **执行权限**：LLM 候选构建命令通过校验后可在 CubeSandbox 内自动执行，无需逐条人工批准。
3. **网络与数据**：CubeSandbox 可联网安装依赖；LLM 可接收必要源码片段、构建文件和日志。
4. **语言范围**：首版必须支持 JavaScript/TypeScript、Python、Java、C/C++、Go。
5. **分期语义**：允许按语言分里程碑实施，但五类语言未全绿前不得声明首版完成。
6. **固化位置**：build plan、指纹和证据的运行时真源只能是数据库；文件只作为临时 CubeSandbox artifact。
7. **项目提示**：本仓库根 `AGENTS.md` 与 repo-local `.codex/AGENTS.md` 必须记录后续 `$deep-interview` 默认压到严格 0%。

## 17. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| CodeQL bundle 镜像体积大 | 构建慢、部署慢 | CubeSandbox 模板镜像、版本缓存、离线制品库 |
| 编译型项目构建不可复现 | 建库失败 | LLM 推理 + evidence 固化 + 人工确认边界 |
| LLM 生成危险命令 | 安全风险 | JSON schema、命令白/黑名单、sandbox、网络默认关 |
| SARIF 字段变化 | 解析失败 | 宽容解析，raw payload 保留，单元测试覆盖可选字段 |
| 与 Opengrep UI/任务耦合过深 | 回归风险 | engine 分流、Opengrep 回归测试先行 |
| 规则资产模型过度泛化 | 实施膨胀 | 首版只扩展 `rules_codeql`，不重写整个规则系统 |

## 18. 待确认问题

以下问题不阻塞计划成文，但会影响后续实施策略：

1. CodeQL query pack 是否先使用内置最小 Argus pack，还是直接导入 GitHub 官方 query suites？建议先用官方 bundle 自带 suite + Argus 最小 pack 双轨。
2. 每类语言的最小样例项目应放在 `backend/tests/fixtures` 还是 runner self-test 内，需要 `$ralplan` 固化测试布局；但验收标准已固定为五类语言全绿。

## 19. 后续推荐动作

1. 用本计划进入 `$ralplan`，生成 PRD 与测试规格：

```text
$ralplan --direct .omx/specs/deep-interview-codeql-opengrep-isolated-scan-plan.md
```

2. PRD 通过后，用 `$ralph` 或 `$team` 分阶段实施。
3. 可按语言和阶段分里程碑实施，但必须在计划/状态中标注“首版未完成”，直到 JavaScript/TypeScript、Python、Java、C/C++、Go 全部端到端全绿。
4. LLM build plan 推理、沙箱自动执行、数据库固化不是可选增强，而是首版验收范围。


## 20. 参考资料

- GitHub Docs: CodeQL CLI `database create`，包含 `--build-mode=none|autobuild|manual` 和 `--command` 语义：https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli-manual/database-create
- GitHub Docs: CodeQL CLI `database analyze`，包含 SARIF 输出参数与分析数据库的 CLI 语义：https://docs.github.com/code-security/codeql-cli/manual/database-analyze
- GitHub Docs: CodeQL query packs，说明 query pack 需要 `qlpack.yml`，且 CodeQL CLI bundle 已包含 core query packs：https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-query-packs
- GitHub Docs: CodeQL query packs reference，说明 query/library pack 与 `codeql-pack.lock.yml` 等 pack 文件约束：https://docs.github.com/en/code-security/reference/code-scanning/codeql/codeql-cli/codeql-query-packs
