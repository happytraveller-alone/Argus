# Rust Gateway Shell Flowchart

## Sources consulted

- `backend/src/main.rs:8` — backend process entry.
- `backend/src/app.rs:5-14` — builds Axum router and fallback.
- `backend/src/routes/mod.rs:16-30` — owns API route nesting.
- `backend/src/routes/mod.rs:32-49` — health handler reads bootstrap status.

## Concrete findings

- `build_router(state)` merges `routes::owned_routes()` and attaches `AppState`.
- `owned_routes()` maps `/api/v1/projects`, `/api/v1/static-tasks`, `/api/v1/agent-tasks`, `/api/v1/system-config`, `/api/v1/search`, `/api/v1/skills`, and `/api/v1/agent-test`.
- Unknown routes return `404 route not owned by rust gateway`.

```mermaid
flowchart TD
  Main["main starts backend<br/>backend/src/main.rs:8"] --> Build["build_router(state)<br/>backend/src/app.rs:5"]
  Build --> Owned["merge owned_routes()<br/>backend/src/routes/mod.rs:16"]
  Owned --> Health["GET /health<br/>backend/src/routes/mod.rs:18"]
  Owned --> Projects["/api/v1/projects<br/>backend/src/routes/mod.rs:26"]
  Owned --> Static["/api/v1/static-tasks<br/>backend/src/routes/mod.rs:29"]
  Owned --> Agent["/api/v1/agent-tasks<br/>backend/src/routes/mod.rs:20"]
  Owned --> Config["/api/v1/system-config<br/>backend/src/routes/mod.rs:25"]
  Build --> Fallback["404 fallback<br/>backend/src/app.rs:8"]
  Health --> Bootstrap["read bootstrap report<br/>backend/src/routes/mod.rs:42"]
```

## Side effects

- Router construction has no domain side effects.
- Health handler reads `state.bootstrap` only.

## External dependencies

- All domain route modules.

## Confidence / gaps

- **Confidence**: High.
- **Gaps**: Did not inspect server binding in full `main.rs` beyond entry point.
