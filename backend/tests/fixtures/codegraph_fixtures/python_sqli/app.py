"""Flask entrypoint for the cross-file SQLi test fixture.

Source: ``flask.request.args`` arrives via :func:`parser.parse_request`,
flows through :func:`db.build_query`, and is executed at :func:`db.run_query`.
A codegraph-aware Trace stage MUST identify the chain
``handle_lookup -> parse_request -> build_query -> run_query`` as reachable.
"""
from flask import Flask, request, jsonify

from parser import parse_request
from db import build_query, run_query

app = Flask(__name__)


@app.route("/lookup")
def handle_lookup():
    parsed = parse_request(request)
    query = build_query(parsed)
    return jsonify(run_query(query))
