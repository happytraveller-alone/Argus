# CodeGraph Integration Test Fixtures

Test corpora used by the codegraph-integration acceptance tests. Each fixture
is a deliberately small, intentionally-flawed-or-sanitized project authored
solely to exercise the Argus intelligent audit pipeline's reasoning over
multi-file call graphs.

These fixtures are NOT real applications. They MUST NOT be deployed. They are
DVWA/WebGoat-style training material that the audit pipeline uses to verify
its own reasoning under controlled, ground-truthed inputs.

## Fixtures

| Fixture | Language | Pattern | Reachable? |
|---------|----------|---------|------------|
| `python_sqli/` | Python (Flask) | SQL injection across 3 files | Yes |
| `java_path_traversal/` | Java (Spring) | Path traversal across 2 files | Yes |
| `go_ssrf/` | Go | SSRF across 2 files | Yes |
| `ts_proto_pollution/` | TypeScript (Express) | Prototype pollution across 2 files | Yes |
| `python_sanitized_negative/` | Python | Same shape as `python_sqli` BUT properly parameterized | No |

The negative fixture (`python_sanitized_negative`) is critical for AC1
precision: codegraph-backed Trace must not over-flag a sanitized chain as
reachable. The other four exercise recall on real cross-file taint flows.

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

Phase 0 adds the last three fields. Additional fields (`expected_sanitizer_symbols`,
`expected_dismissal_rationale`) will land in Phase 1 alongside SoT and Hunt Pass 2.

## Provenance

Patterns are well-documented CWE references (CWE-89, CWE-22, CWE-918,
CWE-1321). No real-world credentials, IPs, or production data are embedded.
