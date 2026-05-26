"""Flask entrypoint for the vendored-SQLi fixture.

The taint flow in this file is INTENTIONALLY identical to ``python_sqli/app.py``
— same source (``request.args``), same chain
(``handle_lookup -> parse_request -> build_query -> run_query``), same sink
(f-string SQL interpolation). The only difference is the on-disk layout: this
tree lives entirely under ``vendor/`` so the path classifier classifies any
finding as ``category=vendor`` with ``confidence_source=path_pattern``.

Internal code review must NOT spend reviewer attention on vendor-pinned code —
it's not first-party so engineers cannot patch the sink here.
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
