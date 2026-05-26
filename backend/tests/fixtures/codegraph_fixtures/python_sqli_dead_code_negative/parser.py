"""Extracts the user-controlled ``user_id`` arg without validation.

Identical to the live ``python_sqli`` fixture — the dead-code guard lives in
``db.py``, not here.
"""


def parse_request(req):
    return {"user_id": req.args.get("user_id", "")}
