# 2026-02-13: Task Duration + Agent Audit Layout

## Scope

This change set implements two UX improvements on branch `refactor/intelligent-audit-realtime-ui`:

1. Projects page task browser: show task duration / elapsed time.
2. Agent Audit task detail page (`/agent-audit/:taskId`): layout refactor
   - Left: event logs
   - Right top: merged realtime findings (unverified + verified)
   - Right bottom: agent section (summary + stats), without agent tree/graph and without security score

## Projects: Task Duration (Task Browser)

### Data sources

- Agent task (`AgentTask`): `created_at`, `started_at`, `completed_at`, `status`
- Static scan:
  - Opengrep scan task: `scan_duration_ms`
  - Optional paired gitleaks scan task: `scan_duration_ms`

### Display rules

- Agent task:
  - Completed: `duration = completed_at - started_at`
  - Running: `elapsed = now - (started_at ?? created_at)` (fallback when started_at missing)
  - Otherwise: `-`
- Static scan:
  - Total duration ms = `opengrep.scan_duration_ms + (pairedGitleaks?.scan_duration_ms ?? 0)`

### UI

In `/#task-browser` items, show:

- `创建时间：...（相对时间）`
- `用时：HH:MM:SS` or `已运行：HH:MM:SS`

Running tasks use a small front-end timer tick to refresh the elapsed label.

## Agent Audit: Layout Refactor

### Layout

- Two columns:
  - Left (narrow): event logs
  - Right (wide): split vertically
    - Top: merged realtime findings list
    - Bottom: agent section (summary + stats)

### Realtime findings merge

Stream finding `id` is not guaranteed to match DB finding id. Therefore merging is best-effort using a fingerprint:

`fingerprint = vulnerability_type + "|" + file_path + "|" + line_start + "|" + title`

When a `finding_verified` arrives:

- If an existing item with same fingerprint exists: upgrade it to `is_verified=true`
- Otherwise: insert as a new verified item

### Removed UI

- Agent list/tree/ownership graph (no longer displayed in the page)
- Security score block in stats panel

## Verification

- `npm --prefix frontend run type-check`
- Manual:
  - `/#task-browser`: duration label appears and running tasks increase over time
  - `/agent-audit/:taskId`: logs left, merged realtime findings top-right, agent summary/stats bottom-right; no security score; no agent tree

