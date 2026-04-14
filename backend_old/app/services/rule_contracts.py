from __future__ import annotations

from pydantic import BaseModel


class OpengrepRuleCreateRequest(BaseModel):
    """Payload used when generating Opengrep rules from patches."""

    repo_owner: str
    repo_name: str
    commit_hash: str
    commit_content: str
