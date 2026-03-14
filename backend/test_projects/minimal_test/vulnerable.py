"""Minimal vulnerable fixture used by parallel workflow tests."""


def sql_injection_vuln(user_input: str) -> str:
    """Potential SQL injection in dynamic query construction."""
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return query


def command_injection_vuln(user_input: str) -> str:
    """Potential command injection in shell command assembly."""
    cmd = f"ping -c 1 {user_input}"
    return cmd


def path_traversal_vuln(user_input: str) -> str:
    """Potential path traversal when joining user-controlled path segments."""
    return f"/tmp/uploads/{user_input}"


def xss_vuln(user_input: str) -> str:
    """Potential reflected XSS when raw HTML is returned."""
    return f"<div>{user_input}</div>"
