from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.agent.flow.lightweight.ast_index import ASTCallIndex
from app.services.agent.flow.lightweight.callgraph_code2flow import Code2FlowCallGraph
from app.services.agent.flow.lightweight.path_scorer import build_lightweight_flow_evidence
from app.services.agent.flow.joern.joern_client import JoernClient
from app.services.agent.flow.joern.codebadger_poc_query import infer_codebadger_language
from app.services.agent.flow.models import FlowEvidence, merge_flow_evidence
from app.services.agent.logic.authz_rules import AuthzRuleEngine

logger = logging.getLogger(__name__)


class FlowEvidencePipeline:
    """Three-track flow evidence pipeline.

    1) tree-sitter + code2flow lightweight path
    2) Joern deep verification for high-risk candidates
    3) logic authz graph rules for auth/IDOR style issues
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
        self.joern_enabled = bool(getattr(settings, "FLOW_JOERN_ENABLED", True))
        self.logic_enabled = bool(getattr(settings, "LOGIC_AUTHZ_ENABLED", True))
        self.unreachable_policy = str(getattr(settings, "FLOW_UNREACHABLE_POLICY", "degrade_likely"))

        self.joern_trigger_severity = {
            item.strip().lower()
            for item in str(
                getattr(settings, "FLOW_JOERN_TRIGGER_SEVERITY", "high,critical")
            ).split(",")
            if item.strip()
        }
        self.joern_trigger_confidence = float(
            getattr(settings, "FLOW_JOERN_TRIGGER_CONFIDENCE", 0.7)
        )

        self.ast_index = ASTCallIndex(project_root=project_root, target_files=target_files)
        self.code2flow = Code2FlowCallGraph(project_root=project_root, target_files=target_files)
        self.code2flow_result = None

        self.joern_client = JoernClient(
            enabled=self.joern_enabled,
            timeout_sec=int(getattr(settings, "FLOW_JOERN_TIMEOUT_SEC", 45)),
            mcp_enabled=bool(getattr(settings, "JOERN_MCP_ENABLED", False)),
            mcp_url=str(
                getattr(settings, "JOERN_MCP_URL", "")
                or getattr(settings, "MCP_CODEBADGER_BACKEND_URL", "")
                or ""
            ),
            mcp_prefer=bool(getattr(settings, "JOERN_MCP_PREFER", False)),
            mcp_cpg_timeout_sec=int(getattr(settings, "JOERN_MCP_CPG_TIMEOUT_SEC", 240)),
            mcp_query_timeout_sec=int(getattr(settings, "JOERN_MCP_QUERY_TIMEOUT_SEC", 90)),
        )
        self.logic_engine = (
            AuthzRuleEngine(project_root=project_root, target_files=target_files)
            if self.logic_enabled
            else None
        )

    def _normalize_confidence(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        text = str(value).strip().lower()
        if text in {"high", "h"}:
            return 0.9
        if text in {"medium", "med", "m"}:
            return 0.7
        if text in {"low", "l"}:
            return 0.4
        try:
            parsed = float(text)
            return max(0.0, min(parsed, 1.0))
        except Exception:
            return 0.0

    def _normalize_line(self, value: Any) -> int:
        try:
            line = int(value)
            return max(1, line)
        except Exception:
            return 1

    def _should_trigger_joern(self, finding: Dict[str, Any], lightweight: FlowEvidence) -> bool:
        if not self.joern_enabled:
            return False

        # Smart audit policy: only allow Joern for Java / C / C++.
        file_path = str(finding.get("file_path") or "").strip()
        if not infer_codebadger_language(file_path):
            return False

        severity = str(finding.get("severity") or "").strip().lower()
        if severity not in self.joern_trigger_severity:
            return False

        confidence = self._normalize_confidence(
            finding.get("confidence")
            or finding.get("ai_confidence")
            or finding.get("verification_result", {}).get("confidence")
        )
        if confidence < self.joern_trigger_confidence:
            return False

        # Prefer Joern for gray-zone path scores as configured in design.
        return 0.35 <= lightweight.path_score <= 0.75

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
        selected = lightweight

        if self._should_trigger_joern(finding, lightweight):
            try:
                joern = await self.joern_client.verify_reachability(
                    project_root=self.project_root,
                    file_path=str(finding.get("file_path") or ""),
                    line_start=self._normalize_line(finding.get("line_start")),
                    call_chain=lightweight.call_chain,
                    control_conditions=lightweight.control_conditions,
                )
                selected = merge_flow_evidence(joern, lightweight)
            except Exception as exc:
                logger.warning("Joern verification failed, fallback to lightweight: %s", exc)

        logic_authz = await self._build_logic_evidence(finding)

        return {
            "flow": selected.to_dict(),
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
            "joern_upgrades": 0,
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

            if isinstance(flow, dict) and flow.get("engine") == "joern":
                counters["joern_upgrades"] += 1

            enriched.append(merged)

        return enriched, counters


__all__ = ["FlowEvidencePipeline"]
