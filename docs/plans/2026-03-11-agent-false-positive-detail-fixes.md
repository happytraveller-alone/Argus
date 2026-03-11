# Agent False Positive Detail Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix agent audit event-log alignment, detail-return scrolling, and false-positive finding persistence/detail loading so false-positive detail routes stop flashing 404.

**Architecture:** Keep the existing `agent_findings` persistence path and extend it with degraded false-positive storage in `verification_result` plus `finding_metadata`, then make frontend detail loading prefer persisted findings and temporarily fall back to route snapshot state. Frontend log restoration should only manipulate internal container scroll state and must not call `scrollIntoView` on the page.

**Tech Stack:** FastAPI, SQLAlchemy ORM, React, TypeScript, node:test, pytest

---

### Task 1: Add failing frontend tests for log layout and scroll restoration

**Files:**
- Modify: `frontend/tests/agentAuditLogEntry.test.tsx`
- Create: `frontend/tests/agentAuditScrollRestore.test.ts`
- Modify: `frontend/src/pages/AgentAudit/index.tsx`
- Modify: `frontend/src/pages/AgentAudit/utils.ts`

**Step 1: Write the failing tests**

- Assert the event-log header and row grid use the same six-column template and the action column is left aligned.
- Add a pure helper test proving scroll restoration only returns a container `scrollTop` target and never relies on `scrollIntoView`.

**Step 2: Run the targeted frontend tests to verify they fail**

Run: `cd frontend && pnpm test -- --runInBand agentAuditLogEntry.test.tsx agentAuditScrollRestore.test.ts`

Expected: FAIL because the current layout still right-aligns the action header/cell and the helper does not exist yet.

**Step 3: Implement the minimal frontend changes**

- Extract scroll-target calculation into a pure helper in `frontend/src/pages/AgentAudit/utils.ts`.
- Update `restoreAndScrollToAnchor` in `frontend/src/pages/AgentAudit/index.tsx` to restore panel scroll positions and then scroll only the relevant container.
- Align the log header/action column with the row grid.

**Step 4: Run the targeted frontend tests to verify they pass**

Run: `cd frontend && pnpm test -- --runInBand agentAuditLogEntry.test.tsx agentAuditScrollRestore.test.ts`

Expected: PASS

### Task 2: Add failing backend tests for degraded false-positive persistence

**Files:**
- Modify: `backend/tests/test_agent_findings_strict_validation.py`
- Modify: `backend/tests/test_agent_findings_persistence.py`
- Modify: `backend/app/api/v1/endpoints/agent_tasks.py`

**Step 1: Write the failing tests**

- Replace the legacy assertion that false positives are discarded.
- Add a test showing `false_positive` findings persist even when file path, line number, and code context are unavailable, while preserving `verification_evidence`, `verification_todo_id`, and `verification_fingerprint`.

**Step 2: Run the targeted backend tests to verify they fail**

Run: `cd backend && pytest tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py -q`

Expected: FAIL because `_save_findings` still filters false positives through the strict file/context gates.

**Step 3: Implement the minimal backend changes**

- Branch `_save_findings` so `false_positive` findings can persist with minimal detail.
- Store verification identifiers in `finding_metadata` and mirror them in `verification_result` for serialization.
- Keep the strict validation path for non-false-positive findings unchanged.

**Step 4: Run the targeted backend tests to verify they pass**

Run: `cd backend && pytest tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py -q`

Expected: PASS

### Task 3: Add failing detail-endpoint and route-snapshot tests

**Files:**
- Modify: `backend/tests/test_agent_finding_detail_endpoint.py`
- Modify: `frontend/tests/findingRouteNavigation.test.ts`
- Modify: `frontend/tests/findingDetailFalsePositiveMode.test.ts`
- Modify: `frontend/src/shared/utils/findingRoute.ts`
- Modify: `frontend/src/pages/FindingDetail.tsx`
- Modify: `frontend/src/shared/api/agentTasks.ts`
- Modify: `backend/app/api/v1/endpoints/agent_tasks.py`

**Step 1: Write the failing tests**

- Backend: assert `get_agent_finding(..., include_false_positive=True)` returns minimal false-positive detail plus verification identifiers.
- Frontend: assert finding-route state can carry a snapshot payload for temporary false-positive detail rendering.
- Frontend: assert the detail page source contains logic for snapshot fallback instead of direct 404-only handling.

**Step 2: Run the targeted tests to verify they fail**

Run: `cd backend && pytest tests/test_agent_finding_detail_endpoint.py -q`
Run: `cd frontend && pnpm test -- --runInBand findingRouteNavigation.test.ts findingDetailFalsePositiveMode.test.ts`

Expected: FAIL because response models and route state do not carry the snapshot/identifier fields yet.

**Step 3: Implement the minimal detail-loading changes**

- Extend `AgentFindingResponse` and frontend `AgentFinding` with optional verification identifiers.
- Update `_serialize_agent_findings` to source `verification_evidence` correctly and expose `verification_todo_id` / `verification_fingerprint`.
- Extend finding-route state with optional agent-finding snapshot data.
- Update `FindingDetail` to prefer persisted data, then temporarily render snapshot-backed false-positive evidence on a 404 during the refresh window.

**Step 4: Run the targeted tests to verify they pass**

Run: `cd backend && pytest tests/test_agent_finding_detail_endpoint.py -q`
Run: `cd frontend && pnpm test -- --runInBand findingRouteNavigation.test.ts findingDetailFalsePositiveMode.test.ts`

Expected: PASS

### Task 4: Add failing realtime merge/event metadata tests

**Files:**
- Modify: `frontend/tests/realtimeFindingsPanelHeaders.test.ts`
- Modify: `frontend/tests/agentAuditEventOrdering.test.ts`
- Modify: `frontend/src/pages/AgentAudit/realtimeFindingMapper.ts`
- Modify: `frontend/src/pages/AgentAudit/index.tsx`
- Modify: `backend/app/services/agent/agents/verification.py`

**Step 1: Write the failing tests**

- Verify realtime false-positive events and persisted findings merge using verification identifiers.
- Verify false-positive events carry the fields needed for the temporary detail snapshot and action label.

**Step 2: Run the targeted tests to verify they fail**

Run: `cd frontend && pnpm test -- --runInBand realtimeFindingsPanelHeaders.test.ts agentAuditEventOrdering.test.ts`

Expected: FAIL if merge/snapshot fields are still incomplete.

**Step 3: Implement the minimal merge/event changes**

- Ensure verification events include `authenticity`, `verdict`, `verification_evidence`, original path/line, and verification identifiers.
- Build navigation state from the merged realtime finding when opening false-positive detail.

**Step 4: Run the targeted tests to verify they pass**

Run: `cd frontend && pnpm test -- --runInBand realtimeFindingsPanelHeaders.test.ts agentAuditEventOrdering.test.ts`

Expected: PASS

### Task 5: Run focused verification before completion

**Files:**
- No code changes expected

**Step 1: Run the combined targeted test set**

Run: `cd backend && pytest tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_finding_detail_endpoint.py tests/test_event_manager_tool_drain.py -q`
Run: `cd frontend && pnpm test -- --runInBand agentAuditLogEntry.test.tsx agentAuditScrollRestore.test.ts realtimeFindingsPanelHeaders.test.ts findingRouteNavigation.test.ts findingDetailFalsePositiveMode.test.ts agentAuditEventOrdering.test.ts`

**Step 2: Review failures and fix only regressions introduced by this work**

**Step 3: Report actual verification status with command evidence**
