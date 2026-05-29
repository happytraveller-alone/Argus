# Rust ↔ agent-engine Contract (v1)

Internal HTTP/JSON contract between the argus Rust backend (`backend/`) and the
Node.js `agent-engine` sidecar. None of these endpoints are exposed via the
public `/api` surface or the Vite proxy.

> **Deployment reality (verified):** the `backend` service runs with
> `network_mode: host`, so it cannot use docker service DNS. The sidecar is
> therefore published on `127.0.0.1:18100` and the backend reaches it at
> `http://localhost:18100` (the same loopback mechanism the backend already uses
> for `db`/`redis`). Consequently these endpoints are **loopback-only on the host,
> not isolated by a private docker network** — any host-local process could reach
> them. The **shared-secret bearer token is the real access control**, not network
> isolation. This is exactly why `/internal/llm-config` (which returns a resolved
> API key) MUST require the bearer token and MUST reject unauthenticated calls
> (AC12).

- **Transport:** HTTP/1.1, JSON bodies. Streaming endpoints use
  newline-delimited JSON (NDJSON), one event object per line.
- **Auth:** every request carries `Authorization: Bearer <AGENT_ENGINE_SHARED_SECRET>`.
  The secret is provided to both processes via env (mounted, never baked into an
  image, never logged). Unauthenticated/invalid → `401`.
- **Versioning:** every request includes `"version": 1`. A receiver that does not
  support the version returns `409 {"error":"unsupported_version"}`. This lets the
  Rust backend and sidecar deploy independently during the incremental rollout.
- **Direction:** `Rust → sidecar` for `/run-stage`; `sidecar → Rust` for
  `/internal/codeintel/*` and `/internal/llm-config` callbacks.

---

## 1. `POST /run-stage`  (Rust → sidecar)

Run a single pipeline stage on the sidecar. Response is an **NDJSON event
stream**; the final line is the terminal result.

### Request
```jsonc
{
  "version": 1,
  "runId": "uuid",            // unique per stage invocation; used for cancel
  "taskId": "uuid",           // the intelligent-task id (Rust-owned)
  "sessionId": "uuid",        // cross-stage agent session (sidecar-owned, Rust-checkpointed)
  "stage": "hunt",            // recon|hunt|validate|gapfill|dedupe|trace|feedback|report
  "model": {                  // resolved per-stage model assignment
    "provider": "google",     // pi KnownProvider
    "api": "google-generative-ai", // pi Api (wire protocol)
    "modelId": "gemini-2.5-pro",
    "baseUrl": "https://...", // optional override
    "fallback": [ { "provider": "...", "api": "...", "modelId": "..." } ] // ordered backups
  },
  "inputs": { /* stage-specific; mirrors the Rust stage input structs */ },
  "limits": { "maxTokensPerCall": 0, "stageDeadlineMs": 0 }
}
```
> The sidecar fetches the API key + any extra headers separately via
> `GET /internal/llm-config` (keys are NEVER sent in this request body).

### Response — NDJSON event stream
Each line is one event. The sidecar does **not** assign `seq`; **Rust stamps
`seq` and `timestamp` on relay** (single ordering authority). Frames:

```jsonc
// progress / reasoning events (relayed to event_log + SSE broadcast)
{ "type": "stage_event", "kind": "stage_started", "message": "...", "data": {} }
{ "type": "stage_event", "kind": "tool_call",     "data": { "tool": "get_callers", "args": {} } }
{ "type": "stage_event", "kind": "tool_result",   "data": { "tool": "get_callers", "ok": true } }
{ "type": "stage_event", "kind": "fallback",      "data": { "from": "gemini-2.5-pro", "to": "claude-…", "reason": "429" } }

// token deltas — BROADCAST-ONLY, NOT persisted to event_log (volume control)
{ "type": "token", "delta": "..." }

// session checkpoint hint — Rust persists {session, event_log slice} at stage boundary
{ "type": "checkpoint", "session": { /* serialized pi AgentHarness session */ } }

// terminal (last line) — exactly one of:
{ "type": "result", "ok": true,  "output": { /* stage output; AuditFinding[] etc., camelCase */ } }
{ "type": "result", "ok": false, "error": { "code": "stage_failed", "message": "...", "retryable": false } }
```

### Field shapes that MUST match Rust (camelCase preserved)
- `EvidenceCodeSnippet`: `{ lineStart, lineEnd, file, code, language }`
- `AuditFinding` / `IntelligentTaskFinding`: existing fields (`id`, `severity`,
  `summary`, `evidenceProse`, `evidenceCodeSnippets`, `file`, `lineStart`,
  `lineEnd`, …) — the sidecar output maps 1:1 onto these.

### Cancellation
- `POST /run-stage/{runId}/cancel` (Rust → sidecar), **or** Rust closing the
  response stream (client disconnect). Either triggers a sidecar-side
  `AbortController` wired into the pi agent loop and the provider `fetch`, so
  LLM billing stops promptly. The sidecar emits a final
  `{ "type": "result", "ok": false, "error": { "code": "cancelled" } }` if it
  can before teardown.

### Retry ownership
- **The sidecar owns LLM transport retry + provider fallback** (pi `packages/ai`
  has no built-in retry, so the sidecar adds it). Rust's `llm.rs` retry loop is
  **bypassed** for stages running on the sidecar. Rust may retry the *whole*
  `/run-stage` call only on connection-level failure, never on a `result.ok:false`.

---

## 2. `POST /internal/codeintel/{op}` and `/internal/codeintel/batch`  (sidecar → Rust)

Codegraph tools invoked by the sidecar agent loop. The Rust `CodeIntelligence`
implementation (and its existing sha256-keyed `QueryCache`) remains authoritative
behind these endpoints.

`{op}` ∈ `find_taint_through | get_callers | get_callees | get_context | search_symbol`

### Request
```jsonc
{ "version": 1, "taskId": "uuid", "archiveSha": "…", "args": { /* op-specific */ } }
```
`batch` request: `{ "version": 1, "taskId": "…", "archiveSha": "…", "calls": [ { "op": "...", "args": {} } ] }`
(amortizes the round-trips of an agent-loop query burst).

### Response
```jsonc
{ "ok": true,  "result": { /* op-specific, identical to in-process CodeIntelligence */ } }
{ "ok": false, "error": { "code": "...", "message": "...", "partial": false } }
```

### Error / timeout / partial-result taxonomy
These calls can now fail over the network, so the agent loop MUST handle:
| code | meaning | agent-loop handling |
|------|---------|---------------------|
| `not_found` | symbol/file not in index | treat as empty result, continue |
| `timeout` | Rust did not answer within the per-call deadline | retry once, then degrade (proceed without that evidence) |
| `partial` (`partial:true`) | result truncated (budget/size) | use what is returned; do not assume completeness |
| `unavailable` | codegraph/index not ready for this task | fall back to single-pass (no tool loop) for the stage |
| `internal` | Rust-side error | surface as a `tool_result` failure event; continue if non-fatal |

Per-call timeout default: 10s. The sidecar must not hang the stage on a slow RPC.

---

## 3. `GET /internal/llm-config`  (sidecar → Rust)

Returns the resolved provider config (including the API key) for a given
provider/model. **Bearer-auth required; bound to the internal network only.**

### Request
`GET /internal/llm-config?provider=google&modelId=gemini-2.5-pro` (+ bearer)

Dual-mode resolution:
- **Native provider** (`google|anthropic|openai|deepseek|qwen|zhipu|moonshot|baidu|minimax|doubao|ollama`):
  the key comes from the matching per-provider `AppConfig` env field. `baseUrl`
  is `null` (the sidecar uses pi defaults) except `ollama`, which returns
  `ollama_base_url` and a `null` key. Unset/empty key →
  `404 { "error": "provider_key_not_configured" }`.
- **Compatible** (`provider` absent, or `openai_compatible|anthropic_compatible|compatible`):
  resolves the single enabled compatible LLM row from `system_config`
  (`llm_config_json`). No usable row → `404`; invalid `baseUrl` → `422`.

### Response
```jsonc
{ "provider": "google",          // native id, or openai_compatible/anthropic_compatible
  "modelId": "gemini-2.5-pro",   // null when not supplied/resolved
  "baseUrl": "…",                // null for native (pi default), set for ollama + compatible
  "apiKey": "…",                 // server-side only; never relayed to /run-stage callers
  "headers": { /* optional extra headers */ } }
```
Rust returns `provider/modelId/baseUrl/apiKey/headers` only — it does **not**
emit a pi `api` wire-protocol field; the **sidecar** maps `provider → pi Api`.
The key is read from the Rust `system_config` / per-provider env and never
logged. AC12 asserts an unauthenticated call (or any call when no shared secret
is configured) returns `401`.

---

## 4. Health

`GET /healthz` (no auth) → `200 { "status": "ok", "service": "argus-agent-engine", "uptimeMs": N }`.

---

## 5. `GET /models`  (public catalog, Phase 1B.1a)

Static pi model catalog. **No auth, no API keys** — proxied verbatim by the Rust
backend's public `GET /api/v1/models`. Built once from pi's generated registry
(`getProviders()` → `getModels()`), cached for the process lifetime.

### Response
```jsonc
{ "version": 1,
  "models": [
    { "id": "gemini-2.5-pro",
      "provider": "google",                 // pi provider id this entry belongs to
      "api": "google-generative-ai",        // pi wire-protocol api (informational)
      "name": "Gemini 2.5 Pro",
      "contextWindow": 1048576,             // total window (tokens)
      "maxOutput": 65536,                   // model.maxTokens (single-call output cap)
      "reasoning": true,                    // thinking/reasoning supported
      "thinkingLevels": ["minimal","low","medium","high"], // [] when reasoning=false
      "input": ["text","image"],            // accepted modalities
      "cost": { "input": 1.25, "output": 10, "cacheRead": 0.31, "cacheWrite": 0 } // USD / 1M tokens
    }
    // …
  ] }
```
The same model id may appear under multiple providers (e.g. a Gemini id under both
`google` and `github-copilot`); a selection is the `(provider, id)` pair, not the
id alone.

---

## 6. Invocation-layer events (sidecar-internal, Phase 1B.1b)

The sidecar's LLM invocation service (`invoke.ts`, `invokeStage`) owns **retry +
fallback + token streaming** (CONTRACT.md "Retry ownership"). It yields the
frames below; these are the source frames the `/run-stage` NDJSON stream (§1)
re-emits, so the **type/kind vocabulary is identical** and the frontend consumes
the same shapes. The sidecar does **not** stamp `seq`/`timestamp` — Rust does on
relay.

```jsonc
// token delta — BROADCAST-ONLY (matches §1 `token`); not persisted to event_log
{ "type": "token", "delta": "..." }

// provider/model fell over after exhausting retries; advancing down the chain
{ "type": "stage_event", "kind": "fallback", "data": { "from": "google/gemini-2.5-pro", "to": "anthropic/claude-…", "reason": "rate_limited" } }

// a transient failure is being retried on the SAME model (exponential backoff + full jitter)
{ "type": "stage_event", "kind": "retry", "data": { "model": "google/gemini-2.5-pro", "attempt": 1, "reason": "server_error" } }

// terminal (exactly one) — mirrors §1 `result`
{ "type": "result", "ok": true,  "output": { "message": { /* pi AssistantMessage */ }, "usage": { /* pi Usage */ }, "model": "google/gemini-2.5-pro" } }
{ "type": "result", "ok": false, "error": { "code": "rate_limited|server_error|client_error|provider_error|cancelled|config_*|…", "message": "...", "retryable": false } }
```

### Retry / fallback classification (sidecar-owned)
- **Retryable** (backoff, then same model up to `maxAttempts`, default 3): HTTP
  `429`/`408`/`409`/`5xx`; or — when no HTTP status is observable — error
  messages matching rate-limit / overloaded / timeout / connection-reset /
  `ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|ENOTFOUND`. Backend `/internal/llm-config`
  network/timeout failures are also retryable.
- **Permanent** (skip straight to the next fallback): HTTP `4xx` other than the
  above (e.g. `400/401/403/404`); `/internal/llm-config` `404 provider_key_not_configured`,
  `401`, `409`, `422`; or a missing shared secret.
- **`cancelled`**: the caller's `AbortSignal` fired (pi emits `stopReason:"aborted"`).
  Never retried; surfaced as `result.ok:false` `code:"cancelled"`.

The resolved API key is attached to the pi `StreamOptions` for the single call
only — it is never stored on the constructed `Model`, serialized into a session,
or logged.

---

## Ownership summary (Principle 2 — no duplicated authority)
| Concern | Owner |
|---------|-------|
| Task lifecycle, Postgres persistence, SSE, event `seq` + ordering, key custody, codegraph index + `QueryCache` | **Rust** |
| Per-stage reasoning (agent loop), cross-stage session, model routing, LLM retry + fallback, compaction | **agent-engine (sidecar)** |
| Per-stage `rust|sidecar` flag (runtime-mutable, instant rollback) | **Rust `system_config`** |
