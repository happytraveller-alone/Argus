# CodeGraph Integration Test Fixtures

Test corpora used by the codegraph-integration acceptance tests. Each fixture
is a deliberately small, intentionally-flawed-or-sanitized project authored
solely to exercise the Argus intelligent audit pipeline's reasoning over
multi-file call graphs.

These fixtures are NOT real applications. They MUST NOT be deployed. They are
DVWA/WebGoat-style training material that the audit pipeline uses to verify
its own reasoning under controlled, ground-truthed inputs.

## Fixtures

Phase 2 / v0.2 acceptance matrix — **6 fixtures**: 3 real-label (Python, Java,
TS) + 3 dismissible negative (sanitized, test, vendor). This is the corpus the
`codegraph_ac2_acceptance` suite runs the production-threshold gates on
(real recall ≥ 90%, sanitized precision ≥ 80%, FPR ≤ 20%, vendor 100%, test 100%).

| Fixture | Language | Pattern | Reachable? | Classification | Phase |
|---------|----------|---------|------------|----------------|-------|
| `python_sqli/` | Python (Flask) | SQL injection across 3 files | Yes | real (llm_inferred) | 1 |
| `java_path_traversal/` | Java (Spring) | Path traversal across 2 files | Yes | real (llm_inferred) | 1 |
| `ts_proto_pollution/` | TypeScript | Prototype pollution across 2 files (no SoT sanitizer in chain) | Yes | real (llm_inferred) | 2 |
| `python_sqli_sanitized_negative/` | Python | `psycopg2.sql.SQL` parameterized variant of `python_sqli/` | No | sanitized (rule_matched) | 1 |
| `java_path_traversal_test_negative/` | Java | Identical shape to `java_path_traversal/`, located under `src/test/java/` | No | test (path_pattern) | 1 |
| `python_sqli_vendor_negative/` | Python | Identical shape to `python_sqli/`, located under `vendor/` | No | vendor (path_pattern) | 2 |

The three negative fixtures exercise distinct dismissal channels:
- `..._sanitized_negative` → **SoT (`rule_matched`)** — the most specific channel
- `..._test_negative` → **path classifier (`path_pattern`)** with `src/test/java/`
- `..._vendor_negative` → **path classifier (`path_pattern`)** with `vendor/`

The three real fixtures exercise recall on cross-file taint flows with no
sanitizer in any chain — the audit pipeline must surface each one without
emitting a dismissal verdict.

## Layout per fixture

- Source files implementing the (un)sanitized chain
- `README.md` — ground truth statement
- `finding.json` — seeded finding metadata as it would arrive at the Trace
  stage from upstream Hunt/Validate/Dedupe pipeline

## `finding.json` schema

Each fixture's `finding.json` carries:

| Field | Type | Purpose |
|-------|------|---------|
| `finding_id` | string | unique fixture-scoped id |
| `file`, `line_start`, `line_end` | string + ints | source location of the (potential) sink |
| `vuln_class` | string | e.g. `sql_injection`, `path_traversal` |
| `severity` | string | `low \| medium \| high \| critical` |
| `description` | string | natural-language summary |
| `evidence` | string | code snippet of the sink |
| `expected_reachable` | bool | ground-truth reachability assertion for Trace |
| `expected_call_chain` | string[] | ordered list of node names the audit pipeline must rediscover |
| `expected_classification` (Phase 0) | `"real" \| "sanitized" \| "test" \| "vendor"` | ground-truth dismissal category — assertions for AC1/AC2 acceptance suites |
| `expected_confidence_source` (Phase 0) | `"rule_matched" \| "llm_inferred" \| "path_pattern"` | ground-truth provenance — which evidence channel SHOULD produce the verdict |
| `expected_path_pattern` (Phase 0) | string \| null | matched glob fragment when `confidence_source == "path_pattern"`, else `null` |

Phase 0 added the last three fields. Phase 1 / v0.1 adds:

| Field | Type | Purpose |
|-------|------|---------|
| `expected_sanitizer_symbols` (Phase 1) | string[] | canonical SoT entries the audit pipeline must surface in `dismissal_evidence.sanitizer_symbols` (only meaningful when `expected_confidence_source == "rule_matched"`) |
| `expected_dismissal_rationale` (Phase 1) | string \| null | non-binding human-readable rationale for the dismissal (test harnesses may assert substring match) |

## Provenance

Patterns are well-documented CWE references (CWE-89, CWE-22, CWE-918,
CWE-1321). No real-world credentials, IPs, or production data are embedded.
