# Agent Audit Verified Default Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-switch the Agent Audit realtime findings panel to "verified" view once a verified finding exists, while showing guidance when none are verified yet.

**Architecture:** Track two booleans in `TaskDetailPage.tsx` (auto-applied + user override). A watcher inspects realtime/persisted findings, applies the verified filter once, and resets per task. `RealtimeFindingsPanel` adopts a richer empty state plus a CTA to revert filters, and `onFiltersChange` gains an optional metadata argument so user actions can be distinguished.

**Tech Stack:** React 18 + TypeScript, pnpm, node:test for SSR-based component tests.

---

### File Map
- Modify: `frontend/src/pages/AgentAudit/TaskDetailPage.tsx` — state flags, filter handler, auto-switch effect.
- Modify: `frontend/src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx` — extended prop typing, empty-state CTA, helper text, wiring metadata back to parent.
- Modify: `frontend/src/pages/AgentAudit/types.ts` — update prop type definition for `onFiltersChange` signature.
- Add: `frontend/src/pages/AgentAudit/components/__tests__/hasVerifiedFinding.test.ts` (or similar) if pure helpers extracted; otherwise extend existing `frontend/tests/realtimeFindingsPanelHeaders.test.ts` and create `frontend/tests/agentAuditVerifiedFilter.test.tsx`.
- Modify: `frontend/tests/realtimeFindingsPanelHeaders.test.ts` — new assertions for empty-state CTA/hint.

---

### Task 1: Guard + handler plumbing in TaskDetailPage

**Files:**
- Modify: `frontend/src/pages/AgentAudit/TaskDetailPage.tsx`

- [ ] **Step 1:** Add `useState` hooks for `hasAutoAppliedVerifiedFilter` and `userOverrideVerificationFilter`, initialised to `false`. Reset them inside an effect keyed by `taskId` so navigating between tasks clears prior state.
- [ ] **Step 2:** Replace the bare `setFindingsFilters` prop with a memoized `handleFindingsFiltersChange(next, options?)`. Inside, detect whether `next.verification` differs from previous; if `options?.source === "user"` and it changes, set the override flag. Always call `setFindingsFilters(next)`.
- [ ] **Step 3:** Update the JSX that renders `<RealtimeFindingsPanel ... onFiltersChange={...} />` to use the new handler and pass through the extended signature.

### Task 2: Auto-switch effect based on verified findings

**Files:**
- Modify: `frontend/src/pages/AgentAudit/TaskDetailPage.tsx`

- [ ] **Step 1:** Create a `useMemo` or helper function `hasVerifiedFinding` that inspects both `persistedDisplayFindings` and `realtimeFindings` for an item where `is_verified` is true or `verification_progress === "verified"`.
- [ ] **Step 2:** Add a `useEffect` that listens to `hasVerifiedFinding`, `userOverrideVerificationFilter`, `hasAutoAppliedVerifiedFilter`, and `findingsFilters.verification`. If there is at least one verified item, no override yet, and we haven't auto-switched, call `handleFindingsFiltersChange({ ...findingsFilters, verification: "verified" }, { source: "system" })` and flip `hasAutoAppliedVerifiedFilter` to true.
- [ ] **Step 3:** Ensure the effect short-circuits when `findingsFilters.verification` is already `"verified"`, and optionally gate by task type if we later distinguish hybrid/intelligent.

### Task 3: Enhance RealtimeFindingsPanel props & empty state

**Files:**
- Modify: `frontend/src/pages/AgentAudit/types.ts`
- Modify: `frontend/src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx`

- [ ] **Step 1:** Update the `onFiltersChange` prop type in both the component definition and shared types to accept an optional second parameter `{ source?: "user" | "system" }` (default `"user"`).
- [ ] **Step 2:** Adjust the keyword/severity/verification select handlers to call `props.onFiltersChange(nextFilters, { source: "user" })` so the parent can differentiate manual intent.
- [ ] **Step 3:** When rendering the empty state (`tableState.rows.length === 0`), detect `props.filters.verification === "verified"`. Display a message such as “暂无已验证漏洞，切换为全部验证状态可查看所有发现” and render a secondary `Button` that calls `props.onFiltersChange({ ...props.filters, verification: "all" }, { source: "user" })`.
- [ ] **Step 4:** Keep the existing phase-based hints for running scans but append the CTA block only when the verified filter hides everything.

### Task 4: Tests for CTA hint and auto-switch helper

**Files:**
- Modify: `frontend/tests/realtimeFindingsPanelHeaders.test.ts`
- Add: `frontend/tests/agentAuditVerifiedFilter.test.tsx` (new test file targeting the helper/logic)

- [ ] **Step 1:** Extend `realtimeFindingsPanelHeaders.test.ts` with a test that renders the panel with `filters.verification = "verified"` and no verified items, asserting that the hint text and CTA button appear with the expected label.
- [ ] **Step 2:** Add a new node:test suite (e.g., `frontend/tests/agentAuditVerifiedFilter.test.tsx`) exporting the helper (from TaskDetailPage or a new util module). Cover cases: (a) verified items present -> helper true, (b) none verified -> false, (c) false-positive items flagged as verified.
- [ ] **Step 3:** Document in the new test how manual overrides prevent the auto-switch by simulating the logic of the effect (call helper + state booleans). This can be done by unit-testing a pure function, e.g., `shouldApplyVerifiedFilter({ hasVerified, override, alreadyApplied, currentFilter })`.
- [ ] **Step 4:** Run `cd frontend && pnpm test:node` to ensure the SSR tests (including the new ones) pass.

---

Plan complete and saved to `docs/superpowers/plans/2026-03-19-agent-verified-default-plan.md`. Ready to execute?
