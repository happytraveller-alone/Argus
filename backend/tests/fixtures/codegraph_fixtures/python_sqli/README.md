# Fixture: python_sqli

## Pattern
Cross-file SQL injection (CWE-89) — Flask handler reads `request.args["user_id"]`
without validation, the value flows through a parser helper to a query builder
that interpolates it into a SQL string, and the string is executed.

## Ground truth
- **vuln_class**: `sql_injection`
- **Sink file:line**: `db.py:7` (the `f"SELECT ..."` interpolation)
- **Source**: `app.py:14` via `request.args.get("user_id")`
- **Reachable**: YES — taint flows `handle_lookup -> parse_request -> build_query -> run_query` across 3 files
- **Expected codegraph evidence**: `get_callers("build_query")` returns `parse_request` and `handle_lookup`; `get_callees("handle_lookup")` returns the full chain.

## Files
- `app.py` — Flask route handler (entry point)
- `parser.py` — extracts user input (taint source)
- `db.py` — builds and executes the SQL string (taint sink)
