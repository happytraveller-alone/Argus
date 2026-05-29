// ---------------------------------------------------------------------------
// LLM invocation service (Phase 1B.1b): sidecar-owned retry + fallback chain +
// token streaming.
//
// pi `packages/ai` has NO built-in retry, so per CONTRACT.md "Retry ownership"
// the sidecar adds it here. A single invocation:
//   1. resolves each candidate model's provider config via /internal/llm-config
//      (key fetched per-call, never stored on the Model or in a session),
//   2. calls pi `stream()`, re-emitting token deltas as they arrive,
//   3. retries the SAME model with exponential backoff on transient failures
//      (network / timeout / 5xx / 429 / provider-overload),
//   4. on exhausted retries, advances to the next model in the fallback chain,
//      emitting a `fallback` stage event (from→to, reason),
//   5. wires the caller's AbortSignal into pi so cancel stops provider billing.
//
// The emitted event frames match CONTRACT.md §1 (stage_event / token / result);
// they are documented in CONTRACT.md under "agent-engine internal invocation
// events". This module does NOT own task lifecycle, persistence, or seq — Rust
// stamps seq on relay.
// ---------------------------------------------------------------------------

import { stream } from "@earendil-works/pi-ai";
import type {
  Api,
  AssistantMessage,
  Context,
  Model,
  ProviderResponse,
  ProviderStreamOptions,
  Usage,
} from "@earendil-works/pi-ai";

import { buildModel } from "./pi.js";
import { deriveBudget } from "./budget.js";
import { fetchLlmConfig, LlmConfigError } from "./llm-config.js";
import type { LlmConfigClientOptions } from "./llm-config.js";

/** A single candidate (provider, modelId) the invocation may use. */
export interface ModelCandidate {
  provider: string;
  modelId?: string;
}

export interface InvokeRequest {
  /** Primary model assignment for the stage. */
  model: ModelCandidate;
  /** Ordered backups tried, in order, after the primary exhausts its retries. */
  fallback?: ModelCandidate[];
  /** Conversation context (system prompt + messages + tools). */
  context: Context;
  /** Caps the output tokens requested per call (`limits.maxTokensPerCall`); 0/absent = model default. */
  maxOutputTokens?: number;
  /** Cancels the whole invocation (Rust cancel → AbortController → provider fetch). */
  signal?: AbortSignal;
}

/** Events emitted by {@link invokeStage}. Mirrors CONTRACT.md §1 frames the
 *  sidecar produces (Rust stamps seq/timestamp on relay; not done here). */
export type InvokeEvent =
  | { type: "stage_event"; kind: "fallback"; data: { from: string; to: string; reason: string } }
  | { type: "stage_event"; kind: "retry"; data: { model: string; attempt: number; reason: string } }
  | { type: "token"; delta: string }
  | { type: "result"; ok: true; output: { message: AssistantMessage; usage: Usage; model: string } }
  | { type: "result"; ok: false; error: { code: string; message: string; retryable: boolean } };

export interface RetryPolicy {
  /** Attempts per model before falling back. Default 3. */
  maxAttempts?: number;
  /** Base backoff in ms (attempt n waits ~base * 2^(n-1) + jitter). Default 500. */
  baseDelayMs?: number;
  /** Backoff ceiling in ms. Default 15_000. */
  maxDelayMs?: number;
}

export interface InvokeOptions {
  retry?: RetryPolicy;
  /** Options forwarded to the /internal/llm-config client (base url, secret, fetch). */
  llmConfig?: LlmConfigClientOptions;
  /** Per-call provider timeout in ms (forwarded to pi `timeoutMs`). Default 120_000. */
  callTimeoutMs?: number;
  /** Injectable sleep, for tests. Default real timer. */
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  /** Injectable streamer, for tests. Default pi `stream`. */
  streamImpl?: typeof stream;
}

const DEFAULT_MAX_ATTEMPTS = 3;
const DEFAULT_BASE_DELAY_MS = 500;
const DEFAULT_MAX_DELAY_MS = 15_000;
const DEFAULT_CALL_TIMEOUT_MS = 120_000;

/**
 * Run one stage invocation across the primary model + fallback chain, yielding
 * an async stream of {@link InvokeEvent}. Terminates with exactly one `result`
 * event. Never throws for provider/transport failures — they surface as a
 * non-ok `result`.
 */
export async function* invokeStage(
  req: InvokeRequest,
  options: InvokeOptions = {},
): AsyncGenerator<InvokeEvent, void, void> {
  const candidates = [req.model, ...(req.fallback ?? [])];
  const policy = normalizePolicy(options.retry);
  const sleep = options.sleep ?? defaultSleep;
  const streamImpl = options.streamImpl ?? stream;

  let lastError: ClassifiedError = {
    code: "no_candidates",
    message: "no model candidates supplied",
    retryable: false,
  };

  for (let i = 0; i < candidates.length; i++) {
    const candidate = candidates[i]!;
    const candidateLabel = labelOf(candidate);

    if (i > 0) {
      // Advancing to a backup — surface the reason the previous one failed.
      yield {
        type: "stage_event",
        kind: "fallback",
        data: { from: labelOf(candidates[i - 1]!), to: candidateLabel, reason: lastError.code },
      };
    }

    // Resolve provider config (key) for this candidate. A config failure is
    // itself classifiable: a missing key is permanent (skip to next), a
    // network/timeout to the backend is transient (retry this candidate).
    for (let attempt = 1; attempt <= policy.maxAttempts; attempt++) {
      if (req.signal?.aborted) {
        yield abortedResult();
        return;
      }

      let resolved: Awaited<ReturnType<typeof fetchLlmConfig>>;
      let model: Model<Api>;
      try {
        resolved = await fetchLlmConfig(
          { provider: candidate.provider, modelId: candidate.modelId },
          options.llmConfig,
        );
        model = buildModel(resolved);
      } catch (err) {
        lastError = classifyConfigError(err);
        if (!lastError.retryable || attempt >= policy.maxAttempts) break;
        yield retryEvent(candidateLabel, attempt, lastError.code);
        await backoff(attempt, policy, sleep, req.signal);
        continue;
      }

      const budget = deriveBudget(model, { maxOutputTokens: req.maxOutputTokens });

      let capturedStatus = 0;
      const streamOptions: ProviderStreamOptions = {
        // The key lives only in this option object for the duration of the
        // call; it is never stored on `model`, serialized, or logged.
        apiKey: resolved.apiKey ?? undefined,
        headers: model.headers,
        signal: req.signal,
        maxTokens: budget.maxOutput,
        timeoutMs: options.callTimeoutMs ?? DEFAULT_CALL_TIMEOUT_MS,
        onResponse: (response: ProviderResponse) => {
          capturedStatus = response.status;
        },
      };

      // Consume one streamed attempt, re-emitting token deltas. A terminal
      // pi `error` event (not an abort) is classified for retry/fallback.
      const outcome = yield* runOneAttempt(streamImpl, model, req.context, streamOptions, () => capturedStatus);

      if (outcome.kind === "ok") {
        yield {
          type: "result",
          ok: true,
          output: { message: outcome.message, usage: outcome.message.usage, model: candidateLabel },
        };
        return;
      }
      if (outcome.kind === "aborted") {
        yield abortedResult();
        return;
      }

      lastError = outcome.error;
      if (!lastError.retryable || attempt >= policy.maxAttempts) break;
      yield retryEvent(candidateLabel, attempt, lastError.code);
      await backoff(attempt, policy, sleep, req.signal);
    }
  }

  // Every candidate exhausted.
  yield {
    type: "result",
    ok: false,
    error: { code: lastError.code, message: lastError.message, retryable: false },
  };
}

type AttemptOutcome =
  | { kind: "ok"; message: AssistantMessage }
  | { kind: "aborted" }
  | { kind: "error"; error: ClassifiedError };

/**
 * Drive a single pi stream to completion, yielding `token` events for text
 * deltas. Returns the classified outcome (ok / aborted / retryable error).
 */
async function* runOneAttempt(
  streamImpl: typeof stream,
  model: Model<Api>,
  context: Context,
  streamOptions: ProviderStreamOptions,
  getStatus: () => number,
): AsyncGenerator<InvokeEvent, AttemptOutcome, void> {
  let s: ReturnType<typeof stream>;
  try {
    s = streamImpl(model, context, streamOptions);
  } catch (err) {
    // stream() only throws for setup errors (e.g. unregistered api) — permanent.
    return { kind: "error", error: { code: "invoke_setup_failed", message: errMessage(err), retryable: false } };
  }

  try {
    for await (const event of s) {
      if (event.type === "text_delta") {
        yield { type: "token", delta: event.delta };
      } else if (event.type === "error") {
        if (event.reason === "aborted") return { kind: "aborted" };
        return { kind: "error", error: classifyProviderError(event.error.errorMessage, getStatus()) };
      } else if (event.type === "done") {
        return { kind: "ok", message: event.message };
      }
    }
  } catch (err) {
    // An iteration-time throw (e.g. fetch rejected) — treat as transient network.
    if (isAbortError(err)) return { kind: "aborted" };
    return { kind: "error", error: { code: "network_error", message: errMessage(err), retryable: true } };
  }

  // Stream ended without an explicit done/error — fall back to the resolved result.
  const message = await s.result();
  if (message.stopReason === "aborted") return { kind: "aborted" };
  if (message.stopReason === "error") {
    return { kind: "error", error: classifyProviderError(message.errorMessage, getStatus()) };
  }
  return { kind: "ok", message };
}

interface ClassifiedError {
  code: string;
  message: string;
  retryable: boolean;
}

const RETRYABLE_MESSAGE_PATTERNS: RegExp[] = [
  /rate.?limit/i,
  /too many requests/i,
  /overloaded/i,
  /\b429\b/,
  /\b5\d\d\b/,
  /timed?\s?out/i,
  /timeout/i,
  /temporarily unavailable/i,
  /service unavailable/i,
  /connection (reset|refused|closed)/i,
  /ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|ENOTFOUND/,
];

/** Classify a pi provider error (terminal `error` event) for retry/fallback. */
function classifyProviderError(message: string | undefined, status: number): ClassifiedError {
  const msg = message ?? "provider error";
  if (status === 429 || status === 408 || status === 409 || (status >= 500 && status <= 599)) {
    return { code: status === 429 ? "rate_limited" : "server_error", message: msg, retryable: true };
  }
  if (status >= 400 && status < 500) {
    // 4xx other than the above (e.g. 400/401/403/404) is a permanent request error.
    return { code: "client_error", message: msg, retryable: false };
  }
  // No usable status (status === 0): fall back to message heuristics.
  if (RETRYABLE_MESSAGE_PATTERNS.some((re) => re.test(msg))) {
    return { code: "transient_error", message: msg, retryable: true };
  }
  return { code: "provider_error", message: msg, retryable: false };
}

/** Classify a /internal/llm-config failure. */
function classifyConfigError(err: unknown): ClassifiedError {
  if (err instanceof LlmConfigError) {
    // 0 = transport (network/timeout/no-secret). Network is retryable;
    // a missing shared secret is a permanent misconfiguration.
    if (err.status === 0) {
      const retryable = err.code === "timeout" || err.code === "network_error";
      return { code: err.code ?? "config_unavailable", message: err.message, retryable };
    }
    // 404 (key not configured) / 422 (bad url) / 401 / 409 are permanent for
    // this candidate — advance to the next fallback.
    return { code: err.code ?? `config_http_${err.status}`, message: err.message, retryable: false };
  }
  return { code: "config_error", message: errMessage(err), retryable: false };
}

function retryEvent(model: string, attempt: number, reason: string): InvokeEvent {
  return { type: "stage_event", kind: "retry", data: { model, attempt, reason } };
}

function abortedResult(): InvokeEvent {
  return { type: "result", ok: false, error: { code: "cancelled", message: "invocation cancelled", retryable: false } };
}

function normalizePolicy(p: RetryPolicy | undefined): Required<RetryPolicy> {
  return {
    maxAttempts: Math.max(1, p?.maxAttempts ?? DEFAULT_MAX_ATTEMPTS),
    baseDelayMs: Math.max(0, p?.baseDelayMs ?? DEFAULT_BASE_DELAY_MS),
    maxDelayMs: Math.max(0, p?.maxDelayMs ?? DEFAULT_MAX_DELAY_MS),
  };
}

async function backoff(
  attempt: number,
  policy: Required<RetryPolicy>,
  sleep: (ms: number, signal?: AbortSignal) => Promise<void>,
  signal?: AbortSignal,
): Promise<void> {
  const exp = policy.baseDelayMs * 2 ** (attempt - 1);
  const capped = Math.min(exp, policy.maxDelayMs);
  // Full jitter to avoid synchronized retry storms across stages.
  const delay = Math.floor(Math.random() * capped);
  await sleep(delay, signal);
}

function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function labelOf(c: ModelCandidate): string {
  return c.modelId ? `${c.provider}/${c.modelId}` : c.provider;
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

function errMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
