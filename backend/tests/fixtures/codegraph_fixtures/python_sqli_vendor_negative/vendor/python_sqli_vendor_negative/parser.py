"""Extracts the user-controlled ``user_id`` arg without validation.

Identical source-side helper to ``python_sqli/parser.py``. Lives under
``vendor/`` — the path itself is what makes the finding non-actionable for
internal review, not the inner code shape.
"""


def parse_request(req):
    return {"user_id": req.args.get("user_id", "")}
