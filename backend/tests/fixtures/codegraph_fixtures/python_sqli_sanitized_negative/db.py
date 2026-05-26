"""Safe sink: builds a parameterized SQL via ``psycopg2.sql.SQL``.

``psycopg2.sql.SQL`` is a canonical entry in the Python sanitizer SoT
(see ``code_intel/sanitizer_sot.rs::PYTHON_SANITIZERS``). The audit pipeline
must classify the finding here as ``sanitized`` / ``rule_matched``.
"""
import psycopg2
import psycopg2.sql as pg_sql


def build_query(parsed):
    # Composed via psycopg2.sql.SQL — parameterized at execute() time. The
    # `{}` placeholder is bound, NOT string-interpolated, so user_id cannot
    # escape into the SQL grammar.
    return pg_sql.SQL("SELECT * FROM users WHERE id = {}").format(
        pg_sql.Placeholder()
    )


def run_query(query, parsed):
    # Parameter binding — user_id is escaped by the driver, not by us.
    conn = psycopg2.connect("dbname=test")
    with conn.cursor() as cur:
        cur.execute(query, (parsed["user_id"],))
        return cur.fetchall()
