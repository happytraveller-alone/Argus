// ---------------------------------------------------------------------------
// Client for the Rust backend's GET /internal/llm-config (CONTRACT.md §3).
//
// The Rust backend is the sole custodian of LLM API keys. The sidecar fetches a
// resolved provider config (including the key) on demand, bearer-authenticated
// with AGENT_ENGINE_SHARED_SECRET. The returned apiKey is used only to drive a
// single provider call and is NEVER logged or persisted.
// ---------------------------------------------------------------------------

/** Shape returned by GET /internal/llm-config. `api` is intentionally absent —
 *  the sidecar maps provider→Api itself (see pi.ts). */
export interface ResolvedLlmConfig {
  provider: string;
  /** null when the caller did not supply / the backend could not resolve one. */
  modelId: string | null;
  /** null for native providers (pi default url); set for ollama + compatible. */
  baseUrl: string | null;
  /** server-side secret; must never be logged or written to a session. */
  apiKey: string | null;
  /** optional extra request headers. */
  headers?: Record<string, string>;
}

export class LlmConfigError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "LlmConfigError";
  }
}

export interface LlmConfigClientOptions {
  /** Base URL of the Rust backend. Defaults to the loopback the backend
   *  publishes on (host networking). */
  backendBaseUrl?: string;
  /** Shared bearer secret. Defaults to env AGENT_ENGINE_SHARED_SECRET. */
  sharedSecret?: string;
  /** Per-request timeout. Defaults to 10s. */
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

const DEFAULT_BACKEND_BASE_URL = "http://localhost:18000";
const DEFAULT_TIMEOUT_MS = 10_000;
const CONTRACT_VERSION = 1;

/**
 * Resolve a provider/model config from the Rust backend.
 *
 * @throws {LlmConfigError} on non-2xx (404 provider_key_not_configured, 401
 *   unauthorized, 409 unsupported_version, 422 invalid baseUrl, …) or transport
 *   failure. Callers (invoke.ts) decide whether the failure is retryable.
 */
export async function fetchLlmConfig(
  params: { provider?: string; modelId?: string },
  options: LlmConfigClientOptions = {},
): Promise<ResolvedLlmConfig> {
  const secret = options.sharedSecret ?? process.env.AGENT_ENGINE_SHARED_SECRET;
  if (!secret) {
    throw new LlmConfigError("AGENT_ENGINE_SHARED_SECRET is not configured", 0, "no_shared_secret");
  }

  const base = options.backendBaseUrl ?? process.env.ARGUS_BACKEND_URL ?? DEFAULT_BACKEND_BASE_URL;
  const url = new URL("/internal/llm-config", base);
  if (params.provider) url.searchParams.set("provider", params.provider);
  if (params.modelId) url.searchParams.set("modelId", params.modelId);
  // Versioned for independent rollout (CONTRACT.md "Versioning").
  url.searchParams.set("version", String(CONTRACT_VERSION));

  const fetchImpl = options.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetchImpl(url, {
      method: "GET",
      headers: { authorization: `Bearer ${secret}`, accept: "application/json" },
      signal: controller.signal,
    });
  } catch (err) {
    const reason = controller.signal.aborted ? "timeout" : "network_error";
    // Never include the secret/url query (carries provider only, but be safe).
    throw new LlmConfigError(`llm-config request failed: ${reason}`, 0, reason);
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const code = await readErrorCode(res);
    throw new LlmConfigError(`llm-config returned ${res.status}`, res.status, code);
  }

  const body = (await res.json()) as Partial<ResolvedLlmConfig>;
  if (typeof body.provider !== "string") {
    throw new LlmConfigError("llm-config response missing provider", res.status, "malformed_response");
  }
  return {
    provider: body.provider,
    modelId: body.modelId ?? null,
    baseUrl: body.baseUrl ?? null,
    apiKey: body.apiKey ?? null,
    headers: body.headers,
  };
}

async function readErrorCode(res: Response): Promise<string | undefined> {
  try {
    const body = (await res.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : undefined;
  } catch {
    return undefined;
  }
}
