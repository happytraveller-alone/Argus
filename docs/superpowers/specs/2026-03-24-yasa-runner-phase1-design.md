# YASA Runner Phase 1 Design

## Goal

将 backend container slim 第一阶段从“backend 镜像内直接执行 YASA”切换为“backend 编排一次性 YASA runner 容器执行”，同时保留现有 API 契约、任务模型和结果落库行为不变，并把本地开发、全量构建与发布链路一起对齐。

## Scope

本阶段只迁移 `YASA`。

- backend 继续负责：
  - 创建扫描任务
  - 解压项目 ZIP、准备输入输出目录
  - 启动和停止扫描
  - 解析 SARIF、写入数据库、更新任务状态
  - bootstrap 扫描调用与结果归一化
- `yasa-runner` 容器负责：
  - 挂载共享工作目录
  - 在容器内执行单次 `YASA` 命令
  - 把报告与日志写回共享目录
- 本阶段不做：
  - `opengrep` runner 切流
  - 常驻 sidecar
  - runner 直接访问数据库
  - runner 失败时回退 backend 本地 `/opt/yasa`

## Current Problems

- backend 运行镜像目前仍假定本地存在 `YASA` 二进制和资源目录，和瘦身目标冲突。
- 静态扫描任务的输入、输出、取消语义主要面向本地 `subprocess`，不适合一次性容器执行。
- bootstrap 扫描与静态扫描各自维护 `YASA` 执行细节，后续迁移其他 scanner 时容易重复造轮子。
- 本地 compose、full build 和 CI 发布链路还没有统一表达 runner 镜像及共享扫描目录。

## Proposed Architecture

### 1. Shared Scan Workspace

backend 在宿主共享目录下为每个任务建立稳定工作区，统一承载输入、输出和日志。

建议目录结构：

```text
${SCAN_WORKSPACE_ROOT}/
  yasa/
    ${task_id}/
      project/
      input/
      output/
        report.sarif
      logs/
        stdout.log
        stderr.log
      meta/
        runner.json
```

约束：

- 目录必须位于 `settings.SCAN_WORKSPACE_ROOT`
- backend 和 runner 通过 bind mount 访问同一物理目录
- backend 负责生命周期清理，runner 只读输入并写输出

### 2. Generic Scanner Runner Contract

新增 `backend/app/services/scanner_runner.py`，作为一次性 scanner 容器编排层。

职责：

- 接收 scanner 类型、镜像、工作目录、命令、环境变量和超时
- 通过 Docker SDK 创建并启动一次性容器
- 将任务工作目录挂载到 runner 容器固定路径 `/scan`
- 将容器 id 暴露给调用方，供中断接口复用
- 等待容器退出并返回 exit code、日志路径和错误摘要
- 在超时或取消时负责 stop/remove 容器

非职责：

- 不解析 `YASA` 报告
- 不直接操作数据库
- 不做 scanner 级业务判断

### 3. YASA Execution Flow

`static_tasks_yasa.py` 与 `agent/bootstrap/yasa.py` 都切到同一套 runner 契约：

1. backend 解压项目 ZIP 到共享工作目录
2. backend 计算语言 profile、checker pack、rule config
3. backend 构造 runner 侧命令，统一写入 `/scan/output`
4. `scanner_runner` 拉起 `SCANNER_YASA_IMAGE`
5. runner 在容器内执行 `YASA`
6. backend 读取 `/scan/output/report.sarif`
7. backend 解析结果并写库
8. backend 清理 container registry 和任务工作目录

### 4. Failure Semantics

本阶段采用单一路径语义，避免双实现长期并存。

- runner 镜像不存在、容器创建失败、容器启动失败、执行超时或退出码异常：
  - 任务标记为 `failed`
  - `error_message` 中保留 runner 侧错误摘要
  - 不回退 backend 本地 `/opt/yasa`
- 用户中断：
  - backend 先 stop/remove 对应 container id
  - 然后更新任务为 `interrupted`
- 报告解析失败：
  - 任务标记为 `failed`
  - 保留 stdout/stderr 路径与摘要，方便排查

## Backend Changes

### Configuration

在 `backend/app/core/config.py` 增加或对齐：

- `SCAN_WORKSPACE_ROOT`
- `SCANNER_YASA_IMAGE`
- `SCANNER_OPENGREP_IMAGE` 作为后续预留

`YASA_BIN_PATH` 与 `YASA_RESOURCE_DIR` 不再作为 backend 运行时硬依赖；若仍保留配置，也只用于 runner 镜像构建或兼容迁移期，不再驱动 backend 本地执行。

### Shared Static Task Utilities

`static_tasks_shared.py` 需要提供：

- 共享工作目录构建/清理函数
- 项目 ZIP 解压切换到稳定工作区
- 本地 `subprocess` 和容器执行共存期的取消注册表
- container id 注册、反注册与 stop helper

取消语义要兼容已有 `bandit/opengrep/phpstan/gitleaks` 本地路径，不能回归现有任务中断能力。

### YASA Runtime Helpers

`yasa_runtime.py` 从“解析 backend 本地 `/opt/yasa`”转为“构造 runner 内命令与路径约定”。

建议调整为：

- 允许指定 runner 内的二进制路径，例如 `/opt/yasa/bin/yasa`
- 允许指定 runner 内资源目录，例如 `/opt/yasa/resource`
- 默认所有 `source_path`、`report_dir`、`rule_config_file` 都基于容器内 `/scan/...`

### API And Bootstrap Integration

`static_tasks_yasa.py` 与 `agent/bootstrap/yasa.py` 统一使用：

- 共享工作目录准备逻辑
- `scanner_runner` 执行入口
- 同一份 SARIF 解析逻辑或共用 helper

这样可以避免 API 路径和 bootstrap 路径出现不同的 runner 协议。

## Container And Release Changes

### Backend Image

backend 运行镜像移除 `YASA` 运行时产物，不再要求：

- `/opt/yasa/bin/yasa`
- `/opt/yasa/resource`
- 任何为 backend 本地执行 `YASA` 保留的 wrapper/fallback

backend 只需保留：

- Docker SDK 依赖
- `/var/run/docker.sock` 访问能力
- 共享扫描工作目录挂载点

### YASA Runner Image

新增 `backend/docker/yasa-runner.Dockerfile`。

镜像职责：

- 安装 `YASA` 可执行文件和资源目录
- 提供稳定入口环境，默认工作目录面向 `/scan`
- 保持单次任务运行，不依赖数据库或 backend 源码

镜像输出契约：

- 读取 `/scan/project`
- 把 SARIF 写到 `/scan/output/report.sarif`
- 把 stdout/stderr 留给容器日志，由 backend 同步到工作目录日志文件

### Compose And Publish

需要一起修改：

- `docker-compose.yml`
- `docker-compose.full.yml`
- `.github/workflows/docker-publish.yml`

要求：

- backend 注入 `SCAN_WORKSPACE_ROOT` 与 `SCANNER_YASA_IMAGE`
- backend 服务挂载共享扫描目录和 `docker.sock`
- full build 可以本地构建 `yasa-runner` 镜像
- 发布工作流增加 `yasa-runner` 的 build/push，标签策略与 backend 保持一致

## Testing Strategy

测试要覆盖三层：

### 1. Runner Abstraction

- 工作目录位于配置根目录下
- runner 创建参数包含镜像、挂载、命令、环境
- timeout / missing container / stop failure 有稳定返回
- container id 注册和反注册正确

### 2. YASA Business Flow

- `static_tasks_yasa.py` 改走 runner 后仍能解析 SARIF 并落库
- bootstrap `YASA` 改走 runner 后仍返回归一化 findings
- runner 失败时任务/扫描结果进入明确失败分支
- 中断任务时优先停止容器而不是仅取消本地协程

### 3. Delivery Path

- compose 默认开发布局包含共享扫描目录与 runner 镜像配置
- full compose 覆盖层包含本地 `yasa-runner` build
- docker publish workflow 包含 `yasa-runner` 推送步骤

所有 Python 验证统一使用 `uv run pytest ...`。

## Risks And Mitigations

- Docker socket 依赖扩大 backend 权限面
  - 本阶段延续现有 docker 集成方式，只把权限使用面限制在 scanner runner 编排
- 共享目录清理不及时会累积磁盘占用
  - 通过统一 cleanup helper 和任务结束后清理收敛
- API 和 bootstrap 分别适配 runner 容易出现协议漂移
  - 共用 `scanner_runner` 与 SARIF helper，避免双份协议
- full build 与发布链路不一致会导致“本地能跑、线上失效”
  - 这次同步修改 compose full 与 workflow，不拆开交付

## Acceptance Criteria

- backend 镜像不再依赖本地 `YASA` 运行时
- `YASA` 静态扫描 API 成功通过 runner 容器完成一次扫描并正常落库
- `YASA` bootstrap 成功通过 runner 容器返回归一化 findings
- 用户中断 `YASA` 任务时可停止对应 runner 容器
- runner 不可用时任务清晰失败，不发生本地 fallback
- 本地 compose、full build 与 GH workflow 都能表达 `yasa-runner` 镜像
- 为 `scanner_runner`、`static_tasks_shared`、`YASA` API/bootstrap、compose/workflow 增加或更新测试

