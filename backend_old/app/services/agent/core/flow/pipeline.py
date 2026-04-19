from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent.runtime_settings import settings
from app.services.agent.core.flow.lightweight.ast_index import ASTCallIndex
from app.services.agent.core.flow.lightweight.callgraph_code2flow import Code2FlowCallGraph
from app.services.agent.core.flow.lightweight.path_scorer import (
    build_lightweight_flow_evidence,
)
from app.services.agent.core.flow.models import FlowEvidence
from app.services.agent.logic.authz_rules import AuthzRuleEngine

logger = logging.getLogger(__name__)


class FlowEvidencePipeline:
    """Flow evidence pipeline.

    1) tree-sitter + code2flow lightweight path
    2) logic authz graph rules for auth/IDOR style issues
    """

    def __init__(
        self,
        *,
        project_root: str,
        target_files: Optional[List[str]] = None,
    ):
        self.project_root = project_root
        self.target_files = target_files or []

        self.light_enabled = bool(getattr(settings, "FLOW_LIGHTWEIGHT_ENABLED", True))
        self.logic_enabled = bool(getattr(settings, "LOGIC_AUTHZ_ENABLED", True))
        self.unreachable_policy = str(getattr(settings, "FLOW_UNREACHABLE_POLICY", "degrade_likely"))

        self.ast_index = ASTCallIndex(project_root=project_root, target_files=target_files)
        self.code2flow = Code2FlowCallGraph(project_root=project_root, target_files=target_files)
        self.code2flow_result = None
        self.logic_engine = (
            AuthzRuleEngine(project_root=project_root, target_files=target_files)
            if self.logic_enabled
            else None
        )

    def _normalize_line(self, value: Any) -> int:
        try:
            line = int(value)
            return max(1, line)
        except Exception:
            return 1

    def _ensure_code2flow(self) -> None:
        if self.code2flow_result is not None:
            return
        try:
            self.code2flow_result = self.code2flow.generate()
        except Exception as exc:
            logger.warning("Code2Flow generation failed: %s", exc)
            self.code2flow_result = None

    async def _build_lightweight(self, finding: Dict[str, Any]) -> FlowEvidence:
        if not self.light_enabled:
            return FlowEvidence(
                path_found=False,
                path_score=0.0,
                blocked_reasons=["lightweight_flow_disabled"],
                engine="ts_code2flow",
            )

        file_path = str(finding.get("file_path") or "").strip()
        if not file_path:
            return FlowEvidence(
                path_found=False,
                path_score=0.0,
                blocked_reasons=["missing_file_path"],
                engine="ts_code2flow",
            )

        line_start = self._normalize_line(finding.get("line_start"))
        # Optional hint: restrict entry points for path search (improves cross-file chain quality).
        raw_entry_points = finding.get("entry_points")
        entry_points: Optional[List[str]] = None
        if isinstance(raw_entry_points, list):
            normalized = [
                str(item).strip()
                for item in raw_entry_points
                if isinstance(item, (str, int, float)) and str(item).strip()
            ]
            if normalized:
                entry_points = normalized[:80]

        self.ast_index.build()
        self._ensure_code2flow()

        extra_edges = self.code2flow_result.edges if self.code2flow_result else None
        path_result = self.ast_index.find_path(
            target_file=file_path,
            target_line=line_start,
            max_depth=9,
            entry_points=entry_points,
            extra_edges=extra_edges,
        )

        has_code2flow = bool(
            self.code2flow_result
            and self.code2flow_result.used_engine == "code2flow"
            and self.code2flow_result.edges
        )

        evidence = build_lightweight_flow_evidence(path_result, has_code2flow=has_code2flow)
        if self.code2flow_result and self.code2flow_result.blocked_reasons:
            evidence.blocked_reasons = list(
                dict.fromkeys(evidence.blocked_reasons + self.code2flow_result.blocked_reasons)
            )
        return evidence

    async def _build_logic_evidence(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        if not self.logic_engine:
            return {
                "missing_authz_checks": False,
                "resource_scope_mismatch": False,
                "idor_path": False,
                "proof_nodes": [],
                "evidence": [],
                "blocked_reasons": ["logic_authz_disabled"],
            }
        return self.logic_engine.analyze_finding(finding)

    async def analyze_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        lightweight = await self._build_lightweight(finding)
        logic_authz = await self._build_logic_evidence(finding)

        return {
            "flow": lightweight.to_dict(),
            "logic_authz": logic_authz,
        }

    async def enrich_findings(
        self,
        findings: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        enriched: List[Dict[str, Any]] = []
        counters = {
            "total": len(findings),
            "path_found": 0,
            "logic_hits": 0,
        }

        for finding in findings:
            if not isinstance(finding, dict):
                continue

            evidence_payload = await self.analyze_finding(finding)
            flow = evidence_payload.get("flow") or {}
            logic = evidence_payload.get("logic_authz") or {}

            merged = dict(finding)
            verification_result = merged.get("verification_result")
            if not isinstance(verification_result, dict):
                verification_result = {}
            verification_result["flow"] = flow
            verification_result["logic_authz"] = logic
            merged["verification_result"] = verification_result

            flow_chain = flow.get("call_chain") if isinstance(flow, dict) else None
            if isinstance(flow_chain, list) and flow_chain:
                merged["dataflow_path"] = flow_chain

            if flow.get("path_found"):
                counters["path_found"] += 1
            if logic.get("missing_authz_checks") or logic.get("resource_scope_mismatch") or logic.get("idor_path"):
                counters["logic_hits"] += 1

            if self.unreachable_policy == "degrade_likely":
                if not flow.get("path_found"):
                    merged_reachability = str(merged.get("reachability") or "").strip().lower()
                    if not merged_reachability:
                        merged["reachability"] = "likely_reachable"
                    authenticity = str(
                        merged.get("authenticity") or merged.get("verdict") or ""
                    ).strip().lower()
                    if authenticity == "confirmed":
                        merged["authenticity"] = "likely"
                        merged["verdict"] = "likely"
            enriched.append(merged)

        return enriched, counters


__all__ = ["FlowEvidencePipeline"]
