# Sandbox Runner Containerization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `run_code`、`sandbox_exec`、`verify_vulnerability` 及现有沙箱兼容调用路径，从直接依赖 `SandboxManager + Docker SDK` 的实现，迁移为参考 `flow-parser-runner` 的按需一次性 `sandbox-runner` 容器执行模式。

**Architecture:** 新增 `SandboxRunSpec`、`SandboxRunResult`、`run_sandbox_container(...)` 和 `SandboxRunnerClient`，让工具层通过显式 runner client 调用独立的 `sandbox-runner` 镜像。保留 `SandboxManager` 作为薄兼容层，将其 `execute_command(...)`、`execute_http_request(...)`、`verify_vulnerability(...)` 统一委托到新 client，避免一次性重写遗留沙箱工具。

**Tech Stack:** Python, Docker SDK, FastAPI backend, existing scanner runner patterns, Docker Compose, pytest, uv

---

## File Structure

### New Files

- `backend/app/services/sandbox_runner.py`
  - 新的 sandbox runner 执行底座，定义 spec/result，同步封装容器启动、日志留存、元数据写入与清理
- `backend/app/services/sandbox_runner_client.py`
  - 提供高层 client，负责 workspace 准备、profile 到 spec 的映射、命令执行和结果回传
- `backend/docker/sandbox-runner.Dockerfile`
  - 新的 runner 镜像构建文件，参考 `backend/docker/flow-parser-runner.Dockerfile`
- `backend/tests/test_sandbox_runner.py`
  - `run_sandbox_container(...)` 的底层契约测试
- `backend/tests/test_sandbox_runner_client.py`
  - `SandboxRunnerClient` 的 workspace、profile、image fallback、结果解析测试

### Modified Files

- `backend/app/core/config.py`
  - 新增 `SANDBOX_RUNNER_IMAGE`，并对 `SANDBOX_IMAGE` 保留 fallback 兼容
- `backend/app/services/agent/tools/sandbox_tool.py`
  - `SandboxManager` 退化为兼容门面，内部改用 `SandboxRunnerClient`
- `backend/app/services/agent/tools/run_code.py`
  - 改为显式依赖新 client 或兼容门面，保持现有 tool 输出协议不变
- `docker-compose.yml`
  - 增加 `sandbox-runner` 本地构建校验服务，并为 backend 注入新镜像配置
- `docker-compose.full.yml`
  - 同步增加 `sandbox-runner` 构建与镜像配置
- `.github/workflows/docker-publish.yml`
  - 增加 `sandbox-runner` 镜像构建和发布入口
- `backend/tests/simple_sandbox_test.py`
  - smoke test 改为验证新 runner 路径

### Existing Files To Reference

- `backend/app/services/scanner_runner.py`
- `backend/app/services/flow_parser_runner.py`
- `backend/docker/flow-parser-runner.Dockerfile`
- `docker/sandbox/Dockerfile`
- `backend/tests/test_flow_parser_runner_client.py`
- `backend/tests/test_run_code_tool.py`
- `backend/tests/test_agent_tool_registry.py`

## Implementation Tasks

### Task 1: Define sandbox runner execution contracts

**Files:**
- Create: `backend/app/services/sandbox_runner.py`
- Test: `backend/tests/test_sandbox_runner.py`

- [ ] **Step 1: Write the failing tests for spec/result and runner execution contract**

Add tests that verify:

- `SandboxRunSpec` captures `image`, `command`, `workspace_dir`, `timeout_seconds`, `env`, `network_mode`, `read_only`, `user`, `mounts`, `tmpfs`, `expected_exit_codes`
- `run_sandbox_container(...)` writes retained logs and `runner.json`-style metadata
- `network_mode`, `security_opt`, `cap_drop`, `tmpfs`, and custom mounts are passed to Docker correctly

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run --project . -s pytest backend/tests/test_sandbox_runner.py -q
```

Expected: tests fail because `sandbox_runner.py` does not exist yet.

- [ ] **Step 3: Implement `SandboxRunSpec`, `SandboxRunResult`, and `run_sandbox_container(...)`**

Implementation requirements:

- Mirror the style of `scanner_runner.py` but keep sandbox-specific runtime controls explicit
- Support `volumes`, `tmpfs`, `network_mode`, `read_only`, `user`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges:true"]`
- Mount a prepared workspace to a fixed runner path such as `/sandbox`
- Persist `stdout.log`, `stderr.log`, and `meta/runner.json` under the workspace
- Return truncated log paths in failures, same spirit as scanner runner

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_sandbox_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_runner.py backend/tests/test_sandbox_runner.py
git commit -m "feat: add sandbox runner execution contracts"
```

### Task 2: Add a high-level `SandboxRunnerClient`

**Files:**
- Create: `backend/app/services/sandbox_runner_client.py`
- Test: `backend/tests/test_sandbox_runner_client.py`

- [ ] **Step 1: Write the failing tests for workspace/profile/image resolution**

Add tests that verify:

- workspaces are created under `SCAN_WORKSPACE_ROOT/sandbox-runner/<run_id>`
- `isolated_exec` maps to `network_mode=none`
- `network_verify` maps to `network_mode=bridge`
- project root is mounted read-only and scratch/temp paths are writable
- `SANDBOX_RUNNER_IMAGE` is preferred and `SANDBOX_IMAGE` remains fallback-compatible

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run --project . -s pytest backend/tests/test_sandbox_runner_client.py -q
```

Expected: FAIL because the client does not exist.

- [ ] **Step 3: Implement `SandboxRunnerClient`**

Implementation requirements:

- Provide methods for:
  - generic command execution
  - HTTP request execution
  - vulnerability verification
- Prepare workspace layout with stable subdirectories like:

```text
<SCAN_WORKSPACE_ROOT>/sandbox-runner/<run_id>/
  input/
  output/
  logs/
  meta/
```

- Map profile names to runtime controls centrally, not in each tool
- Return a tool-friendly result shape compatible with current `SandboxManager` callers

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_sandbox_runner_client.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_runner_client.py backend/tests/test_sandbox_runner_client.py
git commit -m "feat: add sandbox runner client"
```

### Task 3: Rewire `SandboxManager` into a compatibility facade

**Files:**
- Modify: `backend/app/services/agent/tools/sandbox_tool.py`
- Test: `backend/tests/test_run_code_tool.py`
- Test: `backend/tests/simple_sandbox_test.py`

- [ ] **Step 1: Write or update failing tests for compatibility behavior**

Add or update tests that verify:

- `SandboxManager.execute_command(...)` still returns the same shape expected by `run_code` and `sandbox_exec`
- `execute_http_request(...)` still switches to networked execution semantics
- `verify_vulnerability(...)` still returns `is_vulnerable`, `evidence`, `response_status`, and `error`

- [ ] **Step 2: Run targeted tests to verify failures**

Run:

```bash
uv run --project . -s pytest backend/tests/test_run_code_tool.py -q
```

Expected: FAIL after tests are tightened for the new delegation path.

- [ ] **Step 3: Replace direct Docker logic inside `SandboxManager`**

Implementation requirements:

- Keep public method names intact
- Move image selection and execution to `SandboxRunnerClient`
- Preserve existing result keys like `success`, `stdout`, `stderr`, `exit_code`, `error`, `image`, `image_candidates`
- Keep `initialize()`/`is_available` semantics meaningful for callers, but have them reflect runner-image/runtime availability instead of raw inline Docker setup

- [ ] **Step 4: Run targeted tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_run_code_tool.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/tools/sandbox_tool.py backend/tests/test_run_code_tool.py backend/tests/simple_sandbox_test.py
git commit -m "refactor: route sandbox manager through sandbox runner client"
```

### Task 4: Migrate verification tools to the new runner path

**Files:**
- Modify: `backend/app/services/agent/tools/run_code.py`
- Modify: `backend/app/services/agent/tools/sandbox_tool.py`
- Test: `backend/tests/test_run_code_tool.py`
- Test: `backend/tests/agent/test_tools.py`

- [ ] **Step 1: Add failing tests for profile-specific execution**

Add tests that verify:

- `run_code` uses the isolated execution profile
- `sandbox_exec` uses the isolated execution profile
- `verify_vulnerability` uses the network verification profile
- tool metadata remains unchanged for frontend and verification agent consumers

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
uv run --project . -s pytest backend/tests/test_run_code_tool.py backend/tests/agent/test_tools.py -q
```

Expected: FAIL until tool wiring is updated.

- [ ] **Step 3: Rewire tool construction and execution**

Implementation requirements:

- `RunCodeTool` should stop assuming inline Docker orchestration
- `SandboxTool` and `VulnerabilityVerifyTool` should delegate through the new client/facade
- No changes to tool names, args schema, or evidence metadata layout
- No prompt updates required for `VerificationAgent`

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_run_code_tool.py backend/tests/agent/test_tools.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/tools/run_code.py backend/app/services/agent/tools/sandbox_tool.py backend/tests/test_run_code_tool.py backend/tests/agent/test_tools.py
git commit -m "refactor: migrate verification tools to sandbox runner"
```

### Task 5: Add the dedicated sandbox runner image and config wiring

**Files:**
- Create: `backend/docker/sandbox-runner.Dockerfile`
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.full.yml`
- Modify: `.github/workflows/docker-publish.yml`

- [ ] **Step 1: Write failing tests or assertions for config and compose references**

Add/update tests or snapshots that verify:

- backend config exposes `SANDBOX_RUNNER_IMAGE`
- compose injects the runner image and build-check service
- workflow includes sandbox runner build/publish branches

- [ ] **Step 2: Run the relevant tests to verify they fail**

Run:

```bash
uv run --project . -s pytest backend/tests/test_docker_compose_dev_flow.py backend/tests/test_compose_up_with_fallback.py -q
```

Expected: FAIL until config and compose are updated.

- [ ] **Step 3: Implement image/config/compose changes**

Implementation requirements:

- Build `backend/docker/sandbox-runner.Dockerfile` from the current sandbox runtime capability set
- Prefer extracting only what verification and legacy sandbox callers actually need
- Add a one-shot `sandbox-runner` service like `flow-parser-runner`
- Pass `SANDBOX_RUNNER_IMAGE` into backend env
- Keep `SANDBOX_IMAGE` as temporary fallback alias

- [ ] **Step 4: Run the relevant tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_docker_compose_dev_flow.py backend/tests/test_compose_up_with_fallback.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/docker/sandbox-runner.Dockerfile backend/app/core/config.py docker-compose.yml docker-compose.full.yml .github/workflows/docker-publish.yml
git commit -m "feat: add sandbox runner image and delivery wiring"
```

### Task 6: Validate legacy compatibility and public tool surface

**Files:**
- Modify: `backend/tests/test_agent_tool_registry.py`
- Modify: `backend/tests/test_agent_prompt_contracts.py`
- Modify: `backend/tests/test_legacy_cleanup.py`

- [ ] **Step 1: Tighten tests for public surface stability**

Add or confirm assertions that:

- public core tools remain `run_code`, `sandbox_exec`, `verify_vulnerability`
- removed tools remain absent from the registered tool surface
- prompt contracts still mention the same verification tools

- [ ] **Step 2: Run the focused tests to verify failures if any**

Run:

```bash
uv run --project . -s pytest backend/tests/test_agent_tool_registry.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_legacy_cleanup.py -q
```

Expected: either FAIL due to drift introduced by migration, or PASS after minor assertion updates.

- [ ] **Step 3: Adjust tests and compatibility code only as needed**

Implementation requirements:

- Do not re-export removed sandbox language/vulnerability tools
- Keep legacy compatibility at code level, not at public registry level

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
uv run --project . -s pytest backend/tests/test_agent_tool_registry.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_legacy_cleanup.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_agent_tool_registry.py backend/tests/test_agent_prompt_contracts.py backend/tests/test_legacy_cleanup.py
git commit -m "test: lock sandbox runner public tool surface"
```

### Task 7: Run end-to-end verification

**Files:**
- No new source files expected
- Validate touched files from prior tasks

- [ ] **Step 1: Run the backend test suites most impacted by the migration**

Run:

```bash
uv run --project . -s pytest \
  backend/tests/test_sandbox_runner.py \
  backend/tests/test_sandbox_runner_client.py \
  backend/tests/test_run_code_tool.py \
  backend/tests/agent/test_tools.py \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_agent_prompt_contracts.py \
  backend/tests/test_legacy_cleanup.py \
  backend/tests/test_docker_compose_dev_flow.py \
  backend/tests/test_compose_up_with_fallback.py -q
```

Expected: PASS.

- [ ] **Step 2: Run an opt-in smoke test for real Docker integration**

Run:

```bash
RUN_SANDBOX_TESTS=1 uv run --project . -s pytest backend/tests/simple_sandbox_test.py -q
```

Expected: PASS in an environment with Docker access and locally built runner image.

- [ ] **Step 3: Record any environment assumptions**

Document in the final implementation summary:

- whether Docker was available
- whether the runner image had to be built locally
- whether smoke tests were skipped

- [ ] **Step 4: Commit final integration validation changes**

```bash
git add .
git commit -m "test: verify sandbox runner containerization end to end"
```

## Notes And Constraints

- Prefer WSL bash for repo inspection and command execution
- Use `uv run` for Python validation commands
- Use `uv run --project . -s` for Python tests
- Keep the verification tool protocol stable for frontend and agent consumers
- Do not reintroduce removed sandbox public tools into the main registry
- Preserve the current semantic split:
  - no-network execution for `run_code` and `sandbox_exec`
  - bridge-network verification for `verify_vulnerability`
