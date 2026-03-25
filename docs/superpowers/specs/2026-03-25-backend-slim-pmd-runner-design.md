# Backend Slim PMD Runner Design

## Goal

在保留 backend 开发镜像预热 `/opt/backend-venv`、`uv` 和现有启动体验的前提下，将 PMD 从 backend 本地运行时中拆出，切换为与现有 `scanner_runner` 体系兼容的“一次性专用 runner 容器”执行模式，并同步补齐 compose、本地构建与发布链路。

## Scope

本次只改造 PMD 相关链路。

- backend 继续负责：
  - Agent 工具参数校验
  - 目标路径解析
  - 扫描 workspace 准备与清理
  - runner 调度
  - PMD JSON 报告解析
  - 用户可读摘要和结构化 findings 生成
- `pmd-runner` 容器负责：
  - 提供 Java 运行时与 PMD 7.0.0
  - 挂载共享扫描目录到 `/scan`
  - 执行单次 PMD 扫描
  - 将报告写回 `/scan/output`
- 本次不做：
  - 不新增 `static_tasks_pmd.py`
  - 不新增 PMD task/db 模型
  - 不改造其他 scanner 为按需模式
  - 不裁剪 `/opt/backend-venv` 内 Python 依赖
  - 不处理与 PMD 无关的现有失败测试

## Current Problems

- backend 运行镜像当前仍包含仅为 PMD 服务的 `openjdk-21-jre-headless`、`php-cli`、`unzip` 和本地 PMD 安装逻辑，和瘦身目标冲突。
- `PMDTool` 当前仍直接依赖 `SandboxManager` 执行命令，没有接入现有 `scanner_runner` 容器调度契约。
- compose、full overlay 和发布 workflow 里都还没有 PMD runner 镜像入口。
- 当前 PMD 结果主要依赖 stdout 内容推断 JSON，不够稳定，也不符合 runner 模式下固定产物文件的习惯。

## Proposed Architecture

### 1. Backend Runtime Slimming

`backend/Dockerfile` 保留 backend API 和 Agent 工具真正需要的系统依赖，以及已有的：

- `/opt/backend-venv`
- `/usr/local/bin/uv`
- `backend/scripts/dev-entrypoint.sh` 当前自修复逻辑

backend runtime 移除：

- `openjdk-21-jre-headless`
- `php-cli`
- backend runtime 中仅为 PMD 服务的 `unzip`
- PMD 7.0.0 下载、解压和 `/usr/local/bin/pmd` 软链接逻辑

`scanner-tools-base` stage 继续保留，但它如果仍需要 `unzip`，则改为 stage-local 依赖，不再透传自 `runtime-base`。

### 2. Dedicated PMD Runner Image

新增 `backend/docker/pmd-runner.Dockerfile`，镜像职责单一：

- 安装 `openjdk-21-jre-headless`
- 下载并解压 PMD 7.0.0
- 提供稳定的 `pmd` 可执行入口，并保证 `pmd` 在容器 `PATH` 中可直接调用
- 默认围绕 `/scan` 工作目录执行单次任务

该镜像不作为 compose 常驻服务存在，不参与 backend 启动时预热。

命令入口约定固定为：

- 不依赖镜像内 `ENTRYPOINT ["pmd"]` 语义来隐式拼接参数
- backend 传给 `run_scanner_container(...)` 的 `command` 为完整参数数组，即 `["pmd", "check", ...]`
- `pmd-runner` 镜像只需保证 `pmd` 可执行文件在 `PATH` 中
- `run_scanner_container(...)` 使用宿主机 workspace 根目录 `<SCAN_WORKSPACE_ROOT>/pmd-tool/<run_id>` 以 `rw` 方式挂载到容器 `/scan`
- runner 容器的 `working_dir` 固定为 `/scan`
- PMD runner 不新增额外环境变量约定，调用时使用 `env={}`
- 网络行为保持现有 `scanner_runner` 默认行为，本轮不新增 PMD 专用网络配置
- stdout/stderr 不由 runner 主动写入 `logs/`；仍由 backend 通过 `scanner_runner` 从容器日志采集，并在既有契约下落到 workspace 的 `logs/`

### 3. PMDTool Execution Contract

`PMDTool` 切换为直接调用 `run_scanner_container(...)`，不再使用：

- `SandboxManager.initialize()`
- `SandboxManager.is_available`
- `SandboxManager.execute_tool_command(...)`

执行前，backend 在 `settings.SCAN_WORKSPACE_ROOT` 下创建稳定工作区：

```text
${SCAN_WORKSPACE_ROOT}/
  pmd-tool/
    ${run_id}/
      project/
      output/
        report.json
      logs/
      meta/
        rules/
        runner.json
```

约束：

- `run_id` 为每次 `PMDTool` 调用生成的 `uuid4().hex`
- 目录组织语义与现有 `ensure_scan_workspace(scan_type, task_id)` 风格保持一致，即 `<SCAN_WORKSPACE_ROOT>/pmd-tool/<run_id>/...`
- 该 workspace 约定只在 `external_tools.py` 内本地实现，不引入 `static_tasks_shared.py` 依赖
- `project/` 为复制后的项目树，不直接把原始项目目录挂给 runner
- 复制策略以“保持当前扫描覆盖面”为优先：本轮不新增内容裁剪规则，不额外排除 `.git/`、`node_modules/`、构建产物目录或大文件目录
- 复制逻辑仍需避免把 workspace 自身递归复制回 `project/`
- symlink 不做解引用复制，保持为 link 本身；若其目标位于项目树外，本轮不尝试额外纳入扫描
- `output/` 保存 PMD JSON 报告
- `logs/` 保存 `scanner_runner` 保留的 stdout/stderr
- `meta/` 保存 runner 元数据与必要的 staged ruleset

### 4. Ruleset Strategy

ruleset 处理固定为两类：

- 内置别名：
  - `security`
  - `quickstart`
  - `all`

  直接映射为现有 `PMDTool.ruleset_map` 的 exact 值，以保持现有行为和测试预期稳定：

  - `security`:
    - `category/java/security.xml,category/java/errorprone.xml,category/apex/security.xml`
  - `quickstart`:
    - `category/java/security.xml,category/jsp/security.xml,category/javascript/security.xml`
  - `all`:
    - `category/java/security.xml,category/jsp/security.xml,category/javascript/security.xml,category/html/security.xml,category/xml/security.xml,category/plsql/security.xml,category/apex/security.xml,category/visualforce/security.xml`

- 本地 XML 文件：
  - 若文件位于被扫描项目树内，则以 `/scan/project/...` 引用
  - 若文件不位于项目树内，则复制到 `/scan/meta/rules/...` 后再引用
- 非法 ruleset：
  - 若字符串既不是内置 alias，也不是可解析的 `.xml` 文件路径，则直接返回明确错误
  - 不再回退到默认 `security`

这样既保留现有灵活性，也避免 runner 直接访问宿主其他任意路径。

## Execution Flow

`PMDTool` 的正式运行流程为：

1. 解析 `target_path`，保持现有“扫描整个项目或子目录”的用户体验
2. 在 `SCAN_WORKSPACE_ROOT` 下创建隔离 workspace
3. 将项目复制到 `project/`
4. 解析或 stage ruleset
5. 调用 `run_scanner_container(...)` 拉起一次性 PMD runner
6. runner 执行 `pmd check`
7. backend 从 `output/report.json` 读取并解析报告
8. backend 返回摘要与结构化 findings
9. workspace 在工具执行结束后清理

runner 内命令使用参数数组，不走 `sh -lc`，默认 `timeout_seconds=180`，环境变量使用 `env={}`。backend 传入 `run_scanner_container(...)` 的 `command` 形态固定为完整数组 `["pmd", "check", ...]`。目标路径规范化和安全边界固定为：

- 只接受项目内相对路径
- 绝对路径一律拒绝
- 包含 `..` 的路径一律拒绝
- Windows 反斜杠先规范化为 `/`，再按相对路径规则校验
- 规范化后若路径逃出项目根目录，则一律拒绝并返回明确错误
- 若用户传入的路径不存在于项目内，也返回明确错误，不再额外回退到项目根目录

目标路径拼接规则固定为：

- `target_path="."`、`""` 或 `"./"` 时，runner `--dir` 使用 `/scan/project`
- `target_path` 为项目内子目录时，runner `--dir` 使用 `/scan/project/<normalized_target_path>`

核心命令形态为：

```text
pmd check --dir /scan/project/<target> --rulesets <ruleset> --format json --report-file /scan/output/report.json --no-cache
```

## Exit Codes And Error Handling

退出码语义固定按 PMD 7 处理：

- `0`：扫描成功且未发现问题
- `4`：扫描成功但发现问题
- 其他退出码：执行失败

用户可见返回口径：

- 成功且无问题：返回简洁成功摘要
- 成功且有问题：按优先级排序输出摘要，并在 `metadata` 中保留结构化 findings
- 失败：返回必要的错误摘要，不暴露命令拼接细节、临时目录路径和多余 debug 噪声

`scanner_runner` 既有“非零退出码保留日志文件”的契约保持不变，因此 `exit_code=4` 时日志仍会被保存到 workspace，但 `PMDTool` 成功路径不主动向用户展示这些日志。

当 `output/report.json` 不存在或内容无法解析为合法 JSON 时：

- 一律视为执行失败
- 用户侧返回“报告缺失”或“报告解析失败”的错误摘要
- 内部仍保留 `scanner_runner` 写下的 stdout/stderr 与 `runner.json`，用于调试

workspace 清理策略固定为：

- 成功和失败都在本次 `PMDTool` 调用结束时清理 workspace
- 本轮不新增调试保留开关
- 失败场景的诊断依赖调用生命周期内可见的 `logs/` 与 `runner.json`，不通过持久保留整个 workspace 来实现

报告中的文件路径归一化规则固定为：

- 解析 PMD JSON 后，将 `/scan/project/` 前缀剥离为项目相对路径
- 若 PMD 返回的是 `/scan/project` 本身的相对形式，也统一格式化为项目内相对路径
- 用户可见输出和 `metadata.findings` 都遵循同一归一化规则，以保持 Agent 体验和测试断言稳定

## Configuration And Delivery Changes

### Configuration

在 `backend/app/core/config.py` 增加：

- `SCANNER_PMD_IMAGE`

默认值与现有 runner 风格保持一致，例如：

- `vulhunter/pmd-runner:latest`

### Compose

`docker-compose.yml` 与 `docker-compose.full.yml` 中：

- backend 增加 `SCANNER_PMD_IMAGE`
- 不新增 `pmd-runner` 服务
- 不新增 backend 对 `pmd-runner` 的 `depends_on`

### Publish Workflow

`.github/workflows/docker-publish.yml` 增加：

- `build_pmd_runner` input
- PMD runner 构建与推送步骤
- summary 输出中的 PMD runner 镜像信息

## Testing Strategy

测试分为三层：

### 1. PMD Tool Behavior

新增 `backend/tests/test_pmd_runner_tool.py`，覆盖：

- runner 命令构建
- `expected_exit_codes=[0, 4]`
- workspace 目录布局
- ruleset staging 逻辑
- `report.json` 解析
- 成功/有发现/失败三类输出语义

此组测试通过 monkeypatch 替换 `run_scanner_container(...)`，不依赖真实 Docker。

### 2. Text Contracts

新增 `backend/tests/test_pmd_runner_contracts.py`，覆盖：

- backend Dockerfile 不再安装 PMD/JRE/PHP 相关运行时
- compose/full overlay 增加 `SCANNER_PMD_IMAGE`
- compose 文件未引入 `pmd-runner` 常驻服务
- workflow 增加 PMD runner 发布入口

该组测试独立存在，不并入已有 noisy 的 compose dev flow 测试。

### 3. Manual Validation Doc

更新 `backend/tests/test_external_tools_manual.py` 中 PMD 段落，说明：

- PMD 现在依赖 `SCANNER_PMD_IMAGE`
- 执行方式为按需 runner 容器
- 仍然是 opt-in 手工测试，不纳入默认自动化验收

所有 Python 验证命令统一使用：

```bash
uv run --project . pytest ...
```

## Risks And Mitigations

- backend 与 runner 的共享目录语义若处理不一致，可能导致找不到规则文件或报告文件
  - 通过固定 `/scan/project`、`/scan/output`、`/scan/meta` 约定收敛
- 在 `external_tools.py` 中直接复用 API 层 helper 会扩大耦合面
  - 本次只在工具层实现最小必要 helper，不引入 `static_tasks_shared.py`
- PMD 切 runner 后输出口径变化，可能影响 Agent 体验
  - 保持“无问题返回简洁成功，有问题返回摘要与结构化 findings”的现有交互风格
- 发布链路若遗漏 PMD runner，可能出现“本地能跑、发布后缺镜像”
  - 本次同步修改 compose、full overlay 和 workflow，不拆开交付

## Acceptance Criteria

- backend 镜像继续保留 `/opt/backend-venv`、`uv` 和现有 dev-entrypoint 体验
- backend 镜像不再包含本地 PMD、JRE、PHP CLI 相关运行时
- 新增 `pmd-runner` 镜像，并由 backend 通过 `SCANNER_PMD_IMAGE` 按需拉起
- `docker compose up` 时不启动任何常驻 `pmd-runner` 服务
- `PMDTool` 正式执行路径切到 `scanner_runner`
- 本地 ruleset 在项目内/项目外两种场景都能正确引用
- 成功路径从固定 `report.json` 解析结果，不再依赖 stdout 猜测 JSON
- 本次新增测试能够覆盖 Dockerfile/compose/workflow 文本契约和 `PMDTool` 的 runner 行为
