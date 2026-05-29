// ---------------------------------------------------------------------------
// Token budgets derived from the selected model (Phase 1B.4).
//
// Replaces the Rust-side coarse `recommend_tokens` heuristic (8k/16k by model
// name) with budgets computed from the pi `Model`'s real `contextWindow` and
// `maxTokens`. Consumed later by compaction (Phase 1C) to decide when to
// summarize history and how large an output to request.
// ---------------------------------------------------------------------------

import type { Api, Model } from "@earendil-works/pi-ai";

export interface TokenBudget {
  /** Total context window the model accepts (input + output), in tokens. */
  contextWindow: number;
  /** Max output tokens to request for a single call (model's hard cap, optionally lowered by a caller limit). */
  maxOutput: number;
  /** Tokens available for input/history after reserving room for the output. */
  inputBudget: number;
  /** Threshold at which history should be compacted (a fraction of inputBudget). */
  compactionThreshold: number;
}

export interface BudgetOptions {
  /**
   * Optional per-call output cap from the stage request (`limits.maxTokensPerCall`).
   * The effective output is `min(model.maxTokens, maxOutputTokens)` when > 0.
   */
  maxOutputTokens?: number;
  /**
   * Fraction of the context window to reserve for output when the model does
   * not advertise a usable `maxTokens`. Default 0.25.
   */
  outputReserveRatio?: number;
  /**
   * Fraction of the input budget at which compaction should trigger. Default
   * 0.8 — leave 20% headroom so the next turn does not overflow mid-call.
   */
  compactionRatio?: number;
}

const DEFAULT_OUTPUT_RESERVE_RATIO = 0.25;
const DEFAULT_COMPACTION_RATIO = 0.8;

/**
 * Derive a {@link TokenBudget} for a model.
 *
 * - `maxOutput` is the model's own `maxTokens`, clamped down by the caller's
 *   `maxOutputTokens` limit when supplied. If the model reports no usable
 *   `maxTokens`, reserve `outputReserveRatio` of the window instead.
 * - `inputBudget` is the window minus the reserved output, floored at 0.
 * - `compactionThreshold` is `compactionRatio * inputBudget`.
 */
export function deriveBudget<TApi extends Api>(
  model: Model<TApi>,
  options: BudgetOptions = {},
): TokenBudget {
  const contextWindow = positiveOr(model.contextWindow, 0);
  const reserveRatio = clampRatio(options.outputReserveRatio, DEFAULT_OUTPUT_RESERVE_RATIO);
  const compactionRatio = clampRatio(options.compactionRatio, DEFAULT_COMPACTION_RATIO);

  const modelMax = positiveOr(model.maxTokens, 0);
  const reservedByRatio = Math.floor(contextWindow * reserveRatio);
  let maxOutput = modelMax > 0 ? modelMax : reservedByRatio;

  const callerCap = positiveOr(options.maxOutputTokens, 0);
  if (callerCap > 0) maxOutput = Math.min(maxOutput, callerCap);

  // Never let the reserved output exceed the window.
  maxOutput = Math.min(maxOutput, contextWindow);

  const inputBudget = Math.max(contextWindow - maxOutput, 0);
  const compactionThreshold = Math.floor(inputBudget * compactionRatio);

  return { contextWindow, maxOutput, inputBudget, compactionThreshold };
}

function positiveOr(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

function clampRatio(value: number | undefined, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  if (value <= 0 || value >= 1) return fallback;
  return value;
}
