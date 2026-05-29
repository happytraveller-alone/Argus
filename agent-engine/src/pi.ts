// ---------------------------------------------------------------------------
// pi-ai integration: provider→Api mapping and Model construction.
//
// The Rust /internal/llm-config contract deliberately omits pi's `api` wire
// field (CONTRACT.md §3): the SIDECAR owns the provider→Api mapping. This
// module is the single place that mapping lives, plus the logic that turns a
// resolved provider config into a concrete pi `Model<Api>` ready for stream().
// ---------------------------------------------------------------------------

import { getModel, getModels } from "@earendil-works/pi-ai";
import type { Api, Model } from "@earendil-works/pi-ai";

import type { ResolvedLlmConfig } from "./llm-config.js";

/**
 * Provider id as it appears in the Rust contract (verbatim from `system_config`
 * / per-stage assignment). These are the strings CONTRACT.md §3 enumerates —
 * they are NOT identical to pi's `KnownProvider` set (e.g. the contract uses
 * `moonshot`/`zhipu`/`qwen`, pi uses `moonshotai`/`zai`/none). The mapping below
 * targets pi's `Api` (wire protocol), which is what actually drives the request
 * shape, so the provider label only needs to select the right transport.
 */
export type ContractProvider =
  | "google"
  | "anthropic"
  | "openai"
  | "deepseek"
  | "qwen"
  | "zhipu"
  | "moonshot"
  | "baidu"
  | "minimax"
  | "doubao"
  | "ollama"
  | "openai_compatible"
  | "anthropic_compatible"
  | "compatible";

/**
 * Map a contract provider id to the pi `Api` wire protocol.
 *
 * - `google` speaks the Generative Language API.
 * - `anthropic` (+ its compatible variant) speaks the Messages API.
 * - everything else — the native OpenAI-style vendors (deepseek, qwen, zhipu,
 *   moonshot, baidu, minimax, doubao), local `ollama`, and the generic
 *   `openai_compatible`/`compatible` rows — speaks OpenAI Completions, the
 *   universal compatible transport. pi auto-detects per-vendor `compat` quirks
 *   from the `baseUrl`, so we do not hand-tune them here.
 */
export function providerToApi(provider: string): Api {
  switch (provider) {
    case "google":
      return "google-generative-ai";
    case "anthropic":
    case "anthropic_compatible":
      return "anthropic-messages";
    default:
      return "openai-completions";
  }
}

/** A native provider id is one pi ships a generated catalog for. */
function isNativePiProvider(provider: string): provider is Parameters<typeof getModels>[0] {
  return NATIVE_PI_PROVIDERS.has(provider);
}

// pi `KnownProvider` ids that have a generated MODELS catalog. Used only to
// decide whether we can look up canonical model metadata; resolution still
// works for unknown providers via a constructed Model literal.
const NATIVE_PI_PROVIDERS = new Set<string>([
  "amazon-bedrock",
  "anthropic",
  "google",
  "google-vertex",
  "openai",
  "azure-openai-responses",
  "openai-codex",
  "deepseek",
  "github-copilot",
  "xai",
  "groq",
  "cerebras",
  "openrouter",
  "vercel-ai-gateway",
  "zai",
  "mistral",
  "minimax",
  "minimax-cn",
  "moonshotai",
  "moonshotai-cn",
  "huggingface",
  "fireworks",
  "together",
  "opencode",
  "opencode-go",
  "kimi-coding",
  "cloudflare-workers-ai",
  "cloudflare-ai-gateway",
  "xiaomi",
  "xiaomi-token-plan-cn",
  "xiaomi-token-plan-ams",
  "xiaomi-token-plan-sgp",
]);

/**
 * Look up a model in pi's generated catalog by provider + id, returning
 * `undefined` (rather than throwing) when the provider is native but the id is
 * not catalogued. This lets callers fall back to a constructed Model literal.
 */
export function findCatalogModel(provider: string, modelId: string): Model<Api> | undefined {
  if (!isNativePiProvider(provider)) return undefined;
  try {
    // getModel throws on an unknown id; getModels never does, so search it.
    return getModels(provider).find((m) => m.id === modelId) as Model<Api> | undefined;
  } catch {
    return undefined;
  }
}

// A roomy default context window for compatible/unknown models whose true
// window we cannot know. Large enough not to truncate aggressively, small
// enough to stay a meaningful budget. Overridable per the resolved config.
const FALLBACK_CONTEXT_WINDOW = 128_000;
const FALLBACK_MAX_TOKENS = 8_192;

/**
 * Build a concrete pi `Model<Api>` from a resolved /internal/llm-config response
 * plus the requested provider/model.
 *
 * Resolution order:
 *  1. If pi catalogues this (native provider, known id), start from that entry
 *     so cost/contextWindow/maxTokens/reasoning are accurate, then overlay any
 *     baseUrl/headers the Rust side returned (e.g. an ollama base url).
 *  2. Otherwise construct a Model literal: this is the compatible / custom-proxy
 *     path. `baseUrl` MUST come from the resolved config; we fall back to
 *     conservative cost/window defaults since the upstream is unknown.
 *
 * The API key is NEVER stored on the Model — it is passed through StreamOptions
 * at call time (see invoke.ts) so it never lands in a serialized session.
 */
export function buildModel(resolved: ResolvedLlmConfig): Model<Api> {
  const provider = resolved.provider;
  const modelId = resolved.modelId ?? "";
  const api = providerToApi(provider);

  const catalog = modelId ? findCatalogModel(provider, modelId) : undefined;
  if (catalog) {
    return {
      ...catalog,
      // Honor an explicit baseUrl override (ollama, regional endpoints); keep
      // the catalog default when the resolved config leaves it null.
      baseUrl: resolved.baseUrl ?? catalog.baseUrl,
      headers: mergeHeaders(catalog.headers, resolved.headers),
    };
  }

  if (!resolved.baseUrl) {
    throw new Error(
      `cannot build model for provider="${provider}" modelId="${modelId}": ` +
        `no pi catalog entry and no baseUrl in resolved config`,
    );
  }

  return {
    id: modelId || provider,
    name: modelId || provider,
    api,
    provider,
    baseUrl: resolved.baseUrl,
    reasoning: false,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: FALLBACK_CONTEXT_WINDOW,
    maxTokens: FALLBACK_MAX_TOKENS,
    headers: resolved.headers,
  };
}

function mergeHeaders(
  base: Record<string, string> | undefined,
  extra: Record<string, string> | undefined,
): Record<string, string> | undefined {
  if (!base && !extra) return undefined;
  return { ...base, ...extra };
}
