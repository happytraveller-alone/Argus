# Parallel Workflow E2E Test Design

## Context
- Repository: backend service for VulHunter (FastAPI, async LLM-driven agents)
- Recent change: `ParallelPhaseExecutor` enables configurable workers for analysis/verification phases.
- Objective: add a targeted regression test to ensure Workflow orchestration honors the parallel config path without needing API/database layers.

## Scope
- Create `backend/tests/test_parallel_workflow.py` only.
- Test invokes `WorkflowOrchestratorAgent` + `AuditWorkflowEngine` directly with mocked LLMs and deterministic queues.
- Exercise both analysis and verification parallel executors using the minimal vulnerable project fixture.

## Requirements Alignment
1. Use `test_projects/minimal_test/vulnerable.py` as workload (source of 4 known findings).
2. Configure `WorkflowConfig(analysis_max_workers=3, verification_max_workers=2)`.
3. Assert:
   - `WorkflowConfig` propagates into engine + executors.
   - `ParallelPhaseExecutor` initializes worker pools and enforces concurrency (via semaphores/locks) — observed through instrumentation hooks.
   - Combined findings set dedups repeated entries.
   - Structured summary logs execution duration, worker counts, confirmed findings.
4. Keep run time < 30s via mocked agents and synchronous queue drivers.

## Design
### Harness Setup
- Instantiate `WorkflowOrchestratorAgent` with stub `analysis`/`verification` agents whose `.run` methods simulate latency and emit deterministic findings derived from `minimal_test/vulnerable.py` metadata.
- Use `InMemoryReconRiskQueue` seeded with four synthetic risk points referencing `vulnerable.py` line clusters; `InMemoryVulnerabilityQueue` starts empty.
- Provide fake `llm_service` & `event_emitter` to avoid network work.

### Parallel Verification Focus
- Wrap stub agents so each `run` records the `worker_id` (via agent name) into a thread-safe list; also capture timestamps to show overlapping execution windows (coarse granularity sufficient: ensure at least two overlapping workers start before previous finishes by injecting `asyncio.sleep` with staggered durations).
- Spy on `ParallelPhaseExecutor.worker_agents` creation counts and `semaphore._value` transitions via helper exposing metrics.

### Assertions & Reporting
- After `AuditWorkflowEngine.run`, assert `state.phase == COMPLETE`, `state.analysis_risk_points_processed == 4`, `len(state.all_findings) == 4` with deduped titles.
- Inspect orchestrator attributes: `_agent_results` for both phases, `_all_findings` unique, `_verified_queue_fingerprints` length equals findings.
- Validate that recorded worker IDs used >1 unique values per phase, implying multiple workers scheduled.
- Emit final structured report (dict printed via `pprint`) summarizing:
  - wall-clock duration (perf counter difference)
  - configured vs observed worker counts
  - findings list (title + worker assigned)

### Test Style
- Async pytest test using `@pytest.mark.asyncio` (asyncio_mode=auto) to align with rest of suite.
- Provide fixture functions for orchestrator + stub agents for reuse.
- Ensure test cleans up (queues cleared, orchestrator cancellation reset).

## Risks / Mitigations
- **Risk:** Semaphores might allow sequential execution if stub agents finish instantly. *Mitigation:* add `await asyncio.sleep(0.01 + worker_id * 0.005)` inside stub run to overlap.
- **Risk:** Using real vulnerable file content may slow test. *Mitigation:* parse file once to craft risk metadata but keep LLM mocked.
- **Risk:** Race conditions in asserts due to async background tasks. *Mitigation:* rely on orchestrator state after `engine.run()` completes; gather instrumentation from shared lists guarded by `asyncio.Lock` or synchronous list (since test awaits all tasks, data writes sequential under locks from executor).

## Out of Scope
- Modifying production code, queue implementations, or API routes.
- Testing HTTP endpoints or database migrations.
- Validating log formatting beyond structured report.
