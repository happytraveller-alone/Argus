# Sandbox Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Development Testing secondary page that shows CubeSandbox template records and sandbox/task status, using the `/projects` table visual language, with destructive actions limited to FAILED template records/templates only.

**Architecture:** Extend the existing `/api/v1/cubesandbox/templates` namespace with a management overview and bounded FAILED-only cleanup/delete actions. Reuse the existing `/api/v1/cubesandbox-tasks` task list for sandbox status, and add a frontend route under the `devTest` navigation group with typed API wrappers and a Projects-style toolbar/table.

**Tech Stack:** Rust/Axum/sqlx backend, CubeMaster client already present in `runtime/cubesandbox/cubemaster_client.rs`, React/TypeScript frontend, TanStack `DataTable`, Node test runner via `pnpm test:node`.

---

## Scope and Guardrails

- Only operate on template records with `status = failed` and their CubeMaster template IDs.
- Do not delete running sandboxes, completed sandbox task records, project data, scan results, READY/PENDING/BUILDING templates, or generic containerd resources.
- Reset means existing kind-level invalidation (`codeql-cpp/invalidate`, `opengrep/invalidate`) for active template records; it does not delete READY templates.
- Sandbox status display is read-only and sourced from `/api/v1/cubesandbox-tasks` because the current CubeMaster sandbox listing implementation is explicitly best-effort/unavailable.

## File Structure

- `backend/src/db/cubesandbox_templates.rs`
  - Add list-all and FAILED-only delete helpers.
- `backend/src/routes/cubesandbox_templates.rs`
  - Add `GET /`, `DELETE /records/{record_id}`, and `POST /cleanup-failed` under existing `/api/v1/cubesandbox/templates` namespace.
- `backend/tests/cubesandbox_runtime.rs`
  - Add route smoke/contract tests that do not require external CubeMaster and DB-backed tests that skip when `RUST_DATABASE_URL`/`DATABASE_URL` is absent.
- `frontend/src/shared/api/cubesandboxTemplates.ts`
  - Add typed management overview/delete/cleanup/reset wrappers.
- `frontend/src/shared/api/cubesandboxTasks.ts`
  - Add typed list wrapper for existing `/api/v1/cubesandbox-tasks`.
- `frontend/src/pages/sandbox-management/SandboxTemplatesTable.tsx`
  - Projects-style table for template records.
- `frontend/src/pages/SandboxManagement.tsx`
  - Page shell, toolbar, filtering, refresh, cleanup/reset actions, read-only task status table.
- `frontend/src/app/routes.tsx`, `frontend/src/shared/i18n/messages.ts`, `frontend/src/components/layout/TopNavigation.tsx`
  - Add route/nav/i18n/icon.
- `frontend/tests/sandboxManagementPage.test.tsx`, `frontend/tests/sandboxManagementApi.test.ts`, `frontend/tests/sidebarNavigationMetadata.test.ts`
  - Verify page rendering, API contract, and nav metadata.

## Tasks

### Task 1: Backend API red tests

**Files:**
- Modify: `backend/tests/cubesandbox_runtime.rs`

- [ ] Add tests for:
  - `GET /api/v1/cubesandbox/templates` returns a management overview shape when no DB is configured.
  - `POST /api/v1/cubesandbox/templates/cleanup-failed` returns a bounded summary when no DB is configured.
  - DB-backed `DELETE /api/v1/cubesandbox/templates/records/{id}` rejects non-FAILED rows with HTTP 409 and deletes FAILED rows when no CubeMaster template ID is present.
- [ ] Run `cd backend && cargo test cubesandbox_template_management -- --nocapture`.
- [ ] Expected RED before implementation: route not found or missing helpers.

### Task 2: Backend implementation

**Files:**
- Modify: `backend/src/db/cubesandbox_templates.rs`
- Modify: `backend/src/routes/cubesandbox_templates.rs`

- [ ] Add DB helpers:
  - `list_all_history(state, limit)` ordered by `updated_at desc`.
  - `list_failed(state, limit)`.
  - `delete_failed_by_id(state, id)` that returns `None` for missing records, `Conflict`-equivalent data for non-FAILED, and deletes only FAILED rows.
- [ ] Add route serializers and action summaries.
- [ ] For a FAILED row with `template_id`, call `CubemasterClient::delete_template` before deleting the local DB row. If CubeMaster deletion fails, keep the DB row and report the failure.
- [ ] Re-run backend tests from Task 1.

### Task 3: Frontend API and nav red tests

**Files:**
- Create: `frontend/tests/sandboxManagementApi.test.ts`
- Create: `frontend/tests/sandboxManagementPage.test.tsx`
- Modify: `frontend/tests/sidebarNavigationMetadata.test.ts`

- [ ] Add tests that expect:
  - API module exports `getSandboxTemplateManagementOverview`, `deleteFailedSandboxTemplateRecord`, `cleanupFailedSandboxTemplates`, `resetSandboxTemplateKind`.
  - Dev-test nav contains `/sandbox-management` labeled `沙箱管理`.
  - Table markup renders Projects-like columns and disables delete for non-FAILED rows.
- [ ] Run `cd frontend && pnpm test:node sandboxManagement sidebarNavigationMetadata`.
- [ ] Expected RED before implementation: missing route/module/component.

### Task 4: Frontend implementation

**Files:**
- Modify: `frontend/src/shared/api/cubesandboxTemplates.ts`
- Create: `frontend/src/shared/api/cubesandboxTasks.ts`
- Create: `frontend/src/pages/sandbox-management/SandboxTemplatesTable.tsx`
- Create: `frontend/src/pages/SandboxManagement.tsx`
- Modify: `frontend/src/app/routes.tsx`
- Modify: `frontend/src/shared/i18n/messages.ts`
- Modify: `frontend/src/components/layout/TopNavigation.tsx`

- [ ] Implement typed API wrappers.
- [ ] Implement Projects-style toolbar/table page.
- [ ] Add delete confirmation text that explicitly says only FAILED template records/templates are affected.
- [ ] Add cleanup button that calls only the FAILED cleanup API.
- [ ] Add reset buttons for CodeQL/OpenGrep using existing invalidate endpoints.
- [ ] Re-run frontend tests from Task 3.

### Task 5: Full verification and cleanup

**Files:**
- Potential docs update: `docs/architecture.md`, `docs/cubesandbox-python-quickstart.md`, `docs/glossary.md`

- [ ] Run focused backend tests.
- [ ] Run focused frontend tests.
- [ ] Run frontend type/lint check if focused tests pass.
- [ ] Run `$neat-freak` once after code changes and reconcile docs if needed.
- [ ] Complete prompt-to-artifact audit before final response.
