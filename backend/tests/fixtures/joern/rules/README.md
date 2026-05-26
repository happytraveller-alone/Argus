# Joern Rule Corpus Fixtures

Per-rule positive/negative C fixture trees for the Joern detection rule corpus.

## Layout

```
rules/
  <rule_id>/
    positive.c      — minimal C source that MUST trigger the rule
    negative.c      — minimal C source that MUST NOT trigger the rule
    expected.json   — single Finding object for positive.c's first finding
```

## file_path placeholder convention

`expected.json` uses a relative placeholder of the form `<rule_id>/positive.c`
(e.g. `"file_path": "joern-c-unsafe-gets/positive.c"`).

The Rust corpus test (`joern_rule_corpus.rs`) does **not** match `file_path`
exactly. It asserts `file_path.ends_with("<rule_id>/positive.c")` so the test
is independent of the absolute container mount path (`/work/...`) chosen at
runtime.

## expected.json shape

A single JSON object (not a list, not wrapped in `{schema_version, findings}`):

```json
{
  "rule_id": "joern-c-<rule>",
  "cwe": ["CWE-XXX"],
  "cve": [],
  "severity": "HIGH|MEDIUM",
  "confidence": "HIGH|MEDIUM|LOW",
  "file_path": "<rule_id>/positive.c",
  "function": "<func name>",
  "start_line": <N>,
  "end_line": <N>,
  "evidence": {
    "call": "<call or operator name>",
    "code": "<call expression text>"
  }
}
```

The `id` field is **omitted** — it contains a `sha8(evidence.code)` suffix
that cannot be predicted before the CPG is built. The Rust test asserts
presence and shape, not the exact `id` value.

## How the Rust corpus test consumes these fixtures

`joern_rule_corpus.rs` iterates every subdirectory under `rules/`:

1. Parses the rule name from the directory name.
2. Runs `joern-parse` + the rule module against `positive.c` inside a podman
   sandbox; asserts at least one finding where `rule_id` and
   `file_path.ends_with(...)` match `expected.json`.
3. Runs the same scan against `negative.c`; asserts zero findings for that
   `rule_id`.

Timeout is governed by `JOERN_CORPUS_TIMEOUT_SECS` (default 600).
