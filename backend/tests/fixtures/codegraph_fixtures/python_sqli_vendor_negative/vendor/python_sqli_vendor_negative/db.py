"""Builds a SQL string via f-string interpolation (CWE-89) and executes it.

The sink shape is IDENTICAL to ``python_sqli/db.py`` — unsafely interpolated.
The audit pipeline must dismiss findings here because the file lives under
``vendor/``, not because the code is safe.
"""
import sqlite3


def build_query(parsed):
    # Unsanitized interpolation — vendor-pinned code outside first-party patch scope.
    return f"SELECT * FROM users WHERE id = {parsed['user_id']}"


def run_query(query):
    conn = sqlite3.connect(":memory:")
    return conn.execute(query).fetchall()
