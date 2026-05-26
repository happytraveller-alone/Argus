# Argus Joern C/C++ Vulnerability Detection Rules

This directory holds the Joern-based static analysis rule corpus for C/C++ scans run inside the Argus pipeline.

## Layout

```
rules_joern/
├── README.md                       # this file
└── c/
    ├── argus-joern-scan.sc         # orchestrator (the single @main entry; the wrapper invokes this)
    └── lib/
        ├── common.sc               # Finding case class, JSON helpers, externSources,
        │                           # reachableBySafe wrapper, knownCves map, tagCves, output writers
        ├── UPSTREAM_PIN.toml       # pinned Joern querydb SHA for B7/B8 drift-CI step
        ├── unsafe_gets.sc                  # B1
        ├── tainted_strcpy.sc               # B2
        ├── tainted_memcpy.sc               # B3 — catches libplist CVE-2017-6439
        ├── tainted_sprintf_buffer.sc       # B4
        ├── strncpy_missing_null_term.sc    # B5
        ├── alloc_mul_tainted.sc            # B6
        ├── strlen_int_truncation.sc        # B7 — verbatim from upstream IntegerTruncations
        └── signed_left_shift.sc            # B8 — verbatim from upstream SignedLeftShift
```

The Rust runtime hardcodes the orchestrator path (`backend/src/scan/joern.rs:29`) — do not rename `argus-joern-scan.sc`.

## Rule reference

| Rule ID | CWE | Severity | Default Confidence | Taint required? | What it detects |
|---|---|---|---|---|---|
| `joern-c-unsafe-gets` | CWE-120 | HIGH | MEDIUM | no | Any call to `gets()` (always unsafe — no length parameter). |
| `joern-c-tainted-strcpy` | CWE-120, CWE-787 | HIGH | tiered | optional | `strcpy(dest, src)` where `src` is non-literal; HIGH if `src` reaches from an external source AND no bounds-check dominator. |
| `joern-c-tainted-memcpy` | CWE-120, CWE-787 | HIGH | tiered | optional | `memcpy(dest, src, n)` where `n` is non-literal and not `sizeof(...)`. Structural alone fires libplist's `parse_string_node` `memcpy` at bplist.c:288. Taint upgrades confidence. |
| `joern-c-tainted-sprintf-buffer` | CWE-120 | HIGH | tiered | optional | `sprintf`/`vsprintf` with literal format and a tainted value argument (buffer-too-small variant; CWE-134 is out of scope this round). |
| `joern-c-strncpy-missing-null-term` | CWE-170 | MEDIUM | MEDIUM | no | `strncpy(dest, src, sizeof(dest))` not followed by explicit `dest[N-1] = '\0'` in the next 5 sibling AST statements. |
| `joern-c-alloc-mul-tainted` | CWE-190, CWE-680 | HIGH | tiered | optional | `malloc/alloca/realloc/calloc` whose size argument is a multiplication, excluding the all-literal case. HIGH if any factor is tainted. |
| `joern-c-strlen-int-truncation` | CWE-192, CWE-190 | MEDIUM | MEDIUM | no | `int n = strlen(s);` — return value of `strlen` (which is `size_t`) assigned to a narrower `int` on 64-bit platforms. Verbatim from upstream Joern querydb `IntegerTruncations.scala`. |
| `joern-c-signed-left-shift` | CWE-190 | MEDIUM | MEDIUM | no | Signed `<<` on `int`/`long` operands (UB by C11 § 6.5.7). Verbatim from upstream `SignedLeftShift.scala`. |

## Confidence tiering

Each tainted-* rule (B2, B3, B4, B6) assigns confidence based on evidence strength:

| Tier | Predicate |
|------|-----------|
| HIGH | structural match ∧ taint reaches sink from external source ∧ no bounds-check dominator |
| MEDIUM | structural match ∧ (taint OR no bounds-check dominator) |
| LOW | structural match only (no taint, no dominator info) |

External taint sources include: `argv`, `getenv`, `recv`, `read`, `fgets`, `gets`, `scanf`/`fscanf`, `fread`.

Rules B1, B5, B7, B8 use fixed confidence (no tiering) because the CWE class is fully captured by structural patterns.

## Dataflow-engine dependency

`common.reachableBySafe` is the SOLE wrapper around `io.joern.dataflowengineoss.language._`. Rule modules MUST NOT statically import dataflowengineoss; they call `common.reachableBySafe(sink, common.externSources(cpg))` instead.

At orchestrator load:
- `common.dataflowAvailable: Boolean` is set by reflective `Class.forName(...)`.
- If `dataflowAvailable == false`, every `reachableBySafe(...)` returns `Iterator.empty` → rules degrade to structural-only. Confidence is capped at MEDIUM (no taint upgrade is possible).
- If `dataflowAvailable == true`, taint upgrades fire normally.

The pinned image `ghcr.nju.edu.cn/joernio/joern:nightly` includes dataflowengineoss; this fallback exists for robustness against image drift.

## CVE attribution

`common.knownCves: Map[(file_basename, function, line), Seq[CVE]]` is the single source of truth for mapping generic-rule findings to specific CVE identifiers. The orchestrator applies `common.tagCves` after the rule flatMap to enrich findings with `cve: [...]` where the (file, function, line) tuple matches.

Current entries:
- `("bplist.c", "parse_string_node", 288) → Seq("CVE-2017-6439")`

To add a new CVE attribution, append to the `knownCves` map in `c/lib/common.sc` — no other change required.

## Adding a new rule

1. Create `c/lib/<rule_name>.sc` exposing `object <rule_name> { def run(cpg: Cpg): Seq[Finding] }`.
2. Append an `import $file.lib.<rule_name>` + entry in the `modules` Seq inside `c/argus-joern-scan.sc`.
3. Add per-rule fixtures under `backend/tests/fixtures/joern/rules/<rule_id>/{positive.c, negative.c, expected.json}`.
4. Append the new rule_id + asset path to:
   - `EXPECTED_JOERN_ASSET_PATHS` const in `backend/tests/joern_fixture_acceptance.rs`
   - `RULES` const in `backend/tests/joern_rule_corpus.rs`
5. **Restart the backend server**. Startup hook `rust_scan_rule_asset_sync` (`backend/src/bootstrap/init.rs:98`) walks the filesystem, upserts the new asset into `rust_scan_rule_assets`, and the next scan materializes it.

No database migration, no MCP config change, no frontend code needed.

## Schema

Each finding emitted by `common.writeFindings` matches schema `argus.joern.findings.v1`:

```json
{
  "id": "<rule_id>-<basename>-<line>-<sha8(evidence.code)>",
  "rule_id": "joern-c-<short>",
  "title": "<rule_id>",
  "message": "<rule_id>: pattern matched at <file>:<line>",
  "cwe": ["CWE-XXX"],
  "cve": ["CVE-..."] or [],
  "severity": "HIGH|MEDIUM|LOW",
  "confidence": "HIGH|MEDIUM|LOW",
  "file_path": "<source path>",
  "function": "<containing function>",
  "start_line": NNN,
  "end_line": NNN,
  "evidence": {
    "call": "<call name>",
    "code": "<call source text>",
    "taint_source": "<source kind, optional, present when dataflow upgrade fired>",
    "excluded_by": "<exclusion rationale, optional, present for downgraded findings>"
  }
}
```

The Rust parser (`backend/src/scan/joern.rs:237-251`) reads the `findings` array and `schema_version`; the `evidence` sub-object is passed through as `raw_joern` for downstream consumers.

## References

- Joern documentation: <https://docs.joern.io/>
- Upstream querydb: <https://github.com/joernio/joern/tree/master/querydb/src/main/scala/io/joern/scanners/c>
- Argus runtime wrapper: `backend/src/scan/joern.rs:114-166`
- Argus fixture-acceptance test: `backend/tests/joern_fixture_acceptance.rs`
- Argus per-rule corpus test: `backend/tests/joern_rule_corpus.rs`
- Planning artifacts: `.omc/specs/deep-dive-joern-cpp-vuln-rules.md`, `.omc/plans/ralplan-joern-cpp-vuln-rules-v2.md`
