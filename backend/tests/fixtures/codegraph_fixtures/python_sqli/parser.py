"""Extracts the user-controlled ``user_id`` arg without validation."""


def parse_request(req):
    return {"user_id": req.args.get("user_id", "")}
