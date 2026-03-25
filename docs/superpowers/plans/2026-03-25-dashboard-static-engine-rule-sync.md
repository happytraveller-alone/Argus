# Dashboard Static Engine Rule Sync Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard static engine rule totals match the default counts shown on the scan engine pages for each static engine.

**Architecture:** Keep the dashboard frontend consuming `snapshot.static_engine_rule_totals`, and fix the backend snapshot aggregation so it uses the same default counting rules as the engine pages. Cover the mismatched engines with regression tests before changing the aggregation logic, then verify the returned snapshot still maps cleanly into the existing dashboard chart.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, React, TypeScript

---

### Task 1: Lock The Regression In Backend Tests

**Files:**
- Modify: `backend/tests/test_dashboard_snapshot_v2.py`
- Test: `backend/tests/test_dashboard_snapshot_v2.py`

- [ ] **Step 1: Write the failing test**

Add or extend a dashboard snapshot test that sets up:
- Bandit snapshot rules where only part of the rules have persisted state rows
- PHPStan snapshot rules where only part of the rules have persisted state rows
- YASA snapshot rules plus custom rule configs

Assert that `static_engine_rule_totals` matches the rule-page default totals:
- `bandit` counts full visible snapshot rules, not only persisted state rows
- `phpstan` counts full visible snapshot rules, not only persisted state rows
- `yasa` counts built-in rules plus custom rule configs

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project . pytest backend/tests/test_dashboard_snapshot_v2.py -k static_engine_rule_totals`
Expected: FAIL because dashboard snapshot still under-counts `bandit`, `phpstan`, or `yasa`

- [ ] **Step 3: Write minimal implementation**

Update dashboard snapshot aggregation in `backend/app/api/v1/endpoints/projects_insights.py` so static engine rule totals are derived with the same default counting semantics as:
- `frontend/src/pages/BanditRules.tsx`
- `frontend/src/pages/PhpstanRules.tsx`
- `frontend/src/pages/YasaRules.tsx`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project . pytest backend/tests/test_dashboard_snapshot_v2.py -k static_engine_rule_totals`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_dashboard_snapshot_v2.py backend/app/api/v1/endpoints/projects_insights.py
git commit -m "fix: sync dashboard static engine rule totals"
```

### Task 2: Verify Existing Dashboard Frontend Contract Still Holds

**Files:**
- Inspect: `frontend/src/features/dashboard/components/DashboardCommandCenter.tsx`
- Test: `frontend/tests/dashboardCommandCenter.test.tsx`

- [ ] **Step 1: Confirm no frontend mapping change is needed**

Verify the frontend chart already renders `snapshot.static_engine_rule_totals` directly and only needs correct backend data.

- [ ] **Step 2: Run focused frontend test**

Run: `npm test -- dashboardCommandCenter`
Expected: PASS, confirming the chart still accepts the same snapshot payload shape

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/dashboardCommandCenter.test.tsx frontend/src/features/dashboard/components/DashboardCommandCenter.tsx
git commit -m "test: verify dashboard static rule chart contract"
```

### Task 3: Fresh Verification Before Handoff

**Files:**
- Verify only

- [ ] **Step 1: Run backend regression suite**

Run: `uv run --project . pytest backend/tests/test_dashboard_snapshot_v2.py`
Expected: PASS

- [ ] **Step 2: Run frontend dashboard chart test**

Run: `npm test -- dashboardCommandCenter`
Expected: PASS

- [ ] **Step 3: Review diff for scope**

Run: `git diff -- backend/app/api/v1/endpoints/projects_insights.py backend/tests/test_dashboard_snapshot_v2.py`
Expected: Only the dashboard rule total aggregation and its regression coverage changed
