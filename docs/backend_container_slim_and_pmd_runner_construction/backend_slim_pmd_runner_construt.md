# Backend Slim And PMD Runner Construction Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 backend 开发镜像预热 `/opt/backend-venv` 和现有 `uv` 启动体验的前提下，移除 backend 镜像中仅为 PMD 服务的 Java/PHP 运行时与本地 PMD 安装逻辑，并将 PMD 改造成与现有 `scanner_runner` 体系兼容的“按需唤醒、扫描后立即关停”的专有临时容器执行模式。

**Architecture:** backend 继续作为 API 编排层和 Agent 工具宿主，负责参数校验、目标路径解析、扫描 workspace 准备、runner 调度、JSON 报告解析与结果格式化；`pmd-runner` 镜像只承载 Java 运行时和 PMD 分发包，不作为 compose 常驻服务或预热服务存在。只有 `PMDTool` 真正执行时，backend 才通过 `run_scanner_container(...)` 拉起临时 PMD 容器，扫描结束即退出并删除。

**Tech Stack:** FastAPI, Docker Engine API, Docker Compose, GitHub Actions, multi-stage Dockerfile, Python 3.11, uv, pytest, PMD 7.0.0, OpenJDK 21 JRE

---

## Current Code Baseline

- backend 镜像当前仍包含与 PMD 相关的重型依赖：
  - [backend/Dockerfile](/home/xyf/AuditTool/backend/Dockerfile) 的 `runtime-base` 安装了 `openjdk-21-jre-headless`、`php-cli`、`unzip`
  - 同文件的 `runtime` 阶段会下载并解压 `pmd-dist-7.0.0-bin.zip`，把 `pmd` 链接到 `/usr/local/bin/pmd`
- backend 开发镜像当前必须保留预热 venv：
  - [backend/Dockerfile](/home/xyf/AuditTool/backend/Dockerfile) 的 `dev-runtime` 会 `COPY --from=builder /opt/backend-venv /opt/backend-venv`
  - [docker-compose.yml](/home/xyf/AuditTool/docker-compose.yml) 为 backend 挂载 named volume `backend_venv:/opt/backend-venv`
  - [backend/scripts/dev-entrypoint.sh](/home/xyf/AuditTool/backend/scripts/dev-entrypoint.sh) 会在 lockfile 变化时执行 `uv sync --active --frozen --no-dev`
- PMD 当前不是 runner 化实现，而是 Agent 工具内通过 sandbox 执行：
  - [backend/app/services/agent/tools/external_tools.py](/home/xyf/AuditTool/backend/app/services/agent/tools/external_tools.py) 中 `PMDTool` 当前调用 `SandboxManager.execute_tool_command(...)`
  - 同文件里的 ruleset 路径映射逻辑以 `/workspace/...` 为目标容器路径，适配的是 sandbox，不是 `scanner_runner`
  - 当前 PMD 逻辑还依赖 `SandboxManager.initialize()` / `is_available`
- 仓库已经具备可复用的 runner 基础设施：
  - [backend/app/services/scanner_runner.py](/home/xyf/AuditTool/backend/app/services/scanner_runner.py) 已提供 `ScannerRunSpec`、`ScannerRunResult`、`run_scanner_container(...)`
  - [backend/tests/test_scanner_runner.py](/home/xyf/AuditTool/backend/tests/test_scanner_runner.py) 已覆盖临时容器启动、非零退出码日志保留和容器删除行为
- compose 和配置目前没有 PMD 入口：
  - [backend/app/core/config.py](/home/xyf/AuditTool/backend/app/core/config.py) 只有 `SCANNER_YASA_IMAGE`、`SCANNER_OPENGREP_IMAGE`、`SCANNER_BANDIT_IMAGE`、`SCANNER_GITLEAKS_IMAGE`、`SCANNER_PHPSTAN_IMAGE`
  - [docker-compose.yml](/home/xyf/AuditTool/docker-compose.yml) 和 [docker-compose.full.yml](/home/xyf/AuditTool/docker-compose.full.yml) 也没有 `SCANNER_PMD_IMAGE`
- 发布链路同样没有 PMD runner：
  - [.github/workflows/docker-publish.yml](/home/xyf/AuditTool/.github/workflows/docker-publish.yml) 只有 `build_yasa_runner`、`build_opengrep_runner`、`build_bandit_runner`、`build_gitleaks_runner`、`build_phpstan_runner`
- 手工测试文件当前仍按旧路径描述 PMD：
  - [backend/tests/test_external_tools_manual.py](/home/xyf/AuditTool/backend/tests/test_external_tools_manual.py) 中 PMD 段落未说明 `SCANNER_PMD_IMAGE` 依赖
- 当前存在与本轮无关的测试基线噪音：
  - [backend/tests/test_docker_compose_dev_flow.py](/home/xyf/AuditTool/backend/tests/test_docker_compose_dev_flow.py) 当前已经有 `nexus_web` 相关断言失败，不能把本轮 PMD 改造的成功标准绑定为“该文件全量通过”

## Feasibility Corrections

- `PMDTool` 不能使用默认 `tempfile.TemporaryDirectory()` 路径作为 runner workspace：
  - Docker Engine 运行的容器需要 bind mount 宿主机路径
  - backend 运行在容器内时，只有挂载到 backend 容器和 Docker Engine 之间共享的宿主机目录才可安全复用
  - 因此 PMD workspace 必须落在 `settings.SCAN_WORKSPACE_ROOT` 下，而不是随机 `/tmp/tmp*`
- 本轮不修改共享 `scanner_runner` 的日志保留语义：
  - 当前实现对所有“非零退出码”保留 stdout/stderr，即使该退出码被 `expected_exit_codes` 视为成功
  - PMD 只需要做到“成功路径不向用户暴露这些日志”，不要求本轮连带重构 `scanner_runner`
- backend 去掉 `runtime-base` 中的 `unzip` 后，若继续保留未被 final stage 使用的 `scanner-tools-base`，必须把该 stage 对 `unzip` 的依赖改为 stage-local 安装，避免留下后续构建隐患
- 文本契约测试不要继续堆进已有基线噪音的 [backend/tests/test_docker_compose_dev_flow.py](/home/xyf/AuditTool/backend/tests/test_docker_compose_dev_flow.py)：
  - 本轮新增独立测试文件，专门承载 PMD 改造相关的 Dockerfile、compose 和 workflow 文本断言

## Target End State

- `vulhunter/backend-local:latest` 继续保留：
  - 预热的 `/opt/backend-venv`
  - `uv` 二进制
  - 现有 `dev-entrypoint` 自修复和 lockfile 驱动的同步逻辑
- `vulhunter/backend-local:latest` 不再包含：
  - `openjdk-21-jre-headless`
  - 本地 PMD 安装产物
  - backend runtime 仅为 PMD 服务的 `unzip`
  - 已确认不需要留在 backend 内的 `php-cli`
- PMD 改为专有 runner 镜像，但不是 compose 常驻服务：
  - 新增 `vulhunter/pmd-runner-local:latest`
  - 新增 `SCANNER_PMD_IMAGE`
  - `docker compose up` 时不启动任何 `pmd-runner` 服务
  - 只有使用 `PMDTool` 时，backend 才按需拉起临时 PMD 容器
  - 扫描结束后容器立即退出并删除
- PMDTool 的正式执行路径从 sandbox 切换到 `scanner_runner`
  - 不再直接挂载用户项目根目录到 runner
  - 改为先在 `SCAN_WORKSPACE_ROOT` 下创建隔离 workspace，再将项目树复制到 `project/`
  - ruleset XML 若不在项目树内，则复制到 `meta/rules/` 再由 runner 引用
- PMD 日志和输出口径调整为：
  - 正常路径只向用户返回扫描摘要
  - 失败路径只向用户返回错误摘要和必要诊断
  - 不输出命令拼接细节、临时目录细节和多余 debug 噪声
  - `scanner_runner` 仍按既有契约在非零退出码时保留 stdout/stderr 到日志文件；PMDTool 成功路径不向用户暴露这些日志
- 本轮不做的事：
  - 不新增 `static_tasks_pmd.py`
  - 不新增 PMD 数据库模型或 task 表
  - 不裁剪 `/opt/backend-venv` 内的 Python 依赖
  - 不处理 `uv` 二进制体积
  - 不强制从 sandbox 镜像中删除 PMD/JDK
  - 不把其他现有 runner 从 compose 预热模式改成按需模式
  - 不顺手改掉与 PMD 无关的现有测试基线失败

## File Plan

### Create

- `backend/docker/pmd-runner.Dockerfile`
  - PMD 专有 runner 镜像定义
  - 固定 PMD 版本为 `7.0.0`
  - 安装 OpenJDK 21 JRE 和 PMD 运行时所需最小工具
- `backend/tests/test_pmd_runner_tool.py`
  - 覆盖 `PMDTool` runner 化后的命令构建、workspace 布局、ruleset staging、报告解析、按需启动与错误处理
- `backend/tests/test_pmd_runner_contracts.py`
  - 覆盖 backend Dockerfile、compose/full overlay、workflow 的 PMD 相关文本契约

### Modify

- `backend/Dockerfile`
  - 删除 backend 镜像中的 PMD/JRE/PHP 相关安装
  - 保持预热 venv 和 `uv` 复制逻辑不变
  - 保留 `scanner-tools-base`，但把其对 `unzip` 的依赖移到该 stage 内部
- `backend/app/core/config.py`
  - 新增 `SCANNER_PMD_IMAGE`
- `docker-compose.yml`
  - backend 环境变量增加 `SCANNER_PMD_IMAGE`
  - 不新增 `pmd-runner` 服务
  - 不新增 backend 对 `pmd-runner` 的 `depends_on`
- `docker-compose.full.yml`
  - 与默认 compose 对齐 `SCANNER_PMD_IMAGE`
  - 不新增 `pmd-runner` 服务
- `backend/app/services/agent/tools/external_tools.py`
  - 将 `PMDTool` 从 sandbox 执行改为 `scanner_runner` 执行
  - 新增私有辅助函数处理 workspace、ruleset staging、runner 路径映射、日志收敛和 JSON 报告解析
- `backend/tests/test_external_tools_manual.py`
  - 手工测试 PMD 的说明和期望改为 `SCANNER_PMD_IMAGE` 驱动的按需 runner 模式
- `.github/workflows/docker-publish.yml`
  - 新增 `build_pmd_runner` input、构建步骤、GHCR 输出步骤

## Design Decisions Locked In

- 不新建第二套 runner 抽象；直接复用 [backend/app/services/scanner_runner.py](/home/xyf/AuditTool/backend/app/services/scanner_runner.py)
- 不把 PMD 接到静态任务 API；本轮只改 Agent 侧的 `PMDTool`
- PMD runner 固定使用 `openjdk-21-jre-headless`，不使用 JDK；原因是 PMD 仅需运行时，不需要编译能力
- PMD 版本与 backend 当前实现保持一致，固定为 `7.0.0`，避免报告格式和退出码语义漂移
- PMD CLI 采用 PMD 7 官方 `check` 子命令和 `--report-file` 输出方式，退出码语义按 PMD 7 CLI 参考执行：
  - `0` 表示扫描成功且未发现问题
  - `4` 表示扫描成功但发现问题
  - 其他退出码视为执行失败
  - 参考文档: [PMD 7.0.0 CLI reference](https://docs.pmd-code.org/pmd-doc-7.0.0/pmd_userdocs_cli_reference.html)
- PMDTool 调度 runner 时使用参数数组而不是 `sh -lc` 拼 shell 命令，减少 quoting 风险
- PMD JSON 输出使用 `--report-file /scan/output/report.json`，不依赖 stdout 重定向
- PMDTool 的 runner 执行 workspace 统一布局为：
  - `/scan/project`
  - `/scan/output`
  - `/scan/logs`
  - `/scan/meta`
- PMDTool 的宿主机 workspace 固定创建在 `settings.SCAN_WORKSPACE_ROOT` 下，例如：
  - `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>/project`
  - `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>/output`
  - `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>/logs`
  - `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>/meta`
- ruleset 处理策略固定如下：
  - 内置别名 `security` / `quickstart` / `all` 直接传 PMD 官方 ruleset 字符串
  - 本地 XML 文件如果位于被扫描项目树内，则以 `/scan/project/...` 引用
  - 本地 XML 文件如果不位于项目树内，则复制到 `/scan/meta/rules/...` 后以 `/scan/meta/rules/...` 引用
- PMDTool 不再依赖 `SandboxManager.initialize()`、`SandboxManager.is_available`、`SandboxManager.execute_tool_command(...)`
- [backend/app/api/v1/endpoints/static_tasks_shared.py](/home/xyf/AuditTool/backend/app/api/v1/endpoints/static_tasks_shared.py) 不引入到 `external_tools.py`：
  - 该模块是 API 层重模块，耦合面过大
  - `PMDTool` 只复用 `scanner_runner` 契约
  - workspace 准备逻辑在 `external_tools.py` 内本地实现，但语义对齐 `SCAN_WORKSPACE_ROOT`
- 手工测试文件仍是 opt-in：
  - 不把 [backend/tests/test_external_tools_manual.py](/home/xyf/AuditTool/backend/tests/test_external_tools_manual.py) 纳入默认自动化验收命令
- backend 和 PMD runner 的镜像验收使用运行容器验证可执行文件，而不是 `docker history`

## Task 1: Slim Backend Runtime Without Touching Preheated Venv

**Files:**
- Modify: `backend/Dockerfile`
- Test: `backend/tests/test_pmd_runner_contracts.py`

- [ ] **Step 1: 写失败测试，锁定 backend 镜像不再自带 PMD/JRE/PHP**

在 `backend/tests/test_pmd_runner_contracts.py` 新增断言：

```python
def test_backend_dockerfile_no_longer_installs_local_pmd_runtime(): ...
```

断言点：
- `backend/Dockerfile` 不再包含 runtime 阶段安装 PMD 的命令
- `backend/Dockerfile` 的 backend `runtime-base` 不再安装 `openjdk-21-jre-headless`
- `backend/Dockerfile` 的 backend `runtime-base` 不再安装 `php-cli`
- `backend/Dockerfile` 的 backend `runtime-base` 不再安装 `unzip`

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- 新增 backend Dockerfile 断言失败，因为当前 backend 镜像仍包含 PMD/JRE/PHP 逻辑

- [ ] **Step 3: 精简 `runtime-base`，只保留 backend API 必需系统依赖**

在 `backend/Dockerfile` 中：
- 保留 `libpq5`、`curl`、`git`、`libpango-1.0-0`、`libpangoft2-1.0-0`、`libpangocairo-1.0-0`、`libcairo2`、`libgdk-pixbuf-2.0-0`、`libglib2.0-0`、`shared-mime-info`
- 保留可选 `fonts-noto-cjk`
- 移除 `openjdk-21-jre-headless`
- 移除 `php-cli`
- 移除 `unzip`

- [ ] **Step 4: 保留 `scanner-tools-base`，但把 `unzip` 依赖改为 stage-local**

要求：
- 不删除 `scanner-tools-base`
- 不再依赖 `runtime-base` 预装 `unzip`
- 在 `scanner-tools-base` 内，仅在需要解压 YASA 发行包的路径上安装或提供 `unzip`

- [ ] **Step 5: 删除 backend `runtime` 阶段中的 PMD 下载和安装块**

要求：
- 删除 `PMD_CACHE` 下载与 `/opt/pmd-bin-7.0.0` 解压逻辑
- 删除 `/usr/local/bin/pmd` 软链接创建
- 保留 `site-packages` 清理与 `pip` 清理逻辑

- [ ] **Step 6: 保持 dev 体验完全不变**

确认以下行为不改：
- `COPY --from=builder /opt/backend-venv /opt/backend-venv`
- `COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv`
- `ENV VIRTUAL_ENV=/opt/backend-venv`
- 现有 [backend/scripts/dev-entrypoint.sh](/home/xyf/AuditTool/backend/scripts/dev-entrypoint.sh) 逻辑不变

- [ ] **Step 7: 运行 Dockerfile 文本契约测试**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- backend Dockerfile 相关断言恢复通过

## Task 2: Create `pmd-runner` Image And Expose It As On-Demand Scanner Image

**Files:**
- Create: `backend/docker/pmd-runner.Dockerfile`
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.full.yml`
- Test: `backend/tests/test_pmd_runner_contracts.py`

- [ ] **Step 1: 写失败测试，锁定 PMD runner 的配置入口和非预热模式**

在 `backend/tests/test_pmd_runner_contracts.py` 增加断言：

```python
def test_compose_exposes_scanner_pmd_image_without_pmd_runner_service(): ...
def test_full_overlay_exposes_scanner_pmd_image_without_pmd_runner_service(): ...
```

断言点：
- `SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}`
- `docker-compose.yml` 中不存在 `pmd-runner:`
- `docker-compose.full.yml` 中不存在 `pmd-runner:`
- backend `depends_on` 中不包含 `pmd-runner`

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- 新增 PMD image 相关断言失败

- [ ] **Step 3: 在配置中新增 `SCANNER_PMD_IMAGE`**

在 `backend/app/core/config.py` 中新增：

```python
SCANNER_PMD_IMAGE: str = "vulhunter/pmd-runner:latest"
```

位置要求：
- 与现有 `SCANNER_YASA_IMAGE`、`SCANNER_OPENGREP_IMAGE`、`SCANNER_BANDIT_IMAGE`、`SCANNER_GITLEAKS_IMAGE`、`SCANNER_PHPSTAN_IMAGE` 放在同一区块

- [ ] **Step 4: 实现 `backend/docker/pmd-runner.Dockerfile`**

设计约束：
- 基础镜像与现有 runner 一致，继续使用 `python:3.11-slim` 体系以统一系统环境
- 仅安装 `ca-certificates`、`curl`、`unzip`、`openjdk-21-jre-headless`
- 复用现有 runner 的 APT mirror / fallback 风格
- 下载 `pmd-dist-7.0.0-bin.zip`
- 解压到 `/opt/pmd-bin-7.0.0`
- 创建 `/usr/local/bin/pmd`
- `WORKDIR /scan`
- 默认 `CMD ["pmd", "--version"]`

不要在该镜像中安装 backend 代码、backend venv 或其他扫描器

- [ ] **Step 5: 修改默认 compose**

在 `docker-compose.yml` 中：
- backend `environment` 增加 `SCANNER_PMD_IMAGE`
- 不新增 `pmd-runner` 服务
- 不新增 backend 对 `pmd-runner` 的 `depends_on`

- [ ] **Step 6: 修改 full overlay compose**

在 `docker-compose.full.yml` 中：
- backend `environment` 增加 `SCANNER_PMD_IMAGE`
- 不新增 `pmd-runner` 服务
- 不新增 backend 对 `pmd-runner` 的 `depends_on`

- [ ] **Step 7: 运行 compose 文本契约测试**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- 默认 compose 与 full overlay 中的 PMD image / 非预热模式断言全部通过

## Task 3: Migrate `PMDTool` From Sandbox To On-Demand `scanner_runner`

**Files:**
- Modify: `backend/app/services/agent/tools/external_tools.py`
- Create: `backend/tests/test_pmd_runner_tool.py`
- Modify: `backend/tests/test_external_tools_manual.py`

- [ ] **Step 1: 写失败测试，锁定 PMDTool 新的执行契约**

创建 `backend/tests/test_pmd_runner_tool.py`，至少覆盖：

```python
async def test_pmd_tool_uses_scanner_runner_image(...): ...
async def test_pmd_tool_does_not_initialize_sandbox(...): ...
async def test_pmd_tool_creates_workspace_under_scan_workspace_root(...): ...
async def test_pmd_tool_copies_project_into_isolated_workspace(...): ...
async def test_pmd_tool_stages_ruleset_outside_project_into_meta_dir(...): ...
async def test_pmd_tool_accepts_exit_code_4_and_parses_report(...): ...
async def test_pmd_tool_fails_on_runner_exit_code_5(...): ...
async def test_pmd_tool_fails_when_report_missing_for_success_exit(...): ...
```

断言点：
- 不再调用 `SandboxManager.initialize()`
- 不再调用 `SandboxManager.execute_tool_command(...)`
- 调用 `run_scanner_container(...)`
- `ScannerRunSpec.image == settings.SCANNER_PMD_IMAGE`
- workspace 宿主机路径位于 `settings.SCAN_WORKSPACE_ROOT` 下
- 目标目录挂载点是 `/scan/project/...`
- 报告文件固定写到 `/scan/output/report.json`
- 失败时依赖 `scanner_runner` 保留的 stderr/stdout 路径构造错误信息

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py -v
```

Expected:
- 失败，因为 `PMDTool` 仍使用 sandbox

- [ ] **Step 3: 保留 `PMDTool` 的输入接口，替换其执行后端**

在 `external_tools.py` 中保持不变：
- `PMDInput`
- `PMDTool.name`
- `PMDTool.description`
- `PMDTool.args_schema`
- `PMDTool.__init__(project_root, sandbox_manager=None)` 签名

需要替换：
- `_execute(...)` 的运行体
- ruleset 映射到容器路径的方式
- JSON 输出读取方式

- [ ] **Step 4: 在 `PMDTool` 内实现 isolated workspace 准备**

在 `PMDTool` 中新增私有 helper，职责拆分如下：

```python
def _prepare_pmd_workspace(...): ...
def _resolve_pmd_ruleset(...): ...
def _stage_pmd_ruleset(...): ...
def _build_pmd_runner_command(...): ...
def _parse_pmd_report(...): ...
```

实现要求：
- 不使用默认 `tempfile.TemporaryDirectory()` 作为最终 workspace 根目录
- 通过 `settings.SCAN_WORKSPACE_ROOT` 下的唯一任务目录创建 workspace
- workspace 内创建 `project/`、`output/`、`logs/`、`meta/`
- 用 `shutil.copytree(..., dirs_exist_ok=True)` 把 `project_root` 复制到 `project/`
- 调用 `_smart_resolve_target_path(...)` 后，将目标路径映射到 `/scan/project/...`
- 不直接把用户原始项目目录作为 `workspace_dir`
- 不引入 `static_tasks_shared.py`

- [ ] **Step 5: 固定 PMD runner 命令格式**

`ScannerRunSpec.command` 使用数组形式：

```python
[
    "pmd",
    "check",
    "-d",
    "<runner target path>",
    "-R",
    "<selected ruleset>",
    "-f",
    "json",
    "--no-cache",
    "--report-file",
    "/scan/output/report.json",
]
```

不要使用 shell 拼接字符串，不要依赖 stdout 重定向

- [ ] **Step 6: 固定 runner 退出码与结果读取策略**

实现约束：
- `expected_exit_codes=[0, 4]`
- 若 `exit_code in {0, 4}`，必须读取 `/scan/output/report.json`
- 若 `exit_code not in {0, 4}`，返回失败，并携带保留的 stderr/log 路径信息
- 若 `report.json` 缺失且退出码是 `0` 或 `4`，视为失败
- 若 Docker 启动失败或镜像不存在，返回失败，并明确提示检查 `SCANNER_PMD_IMAGE`

- [ ] **Step 7: 保持当前结果格式兼容，并收敛日志输出**

返回的 `ToolResult` 保持以下结构不变：
- `metadata["findings_count"]`
- `metadata["high_count"]`
- `metadata["medium_count"]`
- `metadata["low_count"]`
- `metadata["findings"]`
- `metadata["raw_result"]`

日志要求：
- 成功路径只记录扫描结果摘要
- 失败路径只记录错误摘要和必要诊断
- 不打印完整命令、宿主机临时路径和多余 debug 噪声
- 不要求修改 `scanner_runner` 现有“非零退出保留日志”逻辑

显示文本继续沿用当前 PMDTool 的中文格式化输出风格

- [ ] **Step 8: 更新手工测试文件**

在 `backend/tests/test_external_tools_manual.py` 中：
- 保留 PMDTool 的手工测试入口
- 更新注释和预期，说明 PMD 已走 `SCANNER_PMD_IMAGE`
- 明确它仍是 opt-in 手工测试，不纳入默认自动化验收

- [ ] **Step 9: 运行 PMD 自动化测试**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py -v
```

Expected:
- `test_pmd_runner_tool.py` 通过

## Task 4: Add PMD Runner To Docker Publish Workflow

**Files:**
- Modify: `.github/workflows/docker-publish.yml`
- Test: `backend/tests/test_pmd_runner_contracts.py`

- [ ] **Step 1: 写失败测试，锁定 workflow 新输入与发布项**

在 `backend/tests/test_pmd_runner_contracts.py` 中增加断言：

```python
def test_docker_publish_workflow_builds_pmd_runner(): ...
```

断言点：
- `build_pmd_runner`
- `./backend/docker/pmd-runner.Dockerfile`
- `ghcr.io/${{ github.repository_owner }}/vulhunter-pmd-runner:${{ github.event.inputs.tag }}`

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- workflow 相关断言失败

- [ ] **Step 3: 扩展 workflow_dispatch inputs**

在 `.github/workflows/docker-publish.yml` 中新增：

```yaml
build_pmd_runner:
  description: '构建 PMD runner 镜像'
  required: false
  type: boolean
  default: true
```

- [ ] **Step 4: 增加 `pmd-runner` 构建与 summary 输出**

要求：
- 构建步骤位置与其他 runner 相邻
- `context: ./backend`
- `file: ./backend/docker/pmd-runner.Dockerfile`
- `cache-from` / `cache-to` 使用独立 `scope=pmd-runner`
- summary 输出风格与现有 runner 完全一致

- [ ] **Step 5: 运行 workflow 文本契约测试**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- workflow 发布断言通过

## Task 5: Verification And Acceptance

**Files:**
- Modify if needed: `backend/tests/test_pmd_runner_contracts.py`
- Modify if needed: `backend/tests/test_pmd_runner_tool.py`

- [ ] **Step 1: 跑后端测试集的最小闭环**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest \
  tests/test_pmd_runner_contracts.py \
  tests/test_pmd_runner_tool.py \
  tests/test_scanner_runner.py \
  -v
```

Expected:
- 新增 PMD runner 契约测试、PMDTool runner 测试、既有 `scanner_runner` 测试全部通过
- 不要求 [backend/tests/test_docker_compose_dev_flow.py](/home/xyf/AuditTool/backend/tests/test_docker_compose_dev_flow.py) 因本轮一并恢复全绿

- [ ] **Step 2: 本地构建 backend 与 pmd-runner 镜像**

Run:

```bash
cd /home/xyf/AuditTool
docker build -f backend/docker/pmd-runner.Dockerfile -t vulhunter/pmd-runner-local:latest backend
docker compose build backend
```

Expected:
- 两个镜像构建成功

- [ ] **Step 3: 验证 compose 默认不会预热 PMD runner**

Run:

```bash
cd /home/xyf/AuditTool
docker compose config
```

Expected:
- 输出中 backend 带有 `SCANNER_PMD_IMAGE`
- 输出中没有 `pmd-runner` 服务
- backend `depends_on` 中没有 `pmd-runner`

- [ ] **Step 4: 验证 backend 镜像中不再自带 Java/PHP/PMD**

Run:

```bash
docker run --rm vulhunter/backend-local:latest sh -lc 'command -v java || true; command -v php || true; command -v pmd || true'
```

Expected:
- 三个命令都没有有效可执行输出

- [ ] **Step 5: 验证 pmd-runner 镜像中具备 Java 与 PMD**

Run:

```bash
docker run --rm vulhunter/pmd-runner-local:latest sh -lc 'java -version >/dev/null 2>&1 && pmd --version >/dev/null 2>&1'
```

Expected:
- 退出码为 `0`

- [ ] **Step 6: 需要时执行 PMD 手工烟测**

Run:

```bash
cd /home/xyf/AuditTool/backend
RUN_EXTERNAL_TOOLS_MANUAL_TESTS=1 \
SCANNER_PMD_IMAGE=vulhunter/pmd-runner-local:latest \
uv run --project . pytest tests/test_external_tools_manual.py -k pmd -v -s
```

Expected:
- PMDTool 调用时才创建临时扫描容器
- 扫描结束后容器退出并删除
- 控制台只有扫描结果摘要和错误信息，不出现额外调试噪声
