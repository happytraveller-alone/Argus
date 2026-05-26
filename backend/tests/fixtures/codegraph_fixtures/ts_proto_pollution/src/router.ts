/*
 * Cross-file prototype pollution test fixture (CWE-1321).
 *
 * Express-style HTTP handler reads `req.body` and forwards it directly to a
 * recursive merge helper that walks the keys without filtering `__proto__`
 * (or `constructor.prototype`). A codegraph-aware Hunt MUST identify the
 * chain `mergeUserSettings -> deepMerge` as reachable across 2 files and
 * — because no sanitizer in the chain is in the TypeScript SoT — classify
 * the finding as `real` via `llm_inferred`.
 */

import { deepMerge } from "./utils/merge";

// In-memory user-settings store; not realistic, just enough for the trace.
const userSettings: Record<string, unknown> = {};

export function mergeUserSettings(req: { body: Record<string, unknown> }) {
  // Source: `req.body` is untrusted; keys can include `__proto__`.
  const update = req.body;
  // Sink-reaching call: forwards the untrusted record to deepMerge.
  return deepMerge(userSettings, update);
}
