# Parallel Workflow Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an async pytest covering WorkflowOrchestrator parallel execution pathways using the minimal vulnerable project.

**Architecture:** Instantiate WorkflowOrchestratorAgent with deterministic stub sub-agents, seed in-memory queues, run AuditWorkflowEngine with a custom WorkflowConfig, then assert concurrency evidence and emit a structured report.

**Tech Stack:** Python 3.12, pytest asyncio mode, existing agent workflow modules.

---

### Task 1: Build helper fixtures & instrumentation

**Files:**
- Create: `backend/tests/test_parallel_workflow.py`

**Step 1: Define imports and constants**

Add module-level imports (`asyncio`, `pathlib`, `time`, `pytest`, queue classes, workflow modules) and constants for project path + worker config.

**Step 2: Implement `_load_vulnerable_points()` helper**

Parse `test_projects/minimal_test/vulnerable.py` to build four deterministic risk points referencing known lines/titles.

**Step 3: Create `StubAgent` class**

Inside test module, define `StubAgent` with `__init__(name, agent_type, run_hook)` and async `run` that awaits `run_hook` plus `asyncio.sleep` to simulate work, returning `AgentResult(success=True, findings=[...])` according to provided hook.

**Step 4: Provide fixtures for instrumentation storage**

Pytest fixtures returning dicts/lists capturing worker events (`analysis_events`, `verification_events`, `run_durations`).

### Task 2: Compose orchestrator fixture

**Files:**
- Modify: `backend/tests/test_parallel_workflow.py`

**Step 1: Build `orchestrator_fixture`**

Fixture creates `InMemoryReconRiskQueue`, `InMemoryVulnerabilityQueue`, fake `llm_service`, simple `event_emitter` capturing events, seeds recon queue with `_load_vulnerable_points()`, and instantiates `WorkflowOrchestratorAgent` injecting stub sub-agents whose run hooks append to instrumentation lists and enqueue/dequeue findings.

**Step 2: Configure WorkflowConfig**

Inside fixture, yield tuple `(agent, recon_queue, vuln_queue, workflow_config)` with `WorkflowConfig(enable_parallel_analysis=True, analysis_max_workers=3, enable_parallel_verification=True, verification_max_workers=2)`.

### Task 3: Implement the parallel workflow test

**Files:**
- Modify: `backend/tests/test_parallel_workflow.py`

**Step 1: Write async test function**

Decorate with `@pytest.mark.asyncio`. Arrange harness via fixture, instantiate `AuditWorkflowEngine` with config, start perf counter, run `engine.run`, capture elapsed seconds.

**Step 2: Assertions**

Assert `state.phase == WorkflowPhase.COMPLETE`, processed counts match risk points & findings, `len(seen_worker_ids_analysis) > 1`, `len(seen_worker_ids_verification) > 1`, `len(state.all_findings) == expected`, `len(set(f['title'] for f in state.all_findings)) == expected`, and worker instrumentation contains concurrency evidence (timestamps out-of-order or overlapping start times derived from stored events).

**Step 3: Structured report output**

Construct dict `report = {"duration_s": round(elapsed, 3), "analysis_workers_configured": 3, ... , "findings": [...]}` and `print("Parallel Workflow Report:\n" + json.dumps(report, indent=2, ensure_ascii=False))` to satisfy logging requirement.

### Task 4: Run targeted pytest

**Files:**
- None

**Step 1: Execute test**

Command: `cd backend && pytest tests/test_parallel_workflow.py -v`.

**Step 2: Observe output**

Expect PASS and printed structured report under 30 seconds.

### Task 5: Review & handoff

**Files:**
- None

**Step 1: Summarize changes**

After tests, describe file additions, instrumentation behavior, and report contents for review.
