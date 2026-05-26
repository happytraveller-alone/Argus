"""Builds a SQL string via f-string interpolation (CWE-89) and executes it."""
import sqlite3


def build_query(parsed):
    # Unsanitized interpolation — this is the sink the fixture targets.
    return f"SELECT * FROM users WHERE id = {parsed['user_id']}"


def run_query(query):
    conn = sqlite3.connect(":memory:")
    return conn.execute(query).fetchall()
