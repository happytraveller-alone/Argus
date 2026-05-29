// ---------------------------------------------------------------------------
// Public model catalog (Phase 1B.1a) served at GET /models.
//
// Flattens pi's generated per-provider catalog into a flat JSON array the
// frontend renders (cost / context window / thinking support). This payload is
// proxied verbatim by the Rust backend's public GET /api/v1/models and carries
// NO API keys — it is pure static model metadata.
// ---------------------------------------------------------------------------

import { getModels, getProviders, getSupportedThinkingLevels } from "@earendil-works/pi-ai";
import type { Api, Model } from "@earendil-works/pi-ai";

/** One catalog entry. Costs are USD per 1M tokens (pi's unit). */
export interface CatalogModel {
  id: string;
  provider: string;
  /** pi wire-protocol api (e.g. "anthropic-messages"); informational for the UI. */
  api: Api;
  name: string;
  contextWindow: number;
  /** Max output tokens for a single call, when the model advertises one. */
  maxOutput: number;
  /** True when the model supports a thinking/reasoning mode. */
  reasoning: boolean;
  /** Supported thinking levels (empty when reasoning is unsupported). */
  thinkingLevels: string[];
  /** Accepted input modalities, e.g. ["text","image"]. */
  input: ("text" | "image")[];
  cost: {
    /** USD per 1M input tokens. */
    input: number;
    /** USD per 1M output tokens. */
    output: number;
    cacheRead: number;
    cacheWrite: number;
  };
}

function toCatalogModel(model: Model<Api>): CatalogModel {
  const thinkingLevels = model.reasoning
    ? getSupportedThinkingLevels(model).filter((level) => level !== "off")
    : [];
  return {
    id: model.id,
    provider: model.provider,
    api: model.api,
    name: model.name,
    contextWindow: model.contextWindow,
    maxOutput: model.maxTokens,
    reasoning: model.reasoning,
    thinkingLevels,
    input: model.input,
    cost: {
      input: model.cost.input,
      output: model.cost.output,
      cacheRead: model.cost.cacheRead,
      cacheWrite: model.cost.cacheWrite,
    },
  };
}

/**
 * Build the full flattened catalog across every pi provider.
 *
 * Iterates `getProviders()` → `getModels(provider)`. A provider whose catalog
 * cannot be read is skipped rather than failing the whole listing.
 */
export function buildCatalog(): CatalogModel[] {
  const out: CatalogModel[] = [];
  for (const provider of getProviders()) {
    let models: Model<Api>[];
    try {
      models = getModels(provider) as Model<Api>[];
    } catch {
      continue;
    }
    for (const model of models) out.push(toCatalogModel(model));
  }
  return out;
}
