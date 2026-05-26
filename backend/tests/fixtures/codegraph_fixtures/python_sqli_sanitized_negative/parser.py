"""Extracts the user-controlled ``user_id`` arg without validation.

Same as the unsafe ``python_sqli/parser.py`` — the source side is identical;
only the sink (in ``db.py``) differs. This is deliberate: the audit pipeline
must distinguish on the sink shape (parameterized vs interpolated), not on
the upstream taint source.
"""


def parse_request(req):
    return {"user_id": req.args.get("user_id", "")}
