# CodeQL 隔离扫描纳入静态审计/Opengrep 入口实施计划

> 文档定位：这是新的 Argus CodeQL 扫描实施计划，面向当前 Rust/Axum 后端、React/Vite 前端、Docker runner 静态审计架构。旧文档 `plan/codeql_security/codeql_platform_deploy.md` 包含过时的 AuditTool/Python/FastAPI 表述，仅作为历史背景，不作为本计划的实现依据。

## 1. 结论先行

首版采用 **“静态审计/Opengrep 入口下的新扫描类型 + 后端 engine 完全隔离”**：

- 前端仍在当前静态审计/Opengrep 相关入口中创建和查看扫描，满足“放在 Opengrep 中”的产品体验。
- 后端使用独立 `engine="codeql"`、独立 scan module、独立 runner image、独立规则/查询根目录，满足“与 Opengrep 扫描隔离”。
- 结果、任务进度、finding 状态、AI 分析入口尽量复用现有静态审计体验，避免为首版重做一套并行 UI。
- CodeQL 构建复杂性通过 **沙箱事件流 + LLM 构建方案推理 + 沙箱内自动执行 + 数据库 build plan 固化** 解决，而不是把构建命令硬编码到平台。

## 2. 背景与动机

现有静态审计主线以 Opengrep 为核心，适合无需完整项目编译即可运行的规则扫描。但 CodeQL 的优势在于语义建库与数据流查询，尤其适合需要跨函数、跨文件、跨编译单元分析的漏洞类型。

用户需求的关键点是：

1. CodeQL 要进入当前静态审计体系，而不是外部 CI 示例。
2. CodeQL 必须与 Opengrep 扫描隔离，不能破坏现有 Opengrep 任务、规则、runner 和结果展示。
3. CodeQL 需要独立容器镜像，镜像内包含 CodeQL CLI/bundle。
4. CodeQL 查询库/规则加载逻辑要与 Opengrep 规则加载方式一致。
5. 难点不是简单执行 `codeql database analyze`，而是 `database create` 对编译流程敏感，需要把 runner/sandbox 内的日志、必要源码片段和构建文件准实时传回后端，让大模型推理、自动校验并在沙箱内执行候选构建命令，最终把项目级构建方案固化到数据库。

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

### 3.4 当前缺口

- 没有 `engine="codeql"` 的规则资产发现与加载。
- 没有 CodeQL runner image/script。
- 没有 SARIF 到 `StaticFindingRecord` 的解析器。
- 现有 runner 只在结束后捕获 stdout/stderr；CodeQL 构建推理需要准实时事件流。
- 没有项目级 CodeQL build plan 的存储、指纹和复用机制。

## 4. 外部 CodeQL 事实约束

根据 GitHub CodeQL CLI 文档与本轮 strict-zero deep-interview 决策：

- `codeql database create` 支持 `--build-mode=none|autobuild|manual`。其中 `none` 适用于部分无需构建语言；`autobuild` 和 `manual` 适用于需要构建或可自动构建的语言；传入 `--command` 时即代表手动构建命令。
- `codeql database analyze` 可输出 SARIF，适合作为平台统一解析入口。
- CodeQL SARIF 输出字段可能随版本增加，解析器必须对可选字段保持宽容。
- 自定义 CodeQL 查询应作为 query pack/query suite 管理，并通过 CLI 分析数据库。
- 本计划首版验收必须覆盖 JavaScript/TypeScript、Python、Java、C/C++、Go 五类语言；可按语言分里程碑推进，但五类语言未全绿前不得声明首版完成。

这些事实决定了 Argus 不能只设计“单命令扫描”，而必须设计建库、构建、分析、日志反馈与 build plan 固化的完整闭环。

## 5. 目标架构

```text
Frontend Static Audit / Opengrep Surface
        |
        | create task: engine=codeql
        v
backend/src/routes/static_tasks.rs
        |
        | dispatch by engine
        v
backend/src/scan/codeql.rs
        |
        | materialize rules_codeql + build-plan + runner spec
        v
Docker runner: Argus/codeql-runner-local:latest
        |
        | events.jsonl / summary.json / results.sarif / build-plan-candidate.json
        v
Backend progress watcher + LLM build-plan inference
        |
        | persist successful plan fingerprint
        v
StaticTaskRecord + StaticFindingRecord
        |
        v
Frontend task/finding display consistent with Opengrep
```

## 6. 产品/API 边界

### 6.1 推荐边界

首版不要把 CodeQL 做成 Opengrep 的后处理，也不要把 CodeQL 做成完全脱离静态审计的新顶级系统。推荐边界：

- 用户在静态审计创建入口选择扫描引擎：`Opengrep` 或 `CodeQL`。
- 前端任务列表、任务详情、finding 表格保留一致布局。
- 后端 task record 用 `engine` 区分：`opengrep` 与 `codeql`。
- CodeQL 规则、runner、配置、build plan、SARIF 解析完全独立。

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

保持与 `opengrep.rs` 同样的资产加载思想：DB/assets 是唯一规则来源，runner workspace 是临时 materialized copy。

## 8. CodeQL runner 镜像与脚本

### 8.1 镜像原则

新增 `docker/codeql-runner.Dockerfile`，不要修改 Opengrep runner：

- 基础镜像使用 Debian/Ubuntu/glibc，不使用 Alpine/musl。
- 安装 CodeQL bundle/CLI 到 `/opt/codeql/codeql`。
- 安装最小构建工具集：`bash`, `git`, `python3`, `nodejs/npm`, `make`, `gcc/g++`, `openjdk`, `maven/gradle` 等按阶段取舍。
- 工作目录 `/scan`。
- 内置 self-test：`codeql version`、`codeql resolve languages`、最小样例建库与 SARIF 输出。

新增配置：

```env
SCANNER_CODEQL_IMAGE=Argus/codeql-runner-local:latest
CODEQL_SCAN_TIMEOUT_SECONDS=0
CODEQL_RUNNER_MEMORY_LIMIT_MB=8192
CODEQL_RUNNER_CPU_LIMIT=0
CODEQL_THREADS=0
CODEQL_RAM_MB=6144
CODEQL_MAX_BUILD_INFERENCE_ROUNDS=3
CODEQL_ALLOW_NETWORK_DURING_BUILD=true
CODEQL_LLM_ALLOW_SOURCE_SNIPPETS=true
```

### 8.2 runner 入口脚本

新增 `docker/codeql-scan.sh`，建议参数：

```text
codeql-scan --self-test
codeql-scan \
  --source /scan/source \
  --queries /scan/codeql-queries \
  --database /scan/output/codeql-db \
  --sarif /scan/output/results.sarif \
  --summary /scan/output/summary.json \
  --events /scan/output/events.jsonl \
  --build-plan /scan/build-plan/build-plan.json \
  --language javascript-typescript \
  --threads 0 \
  --ram 6144
```

脚本职责：

1. 记录 `events.jsonl`：阶段开始/结束、命令、退出码、关键日志摘要、产物路径。
2. 根据 build plan 决定 `database create` 的 build mode：`none` / `autobuild` / `manual`。
3. 执行 `database create`。
4. 执行 `database analyze --format=sarifv2.1.0 --output=...`。
5. 写 `summary.json`，让现有 runner summary gate 可判断完成/失败。
6. 不直接调用 LLM；LLM 推理由后端根据事件流驱动。

## 9. 沙箱事件流与 LLM 构建方案推理

### 9.1 为什么需要事件流

CodeQL 建库失败通常不是“扫描规则错误”，而是项目构建失败、依赖缺失、构建系统识别错误、语言选择错误或 monorepo 子目录错误。后端如果只能在容器结束后拿到一坨 stderr，大模型无法稳定迭代构建方案。因此需要结构化事件流。

### 9.2 事件文件格式

runner 写入：`/scan/output/events.jsonl`。

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

- `extracting`
- `detecting_language`
- `preparing_queries`
- `build_plan_select`
- `database_create`
- `build_failure_observed`
- `llm_inference_requested`
- `build_plan_candidate_written`
- `database_analyze`
- `parsing_sarif`
- `completed` / `failed`

### 9.3 后端 watcher

在 `run_codeql_scan_inner(...)` 中启动 watcher：

- 轮询 workspace 中的 `events.jsonl` 增量内容。
- 将事件转换为 `StaticTaskProgressLogRecord`。
- 必要时触发 LLM 构建方案推理。
- watcher 不直接信任 runner 输出；路径必须限制在 workspace 内。

### 9.4 LLM 推理边界

LLM 输入：

- 项目语言、文件树摘要、构建文件摘要。
- 当前 build plan。
- CodeQL database create 失败事件。
- stdout/stderr 安全摘要。
- 已尝试命令与退出码。

LLM 输出必须是结构化 JSON，禁止自由文本直接执行；结构化候选命令通过校验后可自动在 runner 沙箱内执行：

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

执行前校验：

- 命令数量上限。
- 禁止写 workspace 外路径。
- 禁止 Docker-in-Docker、宿主机挂载、凭据读取。
- 网络首版允许开启，用于依赖安装；仍必须记录网络使用证据。
- LLM 可接收必要源码片段、构建文件和日志；不得发送无关完整仓库。
- 最多 `CODEQL_MAX_BUILD_INFERENCE_ROUNDS` 轮。

## 10. 项目级 CodeQL build plan 固化

### 10.1 存储对象

必须新增 `CodeqlBuildPlanRecord` 或等价数据库结构。数据库是 build plan、指纹和证据的唯一运行时真源；文件只能作为临时 runner artifact，不能作为复用依据。

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

## 13. 实施阶段

### Phase 0：计划评审与验收边界确认

产物：

- 本计划文档。
- `.omx/specs/deep-interview-codeql-opengrep-isolated-scan-plan.md`。
- 后续 `$ralplan` 生成 PRD 和 test spec。

确认项：

- 是否允许构建 sandbox 联网。
- LLM 是否可接收源码片段/日志摘要。
- 首版语言排序。
- 是否需要人工批准 LLM 生成命令。

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

### Phase 2：CodeQL runner 镜像与最小扫描

目标：runner 能自检并对样例项目输出 SARIF。

工作：

- 新增 `docker/codeql-runner.Dockerfile`。
- 新增 `docker/codeql-scan.sh`。
- Compose 增加 `codeql-runner` 构建/预热服务。
- 后端配置增加 `SCANNER_CODEQL_IMAGE` 等。

验收：

- `docker build -f docker/codeql-runner.Dockerfile ...` 成功。
- `codeql-scan --self-test` 成功。
- 最小样例生成 `results.sarif` 与 `summary.json`。

### Phase 3：后端 CodeQL task 执行链路

目标：可创建 CodeQL 任务、执行 runner、解析 SARIF、保存 findings。

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

- runner 输出 `events.jsonl`。
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

### 14.2 runner 测试

- `codeql-scan --self-test`。
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

1. CodeQL runner 和 Opengrep runner 必须是不同镜像。
2. CodeQL build 命令只在 runner workspace 内执行。
3. 默认禁用网络构建；允许联网必须是显式配置。
4. 不向 LLM 发送完整源码，默认发送文件树摘要、构建文件摘要、错误日志摘要；如要发送源码片段必须由配置控制。
5. build plan 中保存命令和证据，方便审计。
6. runner 不挂载宿主敏感目录，不读取后端环境凭据。
7. 任务失败时保留必要日志，但避免长期保留完整源码副本。

## 16. 严格 0% Deep-interview 决策固化

本计划已经过 2026-04-30 strict-zero deep-interview 回访，以下边界不得在后续规划或实施中重新模糊化：

1. **完成门槛**：ambiguity 必须为 0%；非目标、决策边界、验收标准、压力回访不得留残余风险。
2. **执行权限**：LLM 候选构建命令通过校验后可在 CodeQL runner 沙箱内自动执行，无需逐条人工批准。
3. **网络与数据**：runner 可联网安装依赖；LLM 可接收必要源码片段、构建文件和日志。
4. **语言范围**：首版必须支持 JavaScript/TypeScript、Python、Java、C/C++、Go。
5. **分期语义**：允许按语言分里程碑实施，但五类语言未全绿前不得声明首版完成。
6. **固化位置**：build plan、指纹和证据的运行时真源只能是数据库；文件只作为临时 runner artifact。
7. **项目提示**：本仓库根 `AGENTS.md` 与 repo-local `.codex/AGENTS.md` 必须记录后续 `$deep-interview` 默认压到严格 0%。

## 17. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| CodeQL bundle 镜像体积大 | 构建慢、部署慢 | 独立 runner 镜像、版本缓存、离线制品库 |
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
