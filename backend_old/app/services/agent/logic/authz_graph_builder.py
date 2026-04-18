from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.services.agent.core.flow.lightweight.ast_index import ASTCallIndex, FunctionSymbol

ROUTE_PATTERNS = [
    r"@app\.route",
    r"@router\.",
    r"app\.(get|post|put|delete|patch)\(",
    r"router\.(get|post|put|delete|patch)\(",
    r"@RequestMapping",
    r"@GetMapping",
    r"@PostMapping",
    r"route\(",
    r"handler",
]

AUTH_CHECK_PATTERNS = [
    r"auth",
    r"authorize",
    r"permission",
    r"is_admin",
    r"jwt",
    r"token",
    r"acl",
    r"role",
    r"guard",
    r"rbac",
]

RESOURCE_ACCESS_PATTERNS = [
    r"\bselect\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\binsert\b",
    r"db\.",
    r"repository\.",
    r"dao\.",
    r"find_by_id",
    r"save\(",
    r"remove\(",
]

OBJECT_SCOPE_PATTERNS = [
    r"owner(_id)?\s*==",
    r"user(_id)?\s*==",
    r"tenant(_id)?\s*==",
    r"org(_id)?\s*==",
    r"check_permission\(",
    r"authorize\(",
    r"can_access\(",
    r"scope",
    r"subject",
]

IDOR_HINT_PATTERNS = [
    r"\bid\b",
    r"resource_id",
    r"object_id",
    r"account_id",
]


@dataclass
class AuthzNode:
    symbol_id: str
    file_path: str
    name: str
    start_line: int
    end_line: int
    is_route: bool
    has_auth_check: bool
    has_resource_access: bool
    has_object_scope_check: bool
    has_id_reference: bool

    def proof_nodes(self) -> List[str]:
        return [
            f"route:{self.file_path}:{self.start_line}",
            f"handler:{self.name}",
            f"resource:{self.file_path}:{self.end_line}",
        ]


class AuthzGraphBuilder:
    """AST-based graph builder for auth/authz logic vulnerabilities."""

    def __init__(self, project_root: str, target_files: Optional[List[str]] = None):
        self.index = ASTCallIndex(project_root=project_root, target_files=target_files)
        self._nodes_cache: Optional[List[AuthzNode]] = None

    def _match_any(self, content: str, patterns: List[str]) -> bool:
        return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in patterns)

    def _build_node(self, symbol: FunctionSymbol) -> AuthzNode:
        body = symbol.content or ""
        lowered = body.lower()
        inferred_route = (
            "request." in lowered
            and ("args.get(" in lowered or "params" in lowered or "path" in lowered)
        )
        return AuthzNode(
            symbol_id=symbol.id,
            file_path=symbol.file_path,
            name=symbol.name,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            is_route=self._match_any(body, ROUTE_PATTERNS) or symbol.is_entry or inferred_route,
            has_auth_check=self._match_any(body, AUTH_CHECK_PATTERNS),
            has_resource_access=self._match_any(body, RESOURCE_ACCESS_PATTERNS),
            has_object_scope_check=self._match_any(body, OBJECT_SCOPE_PATTERNS),
            has_id_reference=self._match_any(body, IDOR_HINT_PATTERNS),
        )

    def build_nodes(self) -> List[AuthzNode]:
        if self._nodes_cache is not None:
            return self._nodes_cache

        self.index.build()
        nodes: List[AuthzNode] = []
        for symbol in self.index.symbols_by_id.values():
            try:
                node = self._build_node(symbol)
                if node.is_route or node.has_resource_access:
                    nodes.append(node)
            except Exception:
                continue

        self._nodes_cache = nodes
        return nodes

    def find_node_by_location(self, file_path: str, line_start: int) -> Optional[AuthzNode]:
        normalized = str(file_path).replace("\\", "/").lstrip("./")
        for node in self.build_nodes():
            if node.file_path != normalized:
                continue
            if node.start_line <= line_start <= node.end_line:
                return node
        return None

    def summarize(self) -> Dict[str, int]:
        nodes = self.build_nodes()
        return {
            "total_nodes": len(nodes),
            "route_nodes": sum(1 for item in nodes if item.is_route),
            "resource_nodes": sum(1 for item in nodes if item.has_resource_access),
            "auth_checked_nodes": sum(1 for item in nodes if item.has_auth_check),
        }


__all__ = ["AuthzGraphBuilder", "AuthzNode"]
