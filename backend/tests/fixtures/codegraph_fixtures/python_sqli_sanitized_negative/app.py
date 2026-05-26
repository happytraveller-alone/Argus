"""Flask entrypoint for the sanitized-via-parameterization fixture.

Mirrors the shape of ``python_sqli/app.py`` but the data flow ends in a safe
parameterized query (see :func:`db.run_query`). A codegraph-aware Hunt MUST
classify the resulting finding as ``sanitized`` with ``confidence_source =
rule_matched`` because ``psycopg2.sql.SQL`` is in the SoT.

Chain (matches python_sqli):
    handle_lookup -> parse_request -> build_query -> run_query
"""
from flask import Flask, request, jsonify

from parser import parse_request
from db import build_query, run_query

app = Flask(__name__)


@app.route("/lookup")
def handle_lookup():
    parsed = parse_request(request)
    query = build_query(parsed)
    return jsonify(run_query(query, parsed))
