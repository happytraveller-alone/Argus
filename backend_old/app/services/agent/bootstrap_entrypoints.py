"""Fallback entrypoint discovery and seed building helpers."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent.bootstrap_seeds import MAX_SEED_FINDINGS, _to_int
from app.services.agent.scope_filters import (
    _build_core_audit_exclude_patterns,
    _is_core_ignored_path,
    _normalize_scan_path,
)

logger = logging.getLogger(__name__)


def _discover_entry_points_deterministic(
    project_root: str,
    target_files: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """在 OpenGrep 候选为空时，确定性发现入口点（grep-like + AST 兜底）。"""

    normalized_project_root = os.path.abspath(project_root)
    root = Path(normalized_project_root)
    effective_exclude_patterns = _build_core_audit_exclude_patterns(exclude_patterns)

    include_set = (
        {_normalize_scan_path(path) for path in target_files if isinstance(path, str)}
        if target_files
        else None
    )

    code_exts = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".go",
        ".php",
        ".rb",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }

    patterns: List[Tuple[str, re.Pattern[str]]] = [
        ("python_fastapi_route", re.compile(r"^\s*@(?:app|router)\.(get|post|put|delete|patch)\b", re.I)),
        ("python_flask_route", re.compile(r"^\s*@app\.route\b", re.I)),
        ("python_main", re.compile(r"__name__\s*==\s*[\"']__main__[\"']")),
        ("django_urlpatterns", re.compile(r"\burlpatterns\s*=")),
        ("express_route", re.compile(r"\b(app|router)\.(get|post|put|delete|patch)\s*\(", re.I)),
        ("node_listen", re.compile(r"\bapp\.listen\s*\(", re.I)),
        ("spring_mapping", re.compile(r"@\s*(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b")),
        ("spring_controller", re.compile(r"@\s*(RestController|Controller)\b")),
        ("go_http_handle", re.compile(r"\bhttp\.HandleFunc\s*\(", re.I)),
        ("laravel_route", re.compile(r"\bRoute::(get|post|put|delete|patch)\s*\(", re.I)),
    ]

    entry_points: List[Dict[str, Any]] = []
    entry_files: List[str] = []

    def consider_file(rel_path: str) -> bool:
        if include_set is not None and rel_path not in include_set:
            return False
        if _is_core_ignored_path(rel_path, effective_exclude_patterns):
            return False
        return True

    max_scan_files = 600
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = os.path.relpath(dirpath, project_root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_core_ignored_path(
                f"{rel_dir}/{d}" if rel_dir else d,
                effective_exclude_patterns,
            )
        ]
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext not in code_exts:
                continue
            abs_path = Path(dirpath) / name
            try:
                rel = abs_path.relative_to(root).as_posix()
            except Exception:
                continue
            if _is_core_ignored_path(rel, effective_exclude_patterns):
                continue
            if not consider_file(_normalize_scan_path(rel)):
                continue
            scanned += 1
            if scanned > max_scan_files:
                break
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                for typ, pat in patterns:
                    matched = pat.search(line)
                    if not matched:
                        continue
                    method = None
                    if matched.lastindex:
                        for gi in range(1, matched.lastindex + 1):
                            group = matched.group(gi)
                            if isinstance(group, str) and group.strip() and group.strip().lower() in {
                                "get",
                                "post",
                                "put",
                                "delete",
                                "patch",
                                "head",
                                "options",
                            }:
                                method = group.strip().lower()
                                break
                    entry_points.append(
                        {
                            "type": typ,
                            "file": rel,
                            "line": idx,
                            "method": method or "",
                            "evidence": stripped[:240],
                        }
                    )
                    if rel not in entry_files:
                        entry_files.append(rel)
                    if len(entry_points) >= 80:
                        break
                if len(entry_points) >= 80:
                    break
            if len(entry_points) >= 80:
                break
        if len(entry_points) >= 80 or scanned > max_scan_files:
            break

    entry_function_names: List[str] = []
    try:
        from app.services.agent.flow.lightweight.ast_index import ASTCallIndex

        ast_target_files = entry_files or (target_files or None)
        ast_index = ASTCallIndex(
            project_root=normalized_project_root,
            target_files=ast_target_files if isinstance(ast_target_files, list) else None,
        )
        inferred = ast_index.infer_entry_points()
        for sym in inferred or []:
            name = str(getattr(sym, "name", "")).strip()
            if name and name not in entry_function_names:
                entry_function_names.append(name)
            if len(entry_function_names) >= 80:
                break
    except Exception as exc:
        logger.debug("[EntryPoints] AST inference failed: %s", exc)

    return {
        "entry_points": entry_points,
        "entry_function_names": entry_function_names,
    }


async def _build_seed_from_entrypoints(
    project_root: str,
    target_vulns: Optional[List[str]],
    entry_function_names: List[str],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """基于入口点提示，使用 SmartScanTool 生成固定数量的 seed findings。"""
    from app.services.agent.tools import SmartScanTool

    severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    confidence_by_severity = {"critical": 0.9, "high": 0.8, "medium": 0.6, "low": 0.4, "info": 0.3}

    tool = SmartScanTool(project_root, exclude_patterns=exclude_patterns or [])
    result = await tool.execute(
        target=".",
        quick_mode=True,
        max_files=200,
        focus_vulnerabilities=target_vulns or None,
    )
    raw_findings = []
    if isinstance(result, object) and getattr(result, "success", False):
        metadata = getattr(result, "metadata", {}) or {}
        raw_findings = metadata.get("findings") if isinstance(metadata, dict) else []
    if not isinstance(raw_findings, list):
        raw_findings = []

    seeds: List[Dict[str, Any]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or "").strip()
        line_no = _to_int(item.get("line_number")) or 1
        vuln_type = str(item.get("vulnerability_type") or "potential_issue").strip() or "potential_issue"
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in severity_weight:
            severity = "medium"
        confidence = float(confidence_by_severity.get(severity, 0.5))

        matched_line = str(item.get("matched_line") or "").strip()
        context = str(item.get("context") or "").strip()
        code_snippet = matched_line or context

        title = f"{vuln_type} 可疑点（入口点回退扫描）"
        description = f"SmartScan 模式匹配：{item.get('pattern_name') or ''}".strip()
        if context:
            description = f"{description}\n上下文：\n{context}".strip()

        seeds.append(
            {
                "title": title,
                "description": description[:1200],
                "file_path": file_path,
                "line_start": int(line_no),
                "line_end": int(line_no),
                "code_snippet": str(code_snippet)[:2000],
                "severity": severity,
                "confidence": confidence,
                "vulnerability_type": vuln_type,
                "source": "fallback_entrypoints_smart_scan",
                "needs_verification": True,
                "entry_points": list(entry_function_names[:20]),
            }
        )

    seen: set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(
        key=lambda s: (
            -severity_weight.get(str(s.get("severity") or "medium").strip().lower(), 2),
            -float(s.get("confidence") or 0.0),
        )
    )
    return deduped[:MAX_SEED_FINDINGS]
