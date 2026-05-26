/*
 * Recursive merge helper — the sink for the prototype-pollution fixture.
 *
 * `deepMerge` walks the source object's keys and recursively merges into the
 * target without filtering reserved keys (`__proto__`, `constructor`,
 * `prototype`). When the attacker supplies `{"__proto__": {"polluted": true}}`
 * via `mergeUserSettings`, `Object.prototype.polluted` becomes `true` for the
 * lifetime of the process.
 *
 * No call in this chain hits the TypeScript sanitizer SoT — the audit pipeline
 * must classify as `real` / `llm_inferred`.
 */

type Bag = Record<string, unknown>;

export function deepMerge(target: Bag, source: Bag): Bag {
  for (const key of Object.keys(source)) {
    const value = source[key];
    if (value !== null && typeof value === "object") {
      // Sink: no `key === "__proto__"` guard, no `Object.create(null)` target.
      // Untrusted nested object writes into target[key] recursively.
      if (typeof target[key] !== "object" || target[key] === null) {
        target[key] = {};
      }
      deepMerge(target[key] as Bag, value as Bag);
    } else {
      target[key] = value;
    }
  }
  return target;
}
