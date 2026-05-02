# PATHFINDER Handoff Prompts

Copy one prompt into `/make-plan` when ready. These prompts intentionally stop at planning; implementation should happen through `/do` or the repo’s normal approved execution lane after tests are specified.

## Unified System A — Retired Static Engine API Quarantine

```text
/make-plan Plan a narrow cleanup for Argus retired static-engine frontend API wrappers.

Target unified component and single entry point:
- Keep `frontend/src/shared/api/opengrep.ts:createOpengrepScanTask` as the only active static audit task creation API.

Exact call sites/files to evaluate and rewrite/delete:
- Current active static API: `frontend/src/shared/api/opengrep.ts:423-515`.
- Retired/residual wrappers: legacy `frontend/src/shared/api/<retired-engine>.ts` static-engine API files.
- Confirm current docs boundary: `docs/architecture.md:32-41`.

Relevant flowcharts:
- `PATHFINDER-2026-04-30/01-flowcharts/static-audit-opengrep.md`
- `PATHFINDER-2026-04-30/02-duplication-report.md#d1--parallel-static-engine-frontend-api-wrappers-accidental-residue-consolidate-by-deletionretirement-boundary`

Plan requirements:
1. First run an import/test usage search for retired static-engine API exports.
2. If unused by current app/tests, plan deletion.
3. If legacy tests still need them, plan a quarantine/retired namespace with explicit docs and no active UI imports.
4. Include frontend typecheck/test commands.

Anti-pattern guards:
- Do not build a static-engine registry/factory.
- Do not re-enable retired backend routes.
- Do not change current Opengrep API behavior.
- Prefer deletion over wrappers around unsupported APIs.
```

## Unified System B — Backend Attachment Header Utility

```text
/make-plan Plan a narrow backend utility extraction for duplicate Content-Disposition attachment header construction.

Target unified component and single entry point:
- New small backend helper such as `backend/src/http/download.rs::attachment_content_disposition(filename: &str, ascii_fallback: &str) -> String`.

Exact call sites to rewrite:
- `backend/src/routes/projects.rs:1442-1479` — project archive `build_content_disposition`, `ascii_fallback_filename`, `percent_encode_utf8`.
- `backend/src/routes/agent_tasks.rs:1973-2013` — report `build_content_disposition`, `percent_encode_utf8`.
- Preserve report-specific filename builders at `backend/src/routes/agent_tasks.rs:1917-1949`.
- Preserve project archive download call at `backend/src/routes/projects.rs:488-514`.
- Preserve report download calls at `backend/src/routes/agent_tasks.rs:1074-1115`.

Relevant flowcharts:
- `PATHFINDER-2026-04-30/01-flowcharts/project-workspace.md`
- `PATHFINDER-2026-04-30/01-flowcharts/intelligent-audit-agentflow.md`
- `PATHFINDER-2026-04-30/02-duplication-report.md#d3--content-disposition--utf-8-percent-encoding-duplicated-in-two-route-modules-accidental-consolidate`

Plan requirements:
1. Add regression tests for ASCII fallback and UTF-8 filename* output before changing helpers.
2. Extract only HTTP attachment-header encoding.
3. Keep domain-specific filename construction local to route modules.
4. Run Rust tests covering both project archive and agent report download helper behavior.

Anti-pattern guards:
- Do not change public filename formats beyond unifying equivalent encoding.
- Do not introduce a broad HTTP utility crate/module hierarchy.
- Do not move AgentTask report naming into the generic helper.
```

## Unified System C — Narrow Task Snapshot Mutation Helper

```text
/make-plan Plan a conservative backend refactor for repeated task snapshot load-mutate-save boilerplate.

Target unified component and single entry points:
- `backend/src/db/task_state.rs::mutate_static_task(...)`
- `backend/src/db/task_state.rs::mutate_agent_task(...)`

Exact call sites to consider rewriting:
- Static progress update: `backend/src/routes/static_tasks.rs:1468-1496`.
- Static failure update: `backend/src/routes/static_tasks.rs:1499-1527`.
- Static interrupt: `backend/src/routes/static_tasks.rs:1602-1627`.
- Agent cancel: `backend/src/routes/agent_tasks.rs:705-731`.
- Agent finding updates: `backend/src/routes/agent_tasks.rs:870-928` if the helper can preserve aggregate refresh semantics.
- Shared snapshot primitives: `backend/src/db/task_state.rs:292-365`.

Relevant flowcharts:
- `PATHFINDER-2026-04-30/01-flowcharts/static-audit-opengrep.md`
- `PATHFINDER-2026-04-30/01-flowcharts/intelligent-audit-agentflow.md`
- `PATHFINDER-2026-04-30/02-duplication-report.md#d2--task-lifecycle-mutation-is-duplicated-across-static-and-intelligent-routes-partly-legitimate-helper-worthy`

Plan requirements:
1. Lock behavior with Rust regression tests for static progress/failure/interrupt and agent cancel/status updates before refactor.
2. Design helpers to preserve current error handling, snapshot save semantics, and returned response shapes.
3. Keep static and intelligent record models separate.
4. Keep file format unchanged.

Anti-pattern guards:
- Do not create a generic `Task` trait or merge status models.
- Do not change task-state JSON schema.
- Do not refactor runner execution in the same plan.
- Do not batch unrelated AgentTask importer changes into this cleanup.
```
