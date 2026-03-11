# Locate Enclosing Function Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve `locate_enclosing_function` so it accepts more realistic call shapes, resolves enclosing functions more reliably across local and verification pipelines, and exposes a stable structured contract for downstream consumers.

**Architecture:** Keep the public tool name and top-level payload shape (`enclosing_function`, `symbols`, `resolution_method`, `diagnostics`) stable. Optimize the implementation in three layers: normalize request inputs before execution, keep tree-sitter-first resolution with stronger regex fallback and clearer diagnostics, and move payload parsing/selection into one shared normalization path so local stringified dict output and MCP-style JSON output behave the same.

**Tech Stack:** Python backend tools, Pydantic, lightweight tree-sitter locator, pytest, existing agent routing and verification pipelines.

---

### Task 1: Shared locator payload normalization

**Files:**
- Create: `/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/function_locator_payload.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/agents/base.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/agents/verification.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_verification_function_locator_fallback.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_agent_verify_reachability_pipeline.py`

**Step 1: Write the failing tests**
- Add one test proving verification enrichment can parse local `locate_enclosing_function` output when it arrives as a Python-literal dict string.
- Add one test proving reachability and verification pick the same best symbol when both `enclosing_function` and `symbols` are present.

**Step 2: Run tests to verify they fail**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_verification_function_locator_fallback.py tests/test_agent_verify_reachability_pipeline.py -q -s -k locate`

**Step 3: Write minimal implementation**
- Add a shared helper that accepts JSON, fenced JSON, and Python-literal dict payloads.
- Centralize symbol selection rules so both agent pipelines use the same covering-range and nearest-distance logic.
- Replace duplicated ad hoc parsing in `BaseAgent` and `VerificationAgent` with the shared helper.

**Step 4: Run tests to verify they pass**
- Re-run the same pytest command.

### Task 2: Input normalization and request contract hardening

**Files:**
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/tools/file_tool.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/mcp/router.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/agents/base.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_locate_enclosing_function_tool.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_mcp_tool_routing.py`

**Step 1: Write the failing tests**
- Add tests for `file_path:line` input, `line` vs `line_start` precedence, and `path` alias handling.
- Add a routing test asserting `locate_enclosing_function` exposes one normalized line field and one normalized path field in metadata/routing output.

**Step 2: Run tests to verify they fail**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_locate_enclosing_function_tool.py tests/test_mcp_tool_routing.py -q -s -k locate_enclosing_function`

**Step 3: Write minimal implementation**
- Reuse the existing `file_path:line` parser inside `LocateEnclosingFunctionTool`.
- Make the local execution path and router path normalize the same input aliases without diverging.
- Preserve the current public contract: relative project paths in payload, positive line numbers only.

**Step 4: Run tests to verify they pass**
- Re-run the same pytest command.

### Task 3: Resolution accuracy and fallback diagnostics

**Files:**
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/function_locator.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/function_locator_cli.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_locate_enclosing_function_tool.py`
- Create: `/home/xyf/AuditTool/backend/tests/test_function_locator_cli.py`

**Step 1: Write the failing tests**
- Add coverage for unsupported-language diagnostics, tree-sitter miss fallback, nested/covering function preference, and representative regex fallback cases for Python and C-like files.
- Add at least one regression test for a control-structure false positive and one for pseudo-function names such as compiler attributes.

**Step 2: Run tests to verify they fail**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_locate_enclosing_function_tool.py tests/test_function_locator_cli.py -q -s`

**Step 3: Write minimal implementation**
- Keep tree-sitter as the primary engine.
- Tighten regex fallback boundaries and diagnostics so misses can be distinguished from parse failures, disabled languages, and empty files.
- Ensure fallback result selection stays aligned with the tree-sitter covering-range rule.

**Step 4: Run tests to verify they pass**
- Re-run the same pytest command.

### Task 4: Verification and reachability pipeline integration

**Files:**
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/agents/base.py`
- Modify: `/home/xyf/AuditTool/backend/app/services/agent/agents/verification.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_verification_function_locator_fallback.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_agent_verify_reachability_pipeline.py`
- Test: `/home/xyf/AuditTool/backend/tests/test_agent_read_scope_budget.py`

**Step 1: Write the failing tests**
- Add one integration test proving `verify_reachability` can continue into `extract_function` after a normalized locator result.
- Add one integration test proving verification enrichment records diagnostics consistently for local success, parser failure, and no-function cases.

**Step 2: Run tests to verify they fail**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_verification_function_locator_fallback.py tests/test_agent_verify_reachability_pipeline.py tests/test_agent_read_scope_budget.py -q -s`

**Step 3: Write minimal implementation**
- Update both pipelines to consume the shared normalized locator result instead of duplicating best-effort parsing.
- Keep current blocked-reason handling and MCP failure reporting unchanged unless tests show a regression.
- Ensure missing-function results stay non-fatal and still expose diagnostics for downstream decisions.

**Step 4: Run tests to verify they pass**
- Re-run the same pytest command.

### Task 5: Tool documentation and regression verification

**Files:**
- Modify: `/home/xyf/AuditTool/backend/docs/agent-tools/skills/locate_enclosing_function.skill.md`
- Modify: `/home/xyf/AuditTool/backend/docs/agent-tools/MCP_TOOL_PLAYBOOK.md`
- Modify: `/home/xyf/AuditTool/backend/scripts/generate_runtime_tool_docs.py`

**Step 1: Update docs**
- Document accepted input shapes (`file_path`, `path`, `file_path:line`, `line_start`, `line`) and the expected payload contract.
- Clarify that resolution order is tree-sitter first, regex fallback second, and that diagnostics are intended for downstream reasoning instead of user-facing errors.

**Step 2: Run targeted verification**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_locate_enclosing_function_tool.py tests/test_function_locator_cli.py tests/test_verification_function_locator_fallback.py tests/test_mcp_tool_routing.py tests/test_agent_verify_reachability_pipeline.py -q -s`

**Step 3: Run broader regression verification**
- Run: `cd /home/xyf/AuditTool/backend && PYTHONPATH=.venv/lib/python3.12/site-packages python3 -m pytest tests/test_agent_virtual_skill_routing.py tests/test_mcp_catalog.py tests/test_tool_skills_memory_sync.py -q -s -k locate_enclosing_function`

**Step 4: Review output and stop if contract drift appears**
- Confirm that public tool name, payload keys, and strict-mode local routing behavior remain unchanged.
