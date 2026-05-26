"""Dead-code negative fixture — the entire taint sink lives inside ``if False:``.

Mirrors the ``python_sqli`` fixture's shape, but the call to ``build_query`` /
``run_query`` is dead-code-guarded. The v0.3.b ``code_intel::dead_code``
detector must classify the finding here as
``dismissal_evidence.category = DeadCode`` with
``confidence_source = RuleMatched`` and
``sanitizer_symbols = ["if_false_branch"]``.
"""
import sqlite3


def build_query(parsed):
    if False:
        # The f-string interpolation never executes.
        return f"SELECT * FROM users WHERE id = {parsed['user_id']}"
    return None


def run_query(query):
    if query is None:
        return []
    conn = sqlite3.connect(":memory:")
    return conn.execute(query).fetchall()
