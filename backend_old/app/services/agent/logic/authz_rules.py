from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.agent.logic.authz_graph_builder import AuthzGraphBuilder, AuthzNode


class AuthzRuleEngine:
    """Route/handler -> auth check -> resource access rule engine."""

    def __init__(self, project_root: str, target_files: Optional[List[str]] = None):
        self.builder = AuthzGraphBuilder(project_root=project_root, target_files=target_files)

    def _as_evidence_line(self, node: AuthzNode, reason: str) -> str:
        return f"{reason}: {node.file_path}:{node.start_line} ({node.name})"

    def analyze_node(self, node: AuthzNode) -> Dict[str, Any]:
        missing_authz_checks = node.is_route and node.has_resource_access and not node.has_auth_check
        resource_scope_mismatch = node.has_auth_check and node.has_resource_access and not node.has_object_scope_check
        idor_path = node.is_route and node.has_resource_access and node.has_id_reference and not node.has_object_scope_check

        evidence: List[str] = []
        if missing_authz_checks:
            evidence.append(self._as_evidence_line(node, "missing_authz_checks"))
        if resource_scope_mismatch:
            evidence.append(self._as_evidence_line(node, "resource_scope_mismatch"))
        if idor_path:
            evidence.append(self._as_evidence_line(node, "idor_path"))

        return {
            "missing_authz_checks": bool(missing_authz_checks),
            "resource_scope_mismatch": bool(resource_scope_mismatch),
            "idor_path": bool(idor_path),
            "proof_nodes": node.proof_nodes(),
            "evidence": evidence,
        }

    def analyze_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        file_path = str(finding.get("file_path") or "").strip()
        line_start = finding.get("line_start")
        try:
            line_start = int(line_start)
        except Exception:
            line_start = None

        if not file_path or line_start is None:
            return {
                "missing_authz_checks": False,
                "resource_scope_mismatch": False,
                "idor_path": False,
                "proof_nodes": [],
                "evidence": [],
                "blocked_reasons": ["logic_missing_location"],
            }

        node = self.builder.find_node_by_location(file_path, max(1, line_start))
        if not node:
            return {
                "missing_authz_checks": False,
                "resource_scope_mismatch": False,
                "idor_path": False,
                "proof_nodes": [],
                "evidence": [],
                "blocked_reasons": ["logic_node_not_found"],
            }

        return self.analyze_node(node)

    def analyze_project(self) -> Dict[str, Any]:
        nodes = self.builder.build_nodes()
        evidence: List[str] = []
        proof_nodes: List[str] = []
        missing = 0
        mismatch = 0
        idor = 0

        for node in nodes:
            result = self.analyze_node(node)
            if result.get("missing_authz_checks"):
                missing += 1
            if result.get("resource_scope_mismatch"):
                mismatch += 1
            if result.get("idor_path"):
                idor += 1
            evidence.extend(result.get("evidence") or [])
            proof_nodes.extend(result.get("proof_nodes") or [])

        return {
            "missing_authz_checks": missing,
            "resource_scope_mismatch": mismatch,
            "idor_path": idor,
            "proof_nodes": list(dict.fromkeys(proof_nodes))[:50],
            "evidence": list(dict.fromkeys(evidence))[:100],
            "summary": self.builder.summarize(),
        }


__all__ = ["AuthzRuleEngine"]
