# Fixture: python_sqli_dead_code_negative (v0.3.b)

Negative fixture for the v0.3.b `DismissalCategory::DeadCode` channel.

## Pattern
Mirrors `python_sqli/`'s shape — Flask handler reading
`request.args["user_id"]`, flowing through a parser into a query builder —
but the entire SQL sink (`build_query`'s f-string interpolation +
subsequent `run_query` execution) lives inside a static `if False:` block.
The `code_intel::dead_code` detector must classify the finding at
`db.py:16` as `dead_code` with `confidence_source = rule_matched` and
`sanitizer_symbols = ["if_false_branch"]`.

## Ground truth
- **vuln_class**: `sql_injection` (apparent — actually unreachable)
- **Sink file:line**: `db.py:16` (inside `if False:`)
- **Expected classification**: `dead_code`
- **Expected confidence source**: `rule_matched`
- **Expected sanitizer_symbols**: `["if_false_branch"]`

## Files
- `app.py` — Flask route handler (unchanged from python_sqli)
- `parser.py` — extracts user input (unchanged from python_sqli)
- `db.py` — the SQL sink, GUARDED by `if False:`
- `finding.json` — fixture metadata + expected classification

## Why this fixture matters
Engineers waste triage time on findings inside dead paths. The dead-code
channel is a deterministic short-circuit that dismisses findings BEFORE the
Hunt Pass 2 LLM call, preserving budget for live-code review.
