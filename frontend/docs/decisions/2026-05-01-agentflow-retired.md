# ADR: Retire agentflow-based intelligent audit execution path

**Status**: Accepted  
**Date**: 2026-05-01  
**Current tree note**: 2026-05-02 reconciliation — `vendor/agentflow-src/` deletion committed (commit 3b0ce36a, 7776f4bf) but not yet pushed; compatibility/schema/fixture assets remain in `backend/agentflow/` and test surfaces.
**Deciders**: Development team

## Context

The agentflow-based intelligent audit feature was the initial implementation of AI-powered security analysis in Argus. It consisted of:

- Python-based AgentFlow pipeline (`backend/agentflow/`) and vendored AgentFlow source (`vendor/agentflow-src/`)
- Rust runtime integration (`backend/src/runtime/agentflow/`)
- Dedicated Docker runner service (`agentflow-runner`)
- Frontend UI for task creation, monitoring, and results (`frontend/src/pages/AgentAudit/`)
- API endpoints for agent tasks, events, and findings (`/api/v1/agent-tasks/*`)

After evaluation, we decided to retire this implementation because:

1. **Architecture mismatch**: The agentflow vendor dependency and Python pipeline added complexity that didn't align with the Rust-first backend direction.
2. **Reimplementation planned**: Codex will provide a fresh intelligent audit implementation with better integration into the existing architecture.
3. **Limited production usage**: The feature had minimal production deployment, making retirement less disruptive.

## Decision Intent

Retire the old agentflow-based intelligent audit execution path:

- **Backend**: Remove the mounted agent task execution routes and Rust runtime wiring.
- **Frontend**: Replace intelligent audit pages with "在开发中" (In Development) placeholder stubs.
- **Vendor/Pipeline**: Remove `vendor/agentflow-src/`; do not treat the retained `backend/agentflow/` historical assets as active execution paths unless a new implementation explicitly reconnects them.
- **Docker**: Remove `agentflow-runner` from the compose mainline.
- **Data**: Stop relying on `agent_tasks` as the active execution source.
- **UI preservation**: Keep route entries and menu items visible but disabled/stubbed to avoid breaking bookmarks and navigation.

The retirement intent is to prevent new work from extending the old AgentFlow execution chain while leaving room for a cleaner Codex-backed implementation.

## Current Implementation State

As of 2026-05-02 in this checkout:

- `backend/src/routes/mod.rs` does not mount `/api/v1/agent-tasks`.
- `backend/src/runtime/mod.rs` does not export `runtime/agentflow`.
- `docker-compose.yml` does not define an `agentflow-runner` service.
- `frontend/src/app/routes.tsx` renders `InDevelopmentPlaceholder` for `/agent-audit/:taskId`.
- `vendor/agentflow-src/` deletion committed (3b0ce36a, 7776f4bf) awaiting push.
- `backend/agentflow/`, AgentFlow fixture/tests, and some compatibility fields/tests still exist.
- `frontend/src/shared/api/agentTasks.ts` and `frontend/src/pages/AgentAudit/components/*` exist as frontend compatibility shims for active pages that still import old AgentAudit helpers.
- `/api/v1/system-config/agent-preflight` still exists and checks LLM configuration plus runner readiness; it is not an AgentTask creation/execution API.

Therefore this ADR means vendored AgentFlow code is retired, but it must not be read as proof that every AgentFlow-named compatibility or fixture asset was deleted.

## Consequences

### Positive

- **Simplified architecture**: Removes Python/vendor dependencies and dual-language complexity.
- **Cleaner execution boundary**: New work should not extend the old AgentFlow route/runtime/runner path.
- **Clean slate for Codex**: The future intelligent audit implementation can define a new route/runtime/frontend contract.

### Negative

- **Feature gap**: Intelligent audit functionality is unavailable until Codex reimplementation completes.
- **User impact**: Users who bookmarked intelligent audit pages will see placeholder stubs instead of 404s.
- **Residual cleanup risk**: Historical pipeline/test assets remain in the tree and need explicit classification before deletion or reuse.

### Neutral

- **Git history preserved**: Prior implementation history remains available for reference.
- **UI stubs maintained**: Routes and menu items stay visible with "在开发中" indicators to signal future availability.
- **Type definitions preserved**: Frontend API client types remain as reference for future implementation.

## Implementation Status

The current tree reflects these completed pieces:

1. Frontend stubbing with `<InDevelopmentPlaceholder />` component
2. Backend Rust route/runtime unmounting for the old AgentTask execution path
3. Compose mainline removal of `agentflow-runner`
4. Vendor retirement: `vendor/agentflow-src/` deletion committed (3b0ce36a, 7776f4bf) awaiting push
5. Documentation reconciliation to mark residual assets as transition/compatibility surfaces

Known residual surfaces:

- `backend/agentflow/`
- AgentFlow fixture/tests
- frontend AgentAudit compatibility shims
- `/api/v1/system-config/agent-preflight`
- frontend tests and compatibility fields that still use intelligent/agent terminology

Verification for this ADR reconciliation: reference checks against `backend/src/routes/mod.rs`, `backend/src/runtime/mod.rs`, `docker-compose.yml`, and `frontend/src/app/routes.tsx`.
