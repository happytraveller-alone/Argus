# AuditTool CodeQL 平台实施部署手册（平台原生 + Docker + 全链路）

> 文档定位：本手册用于把 CodeQL 作为 AuditTool 平台内置静态审计能力落地，不是单纯 CI 示例。  
> 参考来源：`/root/AuditTool/codeql.md`（官方摘要）与 `/root/AuditTool/codeql_standard_implementation.md`（标准化实现规格，主参考）。

---

## 1. 目标与边界

### 1.1 目标

在 AuditTool 中新增 CodeQL 引擎，实现与现有 `opengrep/bandit/gitleaks/phpstan/pmd/yasa` 同级的“平台原生扫描能力”，覆盖：

- Docker runner 安装与执行（当前平台无 CodeQL 运行环境）。
- 后端任务创建、调度、状态管理、结果入库。
- 前端任务创建入口、任务与 findings 展示。
- 预检、发布、验收与运维策略。

### 1.2 首版支持语言

- `python`
- `javascript-typescript`
- `cpp`（承载 C/C++ 路径）

### 1.3 明确边界

- 本文档不实现供应链扫描（OSV/Trivy/Dependabot）。
- 本文档不替代 `.github/workflows/codeql-*.yml` 的纯 CI 方案。
- 本文档以“平台内任务执行 + 数据入库 + UI 可视化”为主线。

---

## 2. AuditTool 现状映射（As-Is）

### 2.1 扫描执行架构现状

当前 AuditTool 静态审计采用统一模式：

1. 后端 API 创建扫描任务。
2. 后端通过 `ScannerRunSpec + run_scanner_container` 启动一次性 runner 容器。
3. 运行目录统一挂载到共享扫描卷（`SCAN_WORKSPACE_ROOT`，默认 `/tmp/Argus/scans`）。
4. 解析产物并写入 `*_scan_tasks` 与 `*_findings` 表。

### 2.2 已有关键契约

- runner 镜像配置键：`SCANNER_*_IMAGE`（例如 `SCANNER_BANDIT_IMAGE`）。
- 预检体系：`backend/app/services/runner_preflight.py`。
- Docker 构建发布：`.github/workflows/docker-publish.yml`。
- 路由聚合：`backend/app/api/v1/endpoints/static_tasks.py`。

### 2.3 与 CodeQL 的差距

- 当前代码中无 `codeql` 后端模型、API、runner、前端 API 客户端。
- 当前预检和构建链路无 CodeQL runner。
- 当前平台没有 CodeQL bundle 安装机制。

---

## 3. 目标架构（To-Be）

### 3.1 组件新增

新增以下组件并对齐现有扫描架构：

- `docker/codeql-runner.Dockerfile`
- 后端配置项：`SCANNER_CODEQL_IMAGE` 等
- 后端模型：`CodeqlScanTask`、`CodeqlFinding`（可选 `CodeqlRuleState`）
- 后端路由：`/api/v1/static-tasks/codeql/*`
- 前端 API：`frontend/src/shared/api/codeql.ts`
- 前端扫描引擎枚举与创建任务弹窗扩展

### 3.2 运行数据流

1. 前端创建 CodeQL 任务（项目、语言、目标路径、构建命令、查询套件）。
2. 后端复制项目到扫描工作区。
3. 后端调用 codeql runner 容器建库与分析，输出 SARIF。
4. 后端解析 SARIF 为平台 findings 并入库。
5. 前端展示任务状态与 findings，支持状态更新。

### 3.3 Runner 调度契约

- 镜像键：`SCANNER_CODEQL_IMAGE`
- 容器工作根：`/scan`
- 必须产物：
  - `meta/runner.json`
  - `output/results.sarif`
  - 失败日志（stdout/stderr）

---

## 4. Docker 环境安装 CodeQL（重点）

> 原则：CodeQL 安装在专用 runner 镜像，不安装进 backend 主镜像。  
> 原因：减少主服务镜像体积、降低升级耦合、保持扫描工具解耦。

### 4.1 目录与文件

新增文件：`docker/codeql-runner.Dockerfile`

建议镜像名：`Argus/codeql-runner:latest`

### 4.2 基础镜像与兼容约束

- 基础镜像必须是 glibc 系 Linux（推荐 Debian/Ubuntu）。
- 禁止 Alpine/musl 作为 CodeQL runner 基础镜像。

### 4.3 Dockerfile 参考模板

```dockerfile
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG CODEQL_BUNDLE_VERSION=2.20.5
ARG CODEQL_BUNDLE_ARCH=linux64

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS codeql-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG CODEQL_BUNDLE_VERSION
ARG CODEQL_BUNDLE_ARCH

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CODEQL_DIST_DIR=/opt/codeql
ENV CODEQL_HOME=/opt/codeql/codeql
ENV PATH=/opt/codeql/codeql:${PATH}

RUN set -eux; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_runtime_packages() { \
      apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl unzip xz-utils zstd \
        git make g++ nodejs npm; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mkdir -p ${CODEQL_DIST_DIR} /scan; \
    BUNDLE="codeql-bundle-${CODEQL_BUNDLE_ARCH}.tar.zst"; \
    URL_BASE="https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_BUNDLE_VERSION}"; \
    curl -fL "${URL_BASE}/${BUNDLE}" -o /tmp/codeql-bundle.tar.zst; \
    tar --use-compress-program=unzstd -xf /tmp/codeql-bundle.tar.zst -C ${CODEQL_DIST_DIR}; \
    rm -f /tmp/codeql-bundle.tar.zst; \
    codeql version; \
    codeql resolve packs; \
    codeql resolve languages

WORKDIR /scan
CMD ["codeql", "version"]
```

### 4.4 安装验证

```bash
docker build -f docker/codeql-runner.Dockerfile -t Argus/codeql-runner-local:latest .
docker run --rm Argus/codeql-runner-local:latest codeql version
docker run --rm Argus/codeql-runner-local:latest codeql resolve languages
```

预期结果：输出中包含 `python`、`javascript`、`cpp`。

### 4.5 弱网与离线建议

- 在线弱网：优先镜像代理 URL，再 fallback 官方 GitHub release。
- 离线部署：
  1. 在可联网环境下载 bundle。
  2. 放入内网制品库。
  3. Dockerfile 使用 `COPY` 或内网 URL 安装。

---

## 5. 后端配置扩展

在 `backend/app/core/config.py` 新增配置键：

```python
SCANNER_CODEQL_IMAGE: str = "Argus/codeql-runner:latest"
CODEQL_DEFAULT_LANGUAGES: str = "python,javascript-typescript,cpp"
CODEQL_DEFAULT_QUERY_SUITE: str = "security-extended"
CODEQL_BUNDLE_VERSION: str = "2.20.5"
CODEQL_TIMEOUT_SECONDS: int = 1800
CODEQL_THREADS: int = 0
CODEQL_RAM_MB: int = 8192
```

在 `docker-compose.yml` 与 `docker-compose.full.yml` 的 backend 环境变量中新增：

```yaml
SCANNER_CODEQL_IMAGE: ${SCANNER_CODEQL_IMAGE:-Argus/codeql-runner-local:latest}
CODEQL_DEFAULT_LANGUAGES: ${CODEQL_DEFAULT_LANGUAGES:-python,javascript-typescript,cpp}
CODEQL_DEFAULT_QUERY_SUITE: ${CODEQL_DEFAULT_QUERY_SUITE:-security-extended}
CODEQL_BUNDLE_VERSION: ${CODEQL_BUNDLE_VERSION:-2.20.5}
CODEQL_TIMEOUT_SECONDS: ${CODEQL_TIMEOUT_SECONDS:-1800}
CODEQL_THREADS: ${CODEQL_THREADS:-0}
CODEQL_RAM_MB: ${CODEQL_RAM_MB:-8192}
```

---

## 6. 数据模型与迁移

### 6.1 新增表：`codeql_scan_tasks`

建议字段：

- `id`（uuid/string）
- `project_id`
- `name`
- `status`（`pending/running/completed/failed/interrupted`）
- `target_path`
- `languages`（JSON 字符串或数组）
- `build_command`（可空，`cpp` 必填）
- `query_suite`
- `total_findings` / `high_count` / `medium_count` / `low_count`
- `scan_duration_ms` / `files_scanned`
- `error_message`
- `created_at` / `updated_at`

### 6.2 新增表：`codeql_findings`

建议字段：

- `id`
- `scan_task_id`
- `rule_id`
- `rule_name`
- `severity`
- `security_severity`
- `message`
- `description`
- `file_path`
- `start_line` / `start_col` / `end_line` / `end_col`
- `status`（`open/verified/false_positive`）
- `raw_payload`（JSON 文本）
- `created_at`

### 6.3 可选表：`codeql_rule_states`

用途：规则启停与软删除（与 Bandit/PHPStan 规则管理一致化）。首版可选。

### 6.4 Alembic 迁移

新增迁移文件，命名建议：

- `xxxx_add_codeql_scan_tables.py`

执行：

```bash
cd backend
uv run alembic upgrade head
```

---

## 7. 扫描执行流程（后端核心）

### 7.1 新增后端模块

建议新增：

- `backend/app/models/codeql.py`
- `backend/app/api/v1/endpoints/static_tasks_codeql.py`

并在 `backend/app/api/v1/endpoints/static_tasks.py` 中：

- include 新 router
- 增加 runtime bind
- 导出 `create_codeql_scan/list_codeql_tasks/...`

### 7.2 执行步骤（单任务）

1. 校验 `project_id`、`target_path`、`languages`。
2. 若 `languages` 包含 `cpp` 且 `build_command` 为空，直接 400。
3. 创建任务记录（`pending` -> `running`）。
4. 准备扫描工作区：
   - `project/`
   - `output/`
   - `logs/`
   - `meta/`
5. 复制项目代码到 `project/`。
6. 调用 runner 容器执行 CodeQL 建库与分析。
7. 解析 `output/results.sarif`。
8. 写入 `codeql_findings`。
9. 更新任务统计与状态。
10. 失败时记录 `error_message`，并保持产物可排障。

### 7.3 建库与分析命令策略

推荐“按语言循环建库和分析，最后聚合 SARIF”：

- DB 目录：`/scan/output/db/<lang>`
- 结果：`/scan/output/results-<lang>.sarif`
- 汇总：后端解析时支持多文件合并

示例命令模板（runner 内执行）：

```bash
# python
codeql database create /scan/output/db/python \
  --language=python \
  --source-root=/scan/project

codeql database analyze /scan/output/db/python \
  codeql/python-queries \
  --format=sarif-latest \
  --threads=0 \
  --ram=8192 \
  --output=/scan/output/results-python.sarif

# javascript-typescript
codeql database create /scan/output/db/javascript-typescript \
  --language=javascript-typescript \
  --source-root=/scan/project

codeql database analyze /scan/output/db/javascript-typescript \
  codeql/javascript-queries \
  --format=sarif-latest \
  --threads=0 \
  --ram=8192 \
  --output=/scan/output/results-js.sarif

# cpp (必须 build_command)
codeql database create /scan/output/db/cpp \
  --language=cpp \
  --command="make" \
  --source-root=/scan/project

codeql database analyze /scan/output/db/cpp \
  codeql/cpp-queries \
  --format=sarif-latest \
  --threads=0 \
  --ram=8192 \
  --output=/scan/output/results-cpp.sarif
```

### 7.4 失败处理约束

- 任一语言建库失败：该任务记 `failed`，写入失败日志与命令快照。
- 必须保留：`meta/runner.json` + `logs/*` + 已产出的 `results-*.sarif`。
- 重试策略：默认人工重试，不自动重跑。

---

## 8. CodeQL 查询与多语言策略

### 8.1 默认查询策略

首版默认使用官方 language query pack：

- Python：`codeql/python-queries`
- JS/TS：`codeql/javascript-queries`
- C/C++：`codeql/cpp-queries`

默认套件级别：`security-extended`（可通过参数切换）。

### 8.2 查询级别建议

- `default`：噪音较低，适合初始上线。
- `security-extended`：首版推荐。
- `security-and-quality`：后续可逐步引入。

### 8.3 C/C++ 特别约束

- `build_command` 必须真实可编译。
- 默认模板：`make`
- 常见替代：`cmake --build build`、`ninja -C build`
- 若命令不可用，直接拒绝任务并返回明确错误。

---

## 9. API 设计（最终契约）

### 9.1 路由列表

- `POST /api/v1/static-tasks/codeql/scan`
- `GET /api/v1/static-tasks/codeql/tasks`
- `GET /api/v1/static-tasks/codeql/tasks/{id}`
- `POST /api/v1/static-tasks/codeql/tasks/{id}/interrupt`
- `DELETE /api/v1/static-tasks/codeql/tasks/{id}`
- `GET /api/v1/static-tasks/codeql/tasks/{id}/findings`
- `PATCH /api/v1/static-tasks/codeql/findings/{id}/status`

### 9.2 创建任务请求示例

```json
{
  "project_id": "8d3f2f4a-xxxx-xxxx-xxxx-1b2c3d4e5f6a",
  "name": "静态分析-CodeQL-demo",
  "target_path": ".",
  "languages": ["python", "javascript-typescript", "cpp"],
  "build_command": "make",
  "query_suite": "security-extended",
  "threads": 0,
  "ram_mb": 8192
}
```

### 9.3 响应字段基线

`CodeqlScanTaskResponse` 至少包含：

- `id/project_id/name/status/target_path/languages/build_command/query_suite`
- `total_findings/high_count/medium_count/low_count`
- `scan_duration_ms/files_scanned/error_message`
- `created_at/updated_at`

`CodeqlFindingResponse` 至少包含：

- `id/scan_task_id/rule_id/rule_name/severity/message`
- `file_path/start_line/start_col/end_line/end_col`
- `status`

### 9.4 入参校验规则

- `languages` 不能为空。
- `languages` 仅允许 `python/javascript-typescript/cpp`。
- 包含 `cpp` 时 `build_command` 必填。
- `threads` 范围：`0` 或正整数。
- `ram_mb` 最小值建议 `2048`。

---

## 10. 前端改造（完整链路）

### 10.1 引擎枚举

文件：`frontend/src/shared/constants/scanEngines.ts`

- 在 `SCAN_ENGINE_TABS` 增加 `"codeql"`。
- 更新默认展示策略（可保持 `opengrep` 为默认 tab）。

### 10.2 前端 API 客户端

新增：`frontend/src/shared/api/codeql.ts`

功能对齐现有 `bandit.ts/phpstan.ts`：

- `createCodeqlScanTask`
- `getCodeqlScanTasks`
- `getCodeqlScanTask`
- `interruptCodeqlScanTask`
- `deleteCodeqlScanTask`
- `getCodeqlFindings`
- `updateCodeqlFindingStatus`

### 10.3 创建任务弹窗

文件：`frontend/src/components/scan/CreateScanTaskDialog.tsx`

新增 CodeQL 选项与参数控件：

- 语言多选（python/js-ts/cpp）
- 构建命令输入框（当选择 `cpp` 时必填）
- 查询套件选择（`default/security-extended`）
- 线程与内存高级参数

### 10.4 任务和结果展示

- 在任务聚合统计中纳入 `codeql_tasks` 与 `codeql_findings`。
- 在静态审计结果页中新增 CodeQL 过滤与详情展示。

---

## 11. 预检与发布链路

### 11.1 Runner Preflight 扩展

文件：`backend/app/services/runner_preflight.py`

新增 preflight spec：

- `name="codeql"`
- `image=settings.SCANNER_CODEQL_IMAGE`
- `dockerfile="docker/codeql-runner.Dockerfile"`
- `command=["codeql", "version"]`

### 11.2 Docker Compose 扩展

`docker-compose.yml` / `docker-compose.full.yml` 的 backend 环境增加 `SCANNER_CODEQL_IMAGE` 等配置，沿用现有 `SCANNER_*_IMAGE` 规范。

### 11.3 发布流水线扩展

文件：`.github/workflows/docker-publish.yml`

新增 input 与 build step：

- input：`build_codeql_runner`（bool）
- step：构建并推送 `docker/codeql-runner.Dockerfile`
- tag：`ghcr.io/${{ github.repository_owner }}/Argus-codeql-runner:${{ github.event.inputs.tag }}`

---

## 12. 分阶段部署步骤（Dev -> Staging -> Prod）

### 12.1 开发环境

1. 新建 codeql runner Dockerfile。
2. 新增后端配置与模型、API、路由。
3. 新增前端 API 与创建任务入口。
4. 执行 DB migration。
5. 本地 `docker compose up --build` 联调。

### 12.2 测试环境

1. 推送包含 codeql runner 的镜像。
2. 设置 `SCANNER_CODEQL_IMAGE` 指向测试标签。
3. 导入 3 个样例仓库（Python/JS/C++）验证。

### 12.3 生产环境

1. 灰度开启 CodeQL 按钮（可先仅管理员可见）。
2. 首周仅开放 `python/js-ts`，第二周再开放 `cpp`（可选策略）。
3. 观察任务失败率与平均耗时，达到阈值后全量放开。

---

## 13. 故障排查

### 13.1 Docker 安装失败

症状：`codeql version` 不可执行。

排查：

1. 检查 bundle 下载 URL 与版本号。
2. 检查 `PATH` 是否包含 `/opt/codeql/codeql`。
3. 检查是否误用 Alpine/musl。

### 13.2 建库失败（尤其 C/C++）

症状：`database create` 返回非 0。

排查：

1. `build_command` 是否在 runner 可用。
2. `target_path` 与 `source-root` 是否正确。
3. 项目是否缺少构建依赖（`make/g++/cmake`）。

### 13.3 SARIF 解析失败

症状：任务完成但 findings 为 0 或报解析错误。

排查：

1. 检查 `output/results-*.sarif` 是否生成。
2. 检查 JSON 是否完整（runner 提前退出会产生空文件）。
3. 检查后端解析器是否兼容 `runs/results` 结构。

### 13.4 任务状态异常

症状：任务长期 `running`。

排查：

1. 检查容器是否超时未回收。
2. 检查中断逻辑是否调用 `stop_scanner_container_sync`。
3. 检查状态更新事务是否回滚。

---

## 14. 验收标准与运维策略

### 14.1 验收清单（必须全部通过）

1. `docker build -f docker/codeql-runner.Dockerfile .` 成功。
2. `docker run --rm <image> codeql version` 成功。
3. `codeql resolve languages` 包含 `python/javascript/cpp`。
4. API 可创建任务并落库。
5. Python、JS/TS、C/C++ 三类样例均可完成一次扫描。
6. findings 可在前端查看并更新状态。
7. 失败任务可保留日志且可重试。
8. 不影响现有六类扫描引擎。
9. preflight 与 `docker-publish` 已包含 codeql runner。

### 14.2 运行 SLO 建议

- 任务成功率：>= 95%
- 中位耗时：
  - Python/JS：<= 15 分钟
  - C/C++：<= 30 分钟
- 故障恢复：P1 问题 4 小时内缓解

### 14.3 升级与回滚

- 升级：每月评估 `CODEQL_BUNDLE_VERSION`。
- 先在测试环境回归三语言样例，再生产灰度。
- 回滚：仅回滚 `SCANNER_CODEQL_IMAGE` 标签，不回滚 backend 主镜像。

### 14.4 误报治理

- 采用 findings `status` 生命周期：`open -> verified/false_positive`。
- 所有 `false_positive` 必须附带原因与复审日期。

---

## 附录 A：后端改造最小文件清单

- `docker/codeql-runner.Dockerfile`
- `backend/app/core/config.py`
- `backend/app/models/codeql.py`
- `backend/alembic/versions/*_add_codeql_scan_tables.py`
- `backend/app/api/v1/endpoints/static_tasks_codeql.py`
- `backend/app/api/v1/endpoints/static_tasks.py`
- `backend/app/services/runner_preflight.py`
- `docker-compose.yml`
- `docker-compose.full.yml`
- `.github/workflows/docker-publish.yml`

## 附录 B：前端改造最小文件清单

- `frontend/src/shared/constants/scanEngines.ts`
- `frontend/src/shared/api/codeql.ts`
- `frontend/src/components/scan/CreateScanTaskDialog.tsx`
- 任务列表/详情聚合模块（按现有 dashboard/task 页面实现位置对齐）

## 附录 C：快速验证脚本（示例）

```bash
# 1) 构建 codeql runner
docker build -f docker/codeql-runner.Dockerfile -t Argus/codeql-runner-local:latest .

# 2) 启动平台
docker compose up -d --build

# 3) 检查后端日志（确认 preflight 包含 codeql）
docker compose logs backend | rg -n "preflight|codeql"

# 4) 通过 API 创建一次 codeql 任务（示意）
# curl -X POST http://localhost:8000/api/v1/static-tasks/codeql/scan ...
```

