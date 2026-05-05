# Open Questions

## ralplan-agentflow-streaming - 2026-04-30

- [ ] AgentFlow `agentflow run` stdout trace event format needs empirical verification -- the spec assumes `{"type":"assistant_delta","content":"..."}` format based on code reading of `orchestrator.py` and `traces.py`, but the exact JSON structure should be confirmed by running `agentflow run` with `--output json` and inspecting raw stdout. If the format differs, `parse_agentflow_trace_line()` in the adapter needs adjustment.

- [ ] The `async-stream` crate is needed for the long-lived SSE endpoint in Phase 3. Confirm this dependency is acceptable for the project, or identify an alternative (e.g., manual `Stream` impl, `tokio_stream`, or `axum::response::Sse` with `futures::stream`). Axum's built-in `Sse` type with `futures::stream::Stream` may be preferable to avoid a new dependency.

- [ ] Incremental persistence uses `task_state::save_snapshot()` which rewrites the full JSON file. At high event rates (10 events/s, flush every 2s = 20 events/flush), this means rewriting the full task state file 30 times per minute. For large task states with many findings, this could become an I/O bottleneck. Consider whether an append-only event log file (separate from the snapshot) would be more appropriate for streaming events.

- [ ] The broadcast channel cleanup in `start_agent_task_core` happens synchronously after `run_streaming_command` returns. If an SSE client connects between the runner finishing and the channel being removed, there is a brief window where the client subscribes to a channel that is about to be dropped. The "completed task falls back to snapshot" logic handles this gracefully, but the timing should be verified under load.

- [ ] Frontend `ThinkingTimeline` component needs a design decision on how to accumulate thinking blocks across nodes. The current `useAgentStream` hook tracks a single `thinking` string. For multi-node thinking (env-inter thinking, then vuln-reasoner thinking), the state management needs to accumulate blocks per-role. This likely requires a new state structure in the existing `useAgentAuditState` hook or a dedicated `useThinkingBlocks` hook.

## ralplan-smart-audit-no-thinking-display - 2026-04-30

- [ ] **Phase 0 outcome**: Is `https://cdn.apiport.cc.cd/v1` reachable from `argus-backend-1`? — Decides whether AC1 demo runs against the configured endpoint or against the documented fallback (different reachable endpoint or smaller test project). MUST be probed before Phase 5 verification.

- [ ] **Lane 2 unknown (carried from trace)**: Does `gpt-5.4` via OpenAI Responses API actually emit `assistant_delta` trace lines that the agentflow-runner adapter maps to `thinking_token` events? — If not, even a perfect display fix will show no thinking content for the model in production use; AC1 demo must switch model.

- [ ] **`thinking_end` emission verification**: Are `thinking_end` events actually being broadcast and persisted today, or only `thinking_start`? — Trace says they are persisted by default (the gate excludes only `thinking_token` and `heartbeat`), but no live observation has confirmed they are actually emitted by the runner adapter. If absent, Phase 3 needs to ensure adapter emits them.

- [ ] **Persistence size impact**: After deploying Phase 3, monitor `rust-task-state.json` size growth on long audits. If average task state exceeds ~500KB or task list endpoint slows, activate Task 3.3 cap (currently planned defensively at length > 2000).

- [ ] **`onPhaseStart` callback existence**: Does `streamOptions` already declare `onPhaseStart`, or does it need to be added to the options interface? — Phase 1 Task 1.3 includes `onPhaseStart` for `phase_start` events; verify the callback is wired through `useAgentStream` to `TaskDetailPage` consumers, otherwise downgrade to `onEvent` fallback.

- [ ] **Failed task `56bfdbf1-…` UI test**: Does AC3's failure-banner check actually require backend changes (Task 4.1 enrichment of `error_message`) to be deployed first, or can the existing `stderr_tail` field be read by the frontend directly? — Confirm the API response shape before assuming Phase 4 backend work is on the critical path for AC3.

- [ ] **Logs panel suppression of thinking**: AC6 assumes the logs panel already renders `type:"thinking"` log entries. If verification reveals the logs panel ALSO suppresses thinking display (separate filter), this becomes a follow-up ticket — explicitly do NOT expand scope during this plan's execution.

## ralplan-agentflow-multi-provider-openai-anthropic - 2026-04-30

- [ ] **`kimi.py` adapter shape (HIGHEST RISK)**: Does `vendor/agentflow-src/agentflow/agents/kimi.py` actually invoke a `kimi` CLI binary that exists in the runner image, or is it a stub that depends on `claude` with kimi env? — Phase 0 Task T0.4 settles this. If broken, AC1 demotes from triple-provider to dual-provider (codex + claude) with kimi as deferred follow-up.

- [ ] **`pi.py` adapter shape**: Same as kimi — Phase 0 Task T0.4 must code-read this and confirm CLI presence in the runner image. PI is the lowest-priority provider; if missing, mark as long-term follow-up.

- [ ] **Claude CLI version in runner image**: Does the `claude` CLI in `argus-agentflow-runner` support `--output-format stream-json --verbose` and emit `content_block_delta` events with `delta.type == "text_delta"`? — Phase 0 Task T0.3 captures real shape. If divergent, Phase 4 parser branch widens to derive deltas from `assistant_message` chunks (assumption A4 fallback).

- [ ] **3rd-party Anthropic-compat endpoint SSE shape**: Does the Anthropic-compat endpoint chosen for AC1 verification emit vanilla Anthropic SSE shape (`event: content_block_delta` with `text_delta`)? — Phase 0 Task T0.2 probes. If shape diverges, fall back to Anthropic-direct endpoint per assumption A2.

- [ ] **`KimiTraceParser` / `PiTraceParser` extension scope**: After T0.4 reveals Kimi/PI streaming format, do they also need `assistant_delta` extension, or are they already symmetric with codex? — Defer to a separate ticket once observed in production unless T0.4 reveals the gap blocks AC1.

- [ ] **`kimi_compatible` naming ambiguity**: Kimi has both an OpenAI-compat endpoint (Moonshot v1) and an Anthropic-compat endpoint (Kimi for coding). Plan resolves to "kimi_compatible → spawns the dedicated `kimi` agent" but operators wanting Kimi-via-Anthropic-shape should use `LLM_PROVIDER=anthropic_compatible` + Kimi base URL. Should we add a separate `kimi_anthropic_compatible` enum value for explicit operator UX, or document the dual-mode as advanced?

- [ ] **System-config UI labels**: Once `kimi_compatible` and `pi_compatible` are accepted by the Rust validator, should the system-config UI show them as labeled options, or keep them advanced-operator-only per spec Non-Goals #5?

- [ ] **Vendor patch capture**: The `ClaudeTraceParser.feed()` extension lives inside `vendor/agentflow-src/`. Should we capture the diff as `vendor/argus-patches/claude-trace-parser-deltas.patch` for re-apply on vendor upgrades, or rely on inline edits surviving merges? — Decide before merging Phase 4.

## ralplan-claw-code-migration - 2026-05-01

- [ ] **JSONL log path location**: Is `~/argus-data/intelligent-task-logs/{task_id}.jsonl` consistent with Argus's existing log layout, or should it live under `/app/uploads/zip_files/intelligent-task-logs/` to match the rust-task-state.json container path? — Decide before Phase 5 T5.3.

- [ ] **Retention cron cadence**: Daily 02:00 UTC purge vs per-task-on-completion lazy expiry — which fits Argus's ops model better? — Phase 5 T5.5 default is daily cron; revisit if operator load profile differs.

- [ ] **Operator retry force-flag**: Should `POST /intelligent-tasks/retry` accept a `force: bool` to bypass per-project lock? — Recommend NO for v1 (decision-D enforces "skip on contention"); revisit if operators report friction.

- [ ] **Tool-rejection metric cardinality**: Is `argus_tool_rejections_total{tool, reason}` cardinality acceptable, or should `reason` be bounded to a fixed enum (≤5 values: `path_outside_project`, `disallowed_tool`, `network_attempt`, `shell_attempt`, `other`)? — Decide before Phase 5 T5.2.

- [ ] **ADR PR sequencing**: Should Phase 0 T0.5 ADR draft be a separate PR landed at Phase 0, or rolled into Phase 6 finalization? — Recommend separate Phase-0 PR so subsequent phases can cite it.

- [ ] **PM-2 `stream_message` visibility**: If Phase 0 T0.4 reveals `ProviderClient::stream_message()` is `pub(crate)`, do we (a) ship `vendor/argus-patches/0001-expose-stream-message.patch` and proceed, or (b) downgrade to per-`thinking_end` granularity (Assumption A7) and accept the UX regression? — Decision needed at end of Phase 0.

- [ ] **PM-1 fallback embedding**: If `cargo tree --duplicates` reveals unresolvable conflicts, do we (a) pin to an older claw-code commit with closer dep tree, (b) accept subprocess fallback (O1c) with reduced AC4 fidelity, or (c) defer migration? — Decision needed at end of Phase 0.

- [ ] **Auto-trigger storm threshold**: PM-3 mitigation (g) says "queue-depth > 50 pending → suspend auto-trigger". Is 50 the right threshold, or should it be operator-tunable via `system_config.intelligent_audit_max_queue_depth`? — Phase 3 T3.7 hardcodes 50; promote to config knob if ops requests.

- [ ] **mock-anthropic-service AC fidelity**: If Phase 0 T0.3 inventory reveals the mock lacks per-token streaming or 401 scenarios, do we (a) extend mock upstream via PR, (b) ship Argus-side mock harness, or (c) accept lower acceptance fidelity? — Decision at end of Phase 0.

## ralplan-opengrep-sandbox-auto-destroy - 2026-05-05 (iteration 2 — revised)

- [ ] **Q1 (NON-BLOCKER, downgraded iteration 2) — Test cubemaster harness shape** — Harness exists at `tests/cubesandbox_runtime.rs`. Gate new tests behind same `feature = "cubemaster_live_test"` pattern as `opengrep_ffmpeg_fp_hardening.rs:7`. Default applied; executor proceeds without re-asking.
- ~~**Q2 — `AppState::from_config` signature change**~~ — **DROPPED iteration 2** (resolved by R3: graceful shutdown gate moved to `axum::Extension<ShutdownGate>`; `AppState::from_config` signature is untouched).
- [ ] **Q3 — Codeql submission endpoint shutdown-gating** — spec only mandates opengrep gating, but leaving codeql ungated creates asymmetric shutdown semantics. Default: gate both POST submission endpoints in `static_tasks.rs`; reviewable. Why it matters: avoids a follow-up PR; tiny scope creep beyond spec.
- [ ] **Q4 — Manifest deletion path coverage** — spec hard-codes `/var/lib/argus/opengrep-pool-manifest.json`, but the live `.env` actually points at `/app/data/opengrep-pool-manifest.json` via `CUBESANDBOX_OPENGREP_POOL_MANIFEST`. Default: migration step deletes BOTH the canonical path AND the path from the deprecated env var (if set) on startup, then forgets the env var. Why it matters: a single-path deletion will silently leave production manifests behind. Document in commit 2 body.
- [ ] **Followup (iteration 2 ADR consequence)** — Schedule deletion of `migrate_remove_opengrep_pool_manifest` helper after vN+1 release. Tracked here so the one-shot migration is not orphaned indefinitely. Source comment `// One-time migration: remove after vN+1 release.` already in place.

## Q5 — Witness datapoint deferral

**Status**: Filed 2026-05-05

**Reason for deferral**: `curl -fsS http://127.0.0.1:8089/healthz` returned non-zero exit (cubemaster unavailable on operator workstation). Neither the health endpoint nor `cubemastercli cubebox list` could reach a live cubemaster process. The machine does not have cubemaster running at the time of Commit 1 execution.

**Earliest opportunity to capture**: First CI run with a live cubemaster instance attached (i.e., cubemaster integration test environment). Alternatively, on any developer workstation where `argus-shutdown.sh` has started cubemaster successfully.

**Owner**: Commit 1 executor; to be verified during Commit 6 integration test phase (AC1 harness with live cubemaster).

**Why it matters**: R5 obligation (cubemaster `create_sandbox` p50/p99 baseline appended to spec Assumption #1) must not be silently dropped. If executor cannot run the fixture, fill in:
- Reason for deferral (machine state / missing dependency / disabled feature)
- Earliest opportunity to capture
- Owner

**Default if unfilled**: Step 0 fully executed; Q5 stays empty.
