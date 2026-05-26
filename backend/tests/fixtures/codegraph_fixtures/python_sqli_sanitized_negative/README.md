# python_sqli_sanitized_negative

This fixture demonstrates the sanitized-via-parameterization pattern that
internal code review should classify as **not-actionable**. It mirrors the
shape of `python_sqli/` (`app.py` → `parser.py` → `db.py`) but `db.py`
constructs the query through `psycopg2.sql.SQL(...).format(pg_sql.Placeholder())`
and binds the user-controlled value at `cur.execute(query, params)` instead of
string-interpolating it.

`psycopg2.sql.SQL` is a canonical entry in the Python sanitizer Source of
Truth (`backend/src/runtime/intelligent/code_intel/sanitizer_sot.rs`). The
audit pipeline MUST classify the seeded finding as `category=sanitized`,
`confidence_source=rule_matched`, and surface the matched symbol via
`sanitizer_symbols=["psycopg2.sql.SQL"]`.

This is a static-analysis test fixture demonstrating safe-coding patterns. It
is NOT a real application and MUST NOT be deployed.
