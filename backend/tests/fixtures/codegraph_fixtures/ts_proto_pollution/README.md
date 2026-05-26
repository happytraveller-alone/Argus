# ts_proto_pollution

Cross-file prototype pollution (CWE-1321) — the third real-label fixture in
the Phase 2 / v0.2 acceptance matrix, exercising the TypeScript SoT.

## Pattern

An Express-style handler reads attacker-controlled `req.body` and forwards
the untrusted record into a recursive merge helper that does not filter the
reserved `__proto__`, `constructor`, or `prototype` keys. The call chain
`mergeUserSettings -> deepMerge` flows across two files.

## Ground truth

- **vuln_class**: `prototype_pollution`
- **Sink file:line**: `src/utils/merge.ts:19-25` (recursive `target[key] = {}`
  + `deepMerge(target[key] as Bag, value as Bag)` without reserved-key filter)
- **Source**: `src/router.ts:18` via `req.body`
- **Reachable**: YES — taint flows `mergeUserSettings -> deepMerge` across
  `src/router.ts` and `src/utils/merge.ts`
- **Expected codegraph evidence**: `get_callers("deepMerge")` returns
  `mergeUserSettings`; `get_callees("mergeUserSettings")` returns `deepMerge`.

No call in the chain matches the TypeScript sanitizer SoT
(`code_intel/sanitizer_sot.rs::TYPESCRIPT_SANITIZERS`) — no `validator.escape`,
no `lodash.escape`, no key-allowlist primitive. The audit pipeline must
classify the finding as `category=real` with `confidence_source=llm_inferred`.

This is a static-analysis test fixture demonstrating an unsanitized cross-file
chain. It is NOT a real application and MUST NOT be deployed.
