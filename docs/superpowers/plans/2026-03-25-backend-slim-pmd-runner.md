# Backend Slim PMD Runner Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 backend 开发镜像预热 `/opt/backend-venv` 与现有 `uv` 启动体验的前提下，移除 backend 镜像中仅为 PMD 服务的 Java/PHP 运行时和本地 PMD 安装逻辑，并将 `PMDTool` 改造成通过 `scanner_runner` 按需拉起、扫描完成即删除的专用临时容器执行模式。

**Architecture:** backend 继续负责参数校验、目标路径规范化、扫描 workspace 准备、runner 调度、JSON 报告解析和结果格式化；`pmd-runner` 镜像只承载 Java 运行时与 PMD 7.0.0，不作为 compose 常驻服务存在。`PMDTool` 在每次调用时创建 `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>/...` 工作区，挂载到 runner 的 `/scan`，用 `run_scanner_container(...)` 执行完整命令数组 `["pmd", "check", ...]`，再从固定的 `output/report.json` 读取结果。

**Tech Stack:** FastAPI, Docker SDK for Python, Docker Compose, GitHub Actions, multi-stage Dockerfile, Python 3.11, uv, pytest, PMD 7.0.0, OpenJDK 21 JRE

---

## Execution Notes

- 在开始实现前，先用 `superpowers:using-git-worktrees` 创建隔离 worktree。
- 所有 Python 测试与验证统一使用 `uv run --project . ...`。
- 不改动与本计划无关的现有脏工作区文件。
- 不新增 `static_tasks_pmd.py`、PMD task/db 模型，且不把其他 runner 改成按需模式。

## File Structure

- Create: `backend/docker/pmd-runner.Dockerfile`
  - PMD 专用 runner 镜像；安装 JRE、下载 PMD 7.0.0、保证 `pmd` 在 `PATH` 中、`WORKDIR /scan`。
- Create: `backend/tests/test_pmd_runner_contracts.py`
  - Dockerfile、compose、workflow 的 PMD 改造文本契约测试。
- Create: `backend/tests/test_pmd_runner_tool.py`
  - `PMDTool` runner 化后的 workspace、命令构建、ruleset staging、报告解析和错误处理测试。
- Modify: `backend/Dockerfile`
  - 移除 backend runtime 中的 `openjdk-21-jre-headless`、`php-cli`、`unzip` 和 PMD 安装块；保留预热 venv / `uv` / `dev-entrypoint` 体验。
- Modify: `backend/app/core/config.py`
  - 增加 `SCANNER_PMD_IMAGE` 设置。
- Modify: `docker-compose.yml`
  - 给 backend 增加 `SCANNER_PMD_IMAGE` 环境变量；不新增 `pmd-runner` 服务，不新增 `depends_on`。
- Modify: `docker-compose.full.yml`
  - 与默认 compose 对齐 `SCANNER_PMD_IMAGE`；不新增 `pmd-runner` 服务。
- Modify: `backend/app/services/agent/tools/external_tools.py`
  - 将 `PMDTool` 从 sandbox 执行切到 `scanner_runner`，并在文件内本地实现 PMD 专用 workspace / ruleset / parsing helper。
- Modify: `backend/tests/test_external_tools_manual.py`
  - 更新 PMD 手工烟测说明，改为 `SCANNER_PMD_IMAGE` 驱动的按需 runner 模式。
- Modify: `.github/workflows/docker-publish.yml`
  - 增加 `build_pmd_runner` input、构建步骤、GHCR summary 输出。

## Task 1: Lock Backend Slimming With Contract Tests

**Files:**
- Create: `backend/tests/test_pmd_runner_contracts.py`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Write the failing Dockerfile contract test**

在 `backend/tests/test_pmd_runner_contracts.py` 新增：

```python
def test_backend_dockerfile_no_longer_installs_local_pmd_runtime():
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
    runtime_base_block = content.split("FROM runtime-base AS scanner-tools-base", 1)[0]
    runtime_block = content.split("FROM runtime-base AS runtime", 1)[1]
    assert "openjdk-21-jre-headless" not in runtime_base_block
    assert "php-cli" not in runtime_base_block
    assert "unzip" not in runtime_base_block
    assert "pmd-dist-7.0.0-bin.zip" not in runtime_block
    assert "/usr/local/bin/pmd" not in runtime_block
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- FAIL because `backend/Dockerfile` still installs runtime JRE/PHP/unzip and still downloads PMD in the final runtime stage.

- [ ] **Step 3: Remove PMD-only packages from `runtime-base`**

在 `backend/Dockerfile` 的 `RUNTIME_PACKAGES` 中：

- 保留 `libpq5`、`curl`、`git`、`libpango-1.0-0`、`libpangoft2-1.0-0`、`libpangocairo-1.0-0`、`libcairo2`、`libgdk-pixbuf-2.0-0`、`libglib2.0-0`、`shared-mime-info`
- 保留可选 `fonts-noto-cjk`
- 移除 `openjdk-21-jre-headless`
- 移除 `php-cli`
- 移除 `unzip`

- [ ] **Step 4: Make `scanner-tools-base` own its unzip dependency**

在 `backend/Dockerfile` 的 `scanner-tools-base` stage 内加入 stage-local `unzip` 处理，要求：

- 不删除 `scanner-tools-base`
- 不再依赖 `runtime-base` 预装 `unzip`
- 仅在 YASA 发行包解压路径上安装/提供 `unzip`

- [ ] **Step 5: Delete the final runtime PMD install block**

删除 `backend/Dockerfile` final `runtime` stage 中从 `PMD_CACHE` 下载、复制、解压 PMD，并创建 `/usr/local/bin/pmd` 的整段逻辑；保留 venv 复制、`site-packages` 清理和 `pip` 清理。

- [ ] **Step 6: Verify dev experience is still untouched**

人工核对这些语句仍保留：

```dockerfile
COPY --from=builder /opt/backend-venv /opt/backend-venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
ENV VIRTUAL_ENV=/opt/backend-venv
CMD ["/usr/local/bin/backend-dev-entrypoint.sh"]
```

且不修改 `backend/scripts/dev-entrypoint.sh`。

- [ ] **Step 7: Re-run the Dockerfile contract test**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- PASS for the backend Dockerfile contract.

- [ ] **Step 8: Commit the slimming baseline**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/Dockerfile backend/tests/test_pmd_runner_contracts.py
git commit -m "refactor: slim backend runtime for PMD runner split"
```

## Task 2: Add the Dedicated PMD Runner Image and Config Wiring

**Files:**
- Create: `backend/docker/pmd-runner.Dockerfile`
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.full.yml`
- Modify: `backend/tests/test_pmd_runner_contracts.py`

- [ ] **Step 1: Extend the contract tests for image wiring without a compose service**

在 `backend/tests/test_pmd_runner_contracts.py` 新增：

```python
def test_compose_exposes_scanner_pmd_image_without_pmd_runner_service(): ...
def test_full_overlay_exposes_scanner_pmd_image_without_pmd_runner_service(): ...
```

断言点：

- `SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}`
- `docker-compose.yml` 中不存在 `pmd-runner:`
- `docker-compose.full.yml` 中不存在 `pmd-runner:`
- backend `depends_on` 中不包含 `pmd-runner`

测试实现要求：

- 所有合同测试都基于 `Path(__file__).resolve().parents[2]` 之类的 repo-root 解析来读文件
- 不要假设 pytest 的当前工作目录是仓库根目录

- [ ] **Step 2: Run the contract tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- FAIL because `SCANNER_PMD_IMAGE` is not wired yet.

- [ ] **Step 3: Create `backend/docker/pmd-runner.Dockerfile`**

实现约束：

- 基础镜像保持 `python:3.11-slim` 风格，与现有 runner 对齐
- 安装 `ca-certificates`、`curl`、`unzip`、`openjdk-21-jre-headless`
- 复用现有 runner 的 APT mirror / fallback 风格
- 下载 `pmd-dist-7.0.0-bin.zip`
- 解压到 `/opt/pmd-bin-7.0.0`
- 创建 `/usr/local/bin/pmd`
- `WORKDIR /scan`
- 不依赖 `ENTRYPOINT ["pmd"]`，只需保证 `pmd` 在 `PATH` 中
- 默认 `CMD ["pmd", "--version"]`

- [ ] **Step 4: Add `SCANNER_PMD_IMAGE` to settings**

在 `backend/app/core/config.py` 的 scanner image 区块中新增：

```python
SCANNER_PMD_IMAGE: str = "vulhunter/pmd-runner:latest"
```

- [ ] **Step 5: Wire `SCANNER_PMD_IMAGE` into default compose**

在 `docker-compose.yml` 的 backend `environment` 中新增：

```yaml
SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}
```

不要新增：

- `pmd-runner` service
- backend 对 `pmd-runner` 的 `depends_on`

- [ ] **Step 6: Wire `SCANNER_PMD_IMAGE` into full overlay compose**

在 `docker-compose.full.yml` 的 backend `environment` 中新增相同变量，且同样不要新增 `pmd-runner` service 或 `depends_on`。

- [ ] **Step 7: Re-run the contract tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- PASS for Dockerfile + compose contract assertions.

- [ ] **Step 8: Commit the runner image and wiring**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/docker/pmd-runner.Dockerfile backend/app/core/config.py docker-compose.yml docker-compose.full.yml backend/tests/test_pmd_runner_contracts.py
git commit -m "feat: add dedicated PMD runner image wiring"
```

## Task 3: Move `PMDTool` From Sandbox to `scanner_runner`

**Files:**
- Modify: `backend/app/services/agent/tools/external_tools.py`
- Create: `backend/tests/test_pmd_runner_tool.py`

- [ ] **Step 1: Write failing PMD runner invocation tests**

在 `backend/tests/test_pmd_runner_tool.py` 新增：

```python
async def test_pmd_tool_uses_scanner_runner_image(...): ...
async def test_pmd_tool_does_not_initialize_sandbox(...): ...
async def test_pmd_tool_creates_workspace_under_scan_workspace_root(...): ...
async def test_pmd_tool_uses_scan_project_for_dot_target(...): ...
async def test_pmd_tool_uses_scan_project_for_empty_target(...): ...
async def test_pmd_tool_uses_scan_project_for_dot_slash_target(...): ...
async def test_pmd_tool_maps_security_alias_to_exact_rulesets(...): ...
async def test_pmd_tool_maps_quickstart_alias_to_exact_rulesets(...): ...
async def test_pmd_tool_maps_all_alias_to_exact_rulesets(...): ...
async def test_pmd_tool_uses_project_local_ruleset_path_without_staging(...): ...
async def test_pmd_tool_stages_external_ruleset_into_meta_rules(...): ...
```

关键断言：

- 不再调用 `SandboxManager.initialize()`
- 不再调用 `SandboxManager.execute_tool_command(...)`
- 调用 `run_scanner_container(...)`
- `ScannerRunSpec.image == settings.SCANNER_PMD_IMAGE`
- `workspace_dir` 位于 `settings.SCAN_WORKSPACE_ROOT / "pmd-tool" / <uuid>`
- `ScannerRunSpec.command` 为完整数组 `["pmd", "check", ...]`
- `ScannerRunSpec.expected_exit_codes == [0, 4]`
- `ScannerRunSpec.env == {}`
- `ScannerRunSpec.artifact_paths == ["output/report.json"]`
- `--report-file /scan/output/report.json`
- `target_path="."`、`""`、`"./"` 时 runner 目标路径都为 `/scan/project`
- `ruleset="security"`、`"quickstart"`、`"all"` 时，最终传给 runner 的 `--rulesets` 必须与 spec 中的 exact mapping 一致
- 项目内 `.xml` ruleset 直接映射为 `/scan/project/...`
- 项目外 `.xml` ruleset 才复制到 `/scan/meta/rules/...`

- [ ] **Step 2: Write failing target-path validation tests**

继续在 `backend/tests/test_pmd_runner_tool.py` 新增：

```python
async def test_pmd_tool_rejects_absolute_target_path(...): ...
async def test_pmd_tool_rejects_parent_traversal_target_path(...): ...
async def test_pmd_tool_rejects_missing_project_subpath(...): ...
```

断言点：

- 绝对路径直接失败
- 包含 `..` 的路径直接失败
- Windows 反斜杠会先规范化再校验
- 不存在的项目内相对路径明确失败
- 不再沿用旧的“路径不存在则回退到项目根目录”行为

- [ ] **Step 3: Run the new PMD tool tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py -v
```

Expected:
- FAIL because `PMDTool` still routes through sandbox and still uses the old path behavior.

- [ ] **Step 4: Add PMD-only helper functions inside `external_tools.py`**

在 `PMDTool` 附近实现最小本地 helper，推荐拆分为：

```python
def _normalize_pmd_target_path(...): ...
def _prepare_pmd_workspace(...): ...
def _resolve_pmd_ruleset(...): ...
def _stage_pmd_ruleset(...): ...
def _build_pmd_runner_command(...): ...
def _read_pmd_report(...): ...
def _normalize_pmd_violation_path(...): ...
```

要求：

- 不引入 `static_tasks_shared.py`
- 只在 `external_tools.py` 内本地实现
- workspace 布局固定为 `project/`、`output/`、`logs/`、`meta/`
- `run_id` 使用 `uuid4().hex`
- `project/` 用 `shutil.copytree(..., dirs_exist_ok=True, symlinks=True)` 复制项目树，并避免把 workspace 自身递归复制回去
- symlink 不做解引用复制
- 复制保护规则写成明确 helper：
  - 先判断 `workspace_dir.resolve()` 是否位于 `project_root.resolve()` 之下
  - 若不在项目树内，则 `copytree` 不需要额外 ignore workspace 前缀
  - 若在项目树内，则基于 `os.path.relpath(workspace_dir, project_root)` 取出首段目录名，并在 `copytree(ignore=...)` 中忽略该目录
  - 测试至少覆盖一次“workspace 位于 project_root 下仍不会把自身递归复制回 project/”的场景

- [ ] **Step 5: Replace sandbox execution with `run_scanner_container(...)`**

将 `PMDTool._execute(...)` 改为：

```python
process_result = await run_scanner_container(
    ScannerRunSpec(
        scanner_type="pmd-tool",
        image=settings.SCANNER_PMD_IMAGE,
        workspace_dir=str(workspace_dir),
        command=[
            "pmd",
            "check",
            "--dir",
            runner_target_path,
            "--rulesets",
            selected_ruleset,
            "--format",
            "json",
            "--report-file",
            "/scan/output/report.json",
            "--no-cache",
        ],
        timeout_seconds=180,
        env={},
        expected_exit_codes=[0, 4],
        artifact_paths=["output/report.json"],
    )
)
```

- [ ] **Step 6: Keep metadata and user-facing text contract stable**

实现时保留这些字段：

```python
metadata = {
    "findings_count": ...,
    "high_count": ...,
    "medium_count": ...,
    "low_count": ...,
    "findings": violations[:10],
    "raw_result": pmd_result,
}
```

并继续输出中文摘要文本，而不是把原始 JSON 直接暴露给用户。

- [ ] **Step 7: Re-run the PMD tool tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py -v
```

Expected:
- PASS for invocation, workspace, ruleset staging, and target-path validation coverage.

- [ ] **Step 8: Commit the runner invocation migration**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/app/services/agent/tools/external_tools.py backend/tests/test_pmd_runner_tool.py
git commit -m "refactor: run PMD tool through scanner runner"
```

## Task 4: Lock Report Parsing and Failure Semantics

**Files:**
- Modify: `backend/app/services/agent/tools/external_tools.py`
- Modify: `backend/tests/test_pmd_runner_tool.py`
- Modify: `backend/tests/test_external_tools_manual.py`

- [ ] **Step 1: Write failing report and error-handling tests**

在 `backend/tests/test_pmd_runner_tool.py` 补充：

```python
async def test_pmd_tool_accepts_exit_code_4_and_parses_report(...): ...
async def test_pmd_tool_fails_on_unexpected_exit_code(...): ...
async def test_pmd_tool_fails_when_report_missing_for_success_exit(...): ...
async def test_pmd_tool_fails_when_report_json_is_invalid(...): ...
async def test_pmd_tool_fails_when_ruleset_file_cannot_be_resolved(...): ...
async def test_pmd_tool_normalizes_scan_project_paths(...): ...
async def test_pmd_tool_cleans_workspace_after_success_and_failure(...): ...
```

断言点：

- `exit_code=4` 仍被当作成功且能读取 `output/report.json`
- `exit_code not in {0, 4}` 时失败，并引用保留的 stderr/stdout 信息
- `report.json` 缺失或 JSON 非法时，即使退出码是 `0/4` 也失败
- ruleset 引用不存在、复制失败或未知非 XML ruleset 字符串时返回明确错误摘要
- 未知 ruleset 不回退到默认 `security`
- PMD 报告中的 `/scan/project/...` 路径会被归一化成项目相对路径
- 成功和失败两条路径都会在调用结束时清理 `<SCAN_WORKSPACE_ROOT>/pmd-tool/<uuid>`

- [ ] **Step 2: Write a failing manual-doc regression assertion**

在 `backend/tests/test_pmd_runner_contracts.py` 或 `backend/tests/test_pmd_runner_tool.py` 新增一个轻量文本断言，确认 `backend/tests/test_external_tools_manual.py` 的 PMD 段落提到了 `SCANNER_PMD_IMAGE` 和按需 runner 模式。

- [ ] **Step 3: Run the parsing/error tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py -v
```

Expected:
- FAIL because the new parsing / missing-report / path-normalization behaviors are not all implemented yet.

- [ ] **Step 4: Implement output-first parsing and failure branches**

在 `external_tools.py` 中固定这些行为：

- 优先读取 `output/report.json`
- 不再从 stdout 猜测 JSON
- `exit_code in {0, 4}` 时强制要求存在且能解析 `report.json`
- `exit_code not in {0, 4}` 时构造失败摘要，并在内部使用 `process_result.stderr_path` / `stdout_path` / `error`
- 成功路径不向用户暴露 `logs/` 或宿主机路径

- [ ] **Step 5: Update the manual PMD smoke test notes**

在 `backend/tests/test_external_tools_manual.py` 的 PMD 段落中：

- 保留测试入口
- 更新注释为 `SCANNER_PMD_IMAGE` 驱动的按需 runner
- 说明它仍是 opt-in 手工烟测，不纳入默认自动化验收

- [ ] **Step 6: Re-run the PMD tool tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_tool.py tests/test_pmd_runner_contracts.py -v
```

Expected:
- PASS for parsing, failure semantics, manual-doc text contract, and metadata/path normalization coverage.

- [ ] **Step 7: Commit the parsing and diagnostics pass**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/app/services/agent/tools/external_tools.py backend/tests/test_pmd_runner_tool.py backend/tests/test_external_tools_manual.py backend/tests/test_pmd_runner_contracts.py
git commit -m "feat: finalize PMD runner report handling"
```

## Task 5: Publish the PMD Runner Image

**Files:**
- Modify: `.github/workflows/docker-publish.yml`
- Modify: `backend/tests/test_pmd_runner_contracts.py`

- [ ] **Step 1: Write the failing workflow contract test**

在 `backend/tests/test_pmd_runner_contracts.py` 新增：

```python
def test_docker_publish_workflow_builds_pmd_runner(): ...
```

断言点：

- `build_pmd_runner`
- `./backend/docker/pmd-runner.Dockerfile`
- `ghcr.io/${{ github.repository_owner }}/vulhunter-pmd-runner:${{ github.event.inputs.tag }}`

- [ ] **Step 2: Run the contract tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- FAIL because the publish workflow does not yet include PMD runner steps.

- [ ] **Step 3: Add the workflow input**

在 `.github/workflows/docker-publish.yml` 中新增：

```yaml
build_pmd_runner:
  description: '构建 PMD runner 镜像'
  required: false
  type: boolean
  default: true
```

- [ ] **Step 4: Add the PMD runner build step and summary line**

要求：

- 构建步骤与其他 runner 相邻
- `context: ./backend`
- `file: ./backend/docker/pmd-runner.Dockerfile`
- `cache-from` / `cache-to` 使用 `scope=pmd-runner`
- summary 输出风格与其他 runner 完全一致

- [ ] **Step 5: Re-run the workflow contract tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_runner_contracts.py -v
```

Expected:
- PASS for the workflow contract.

- [ ] **Step 6: Commit the publish wiring**

Run:

```bash
cd /home/xyf/AuditTool
git add .github/workflows/docker-publish.yml backend/tests/test_pmd_runner_contracts.py
git commit -m "ci: publish PMD runner image"
```

## Task 6: Verify the End-to-End PMD Runner Slice

**Files:**
- Modify if needed: `backend/tests/test_pmd_runner_contracts.py`
- Modify if needed: `backend/tests/test_pmd_runner_tool.py`

- [ ] **Step 1: Run the minimal automated verification suite**

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
- PASS for the new PMD contract tests, PMD tool tests, and existing `scanner_runner` tests.
- Do not require `tests/test_docker_compose_dev_flow.py` to go green as part of this task.

- [ ] **Step 2: Build the two relevant images**

Run:

```bash
cd /home/xyf/AuditTool
docker build -f backend/docker/pmd-runner.Dockerfile -t vulhunter/pmd-runner-local:latest backend
docker compose build backend
```

Expected:
- Both images build successfully.

- [ ] **Step 3: Verify compose does not prewarm PMD**

Run:

```bash
cd /home/xyf/AuditTool
docker compose config
```

Expected:
- backend contains `SCANNER_PMD_IMAGE`
- output does not define a `pmd-runner` service
- backend `depends_on` does not include `pmd-runner`

- [ ] **Step 4: Verify backend image no longer contains Java, PHP, or PMD**

Run:

```bash
docker run --rm vulhunter/backend-local:latest sh -lc 'command -v java || true; command -v php || true; command -v pmd || true'
```

Expected:
- No effective executable path is printed for `java`, `php`, or `pmd`.

- [ ] **Step 5: Verify the PMD runner image contains Java and PMD**

Run:

```bash
docker run --rm vulhunter/pmd-runner-local:latest sh -lc 'java -version >/dev/null 2>&1 && pmd --version >/dev/null 2>&1'
```

Expected:
- Exit code `0`.

- [ ] **Step 6: Run the optional PMD manual smoke test if Docker is available**

Run:

```bash
cd /home/xyf/AuditTool/backend
RUN_EXTERNAL_TOOLS_MANUAL_TESTS=1 \
SCANNER_PMD_IMAGE=vulhunter/pmd-runner-local:latest \
uv run --project . pytest tests/test_external_tools_manual.py -k pmd -v -s
```

Expected:
- PMDTool only creates a temporary runner container when the tool is invoked
- the container exits and is removed after the scan
- console output stays limited to scan summaries / error summaries, without extra debug noise

- [ ] **Step 7: Commit any verification-only test adjustments**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/tests/test_pmd_runner_contracts.py backend/tests/test_pmd_runner_tool.py
git commit -m "test: finalize PMD runner verification coverage"
```
