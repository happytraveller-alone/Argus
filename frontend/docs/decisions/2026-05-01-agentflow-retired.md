# ADR: Retire agentflow-based intelligent audit feature

**Status**: Accepted  
**Date**: 2026-05-01  
**Deciders**: Development team

## Context

The agentflow-based intelligent audit feature was the initial implementation of AI-powered security analysis in Argus. It consisted of:

- Python-based AgentFlow pipeline (`backend/agentflow/`, `vendor/agentflow-src/`)
- Rust runtime integration (`backend/src/runtime/agentflow/`)
- Dedicated Docker runner service (`agentflow-runner`)
- Frontend UI for task creation, monitoring, and results (`frontend/src/pages/AgentAudit/`)
- API endpoints for agent tasks, events, and findings (`/api/v1/agent-tasks/*`)

After evaluation, we decided to retire this implementation because:

1. **Architecture mismatch**: The agentflow vendor dependency and Python pipeline added complexity that didn't align with the Rust-first backend direction.
2. **Reimplementation planned**: Codex will provide a fresh intelligent audit implementation with better integration into the existing architecture.
3. **Limited production usage**: The feature had minimal production deployment, making retirement less disruptive.

## Decision

We will completely retire the agentflow-based intelligent audit feature:

- **Backend**: Remove all agentflow runtime code, agent task routes, and Python pipeline code.
- **Frontend**: Replace intelligent audit pages with "在开发中" (In Development) placeholder stubs.
- **Vendor**: Delete `vendor/agentflow-src/` and related patches.
- **Docker**: Remove `agentflow-runner` service and related infrastructure.
- **Data**: Drop `agent_tasks` from project metrics and task state; remove agentflow output directories.
- **UI preservation**: Keep route entries and menu items visible but disabled/stubbed to avoid breaking bookmarks and navigation.

The retirement is irreversible from a code standpoint. Git history preserves the implementation for reference.

## Consequences

### Positive

- **Simplified architecture**: Removes Python/vendor dependencies and dual-language complexity.
- **Clean slate for Codex**: No legacy code to work around when implementing the new intelligent audit.
- **Reduced maintenance**: No need to maintain agentflow runner, Python dependencies, or integration code.

### Negative

- **Feature gap**: Intelligent audit functionality is unavailable until Codex reimplementation completes.
- **User impact**: Users who bookmarked intelligent audit pages will see placeholder stubs instead of 404s.

### Neutral

- **Git history preserved**: Full implementation remains in git history for reference.
- **UI stubs maintained**: Routes and menu items stay visible with "在开发中" indicators to signal future availability.
- **Type definitions preserved**: Frontend API client types remain as reference for future implementation.

## Implementation

The retirement was executed in phases:

1. Frontend stubbing with `<InDevelopmentPlaceholder />` component
2. Frontend cross-cutter cleanup (dashboard, project detail, finding detail)
3. Frontend file deletions (AgentAudit pages, hooks, API clients)
4. Backend Rust deletions and modifications
5. Backend Python and vendor deletions
6. Docker/Compose/Env/Scripts cleanup
7. Data migration (drop DB column, remove task state key, delete output directories)
8. Documentation updates and this ADR

Verification: `cargo check`, `cargo test --lib`, `tsc --noEmit`, container startup, and stub page rendering all pass.
