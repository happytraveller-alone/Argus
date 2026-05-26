"""Flask entrypoint mirror of the python_sqli fixture, but the SQL sink is
guarded by a static ``if False:`` block in db.py — the call chain is therefore
dead code from the audit perspective."""
from flask import Flask, request, jsonify

from parser import parse_request
from db import build_query, run_query

app = Flask(__name__)


@app.route("/lookup")
def handle_lookup():
    parsed = parse_request(request)
    query = build_query(parsed)
    return jsonify(run_query(query))
