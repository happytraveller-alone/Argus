"""Finding normalization, enrichment, persistence, and serialization for agent tasks."""

import json
import logging
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.agent_task import AgentFinding, FindingStatus, VulnerabilitySeverity
from app.services.agent.utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
    build_cn_structured_title,
    infer_code_fence_language,
    normalize_cwe_id as normalize_cwe_id_util,
    resolve_cwe_id as resolve_cwe_id_util,
    resolve_vulnerability_profile as resolve_vulnerability_profile_util,
)

from .agent_tasks_bootstrap import _is_core_ignored_path
from .agent_tasks_contracts import AgentFindingResponse

logger = logging.getLogger(__name__)

def _safe_text(value: Any) -> str:
    """将任意结构安全转换为文本，避免保存时意外截断或类型错误。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _safe_text(value).strip()
    return text or None


def _normalize_relative_file_path(path_value: str, project_root: Optional[str]) -> str:
    normalized = path_value.replace("\\", "/").strip()
    if not normalized:
        return normalized
    if not project_root:
        if os.path.isabs(normalized):
            return os.path.basename(normalized)
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized
    try:
        rel = os.path.relpath(normalized, project_root)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except Exception:
        pass
    if os.path.isabs(normalized):
        return os.path.basename(normalized)
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


_ABS_PATH_IN_TEXT_RE = re.compile(r"(?P<path>(?:[A-Za-z]:[\\/]|/)[^\s:]+)")


def _sanitize_text_paths(value: Any, project_root: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return None
    normalized_text = text.replace("\\", "/")

    def _replace(match: re.Match[str]) -> str:
        matched_path = str(match.group("path") or "")
        if not matched_path:
            return match.group(0)
        return _normalize_relative_file_path(matched_path, project_root)

    return _ABS_PATH_IN_TEXT_RE.sub(_replace, normalized_text)


def _resolve_finding_file_path(
    raw_file_path: Optional[str],
    project_root: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    if not raw_file_path:
        return None, None

    candidate = raw_file_path.strip()
    candidate = re.sub(r":\d+(?:-\d+)?\s*$", "", candidate).strip()
    if not candidate:
        return None, None

    candidate = candidate.replace("\\", "/")
    path_candidates: List[Path] = []
    raw_path = Path(candidate)
    path_candidates.append(raw_path)

    if project_root:
        root_path = Path(project_root)
        path_candidates.append(root_path / candidate)
        if candidate.startswith("./"):
            path_candidates.append(root_path / candidate[2:])

    for path_obj in path_candidates:
        try:
            resolved = path_obj.resolve()
        except Exception:
            continue
        if resolved.is_file():
            stored = _normalize_relative_file_path(str(resolved), project_root)
            return stored, str(resolved)

    # Fallback: 尝试按后缀路径或 basename 在项目根目录中匹配，降低模型路径漂移导致的全量过滤
    if project_root:
        try:
            root_path = Path(project_root).resolve()
            normalized_candidate = candidate.lstrip("./")
            candidate_parts = [part for part in normalized_candidate.split("/") if part]

            # 1) 逐级裁剪前缀，按 suffix 尝试匹配
            for idx in range(len(candidate_parts)):
                suffix_candidate = root_path.joinpath(*candidate_parts[idx:])
                if suffix_candidate.is_file():
                    resolved = suffix_candidate.resolve()
                    stored = _normalize_relative_file_path(str(resolved), project_root)
                    return stored, str(resolved)

            # 2) basename 唯一匹配兜底（限制匹配数量避免大仓库扫描过慢）
            if candidate_parts:
                basename = candidate_parts[-1]
                matches: List[Path] = []
                for matched in root_path.rglob(basename):
                    if matched.is_file():
                        matches.append(matched)
                    if len(matches) > 8:
                        break

                if len(matches) == 1:
                    resolved = matches[0].resolve()
                    stored = _normalize_relative_file_path(str(resolved), project_root)
                    return stored, str(resolved)

                if len(matches) > 1:
                    suffix_text = "/".join(candidate_parts[-3:]) if len(candidate_parts) >= 3 else normalized_candidate
                    normalized_suffix = suffix_text.replace("\\", "/")
                    for matched in matches:
                        matched_posix = matched.as_posix()
                        if matched_posix.endswith(normalized_suffix):
                            resolved = matched.resolve()
                            stored = _normalize_relative_file_path(str(resolved), project_root)
                            return stored, str(resolved)
        except Exception:
            pass

    return None, None


def _infer_line_range_from_snippet(
    file_lines: List[str],
    snippet: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    if not snippet:
        return None, None

    snippet_text = snippet.strip("\n")
    if not snippet_text:
        return None, None

    file_text = "\n".join(file_lines)
    first_index = file_text.find(snippet_text)
    if first_index < 0:
        return None, None
    if file_text.find(snippet_text, first_index + 1) >= 0:
        return None, None

    line_start = file_text.count("\n", 0, first_index) + 1
    line_count = max(1, snippet_text.count("\n") + 1)
    line_end = line_start + line_count - 1
    return line_start, line_end


def _extract_location_parts(finding: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    location = finding.get("location")
    if not location or not isinstance(location, str):
        return None, None
    location = location.strip()
    if not location:
        return None, None

    if ":" not in location:
        return location, None

    file_part, line_part = location.split(":", 1)
    line_num = _to_int(line_part.split("-", 1)[0].strip())
    return file_part.strip(), line_num


def _build_code_windows(
    file_lines: List[str],
    line_start: int,
    line_end: int,
    radius: int = 3,
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int]]:
    if not file_lines:
        return None, None, None, None

    total_lines = len(file_lines)
    safe_start = max(1, min(line_start, total_lines))
    safe_end = max(safe_start, min(line_end, total_lines))

    snippet_start_idx = safe_start - 1
    snippet_end_idx = safe_end
    snippet = "\n".join(file_lines[snippet_start_idx:snippet_end_idx]).strip("\n")

    context_start = max(1, safe_start - radius)
    context_end = min(total_lines, safe_end + radius)
    context_start_idx = context_start - 1
    context_end_idx = context_end
    context = "\n".join(file_lines[context_start_idx:context_end_idx]).strip("\n")

    if not context:
        return None, None, None, None
    if not snippet:
        snippet = context

    return snippet, context, context_start, context_end


def _normalize_authenticity_verdict(
    finding: Dict[str, Any],
    confidence: float,
) -> Optional[str]:
    verdict = finding.get("authenticity") or finding.get("verdict")
    if isinstance(verdict, str):
        verdict = verdict.strip().lower()
    else:
        verdict = None

    allowed = {"confirmed", "likely", "uncertain", "false_positive"}
    if verdict in allowed:
        return verdict

    status_hint = str(finding.get("status") or "").strip().lower()
    if status_hint in {"false_positive", "false-positive", "not_vulnerable", "not_exists", "non_vuln"}:
        return "false_positive"
    if status_hint in {"uncertain", "unknown", "needs_review", "needs-review"}:
        return "uncertain"
    if status_hint in {"verified", "true_positive", "exists", "vulnerable", "confirmed", "likely"}:
        return "likely"

    source_value = str(finding.get("source") or "").lower()
    if source_value in {"verification", "verification_agent", "agent_verification"}:
        return "confirmed"
    if source_value in {"analysis", "analysis_agent", "recon_high_risk", "bootstrap"}:
        return "likely"
    if confidence >= 0.85:
        return "likely"
    if confidence <= 0.2:
        return "false_positive"
    return "uncertain"


def _normalize_verification_status(
    status_value: Any,
    verdict: Optional[str],
) -> str:
    text = str(status_value or "").strip().lower()
    if text in {"verified", "true_positive", "exists", "vulnerable"}:
        return FindingStatus.VERIFIED
    if text in {"false_positive", "false-positive", "not_vulnerable", "not_exists", "non_vuln"}:
        return FindingStatus.FALSE_POSITIVE
    if text in {"uncertain", "unknown", "needs_review", "needs-review"}:
        return FindingStatus.UNCERTAIN
    if text in {"confirmed", "likely"}:
        return FindingStatus.VERIFIED

    normalized_verdict = str(verdict or "").strip().lower()
    if normalized_verdict in {"confirmed", "likely"}:
        return FindingStatus.VERIFIED
    if normalized_verdict == "false_positive":
        return FindingStatus.FALSE_POSITIVE
    return FindingStatus.UNCERTAIN


def _normalize_reachability(
    finding: Dict[str, Any],
    verdict: str,
) -> Optional[str]:
    value = finding.get("reachability")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"reachable", "likely_reachable", "unreachable"}:
            return normalized

    if verdict == "confirmed":
        return "reachable"
    if verdict == "likely":
        return "likely_reachable"
    if verdict == "uncertain":
        return "unknown"
    if verdict == "false_positive":
        return "unreachable"
    return "unknown"


def _normalize_cwe_id(value: Any) -> Optional[str]:
    return normalize_cwe_id_util(value)


def _extract_cwe_from_references(references: Any) -> Optional[str]:
    if references is None:
        return None
    if isinstance(references, list):
        for item in references:
            normalized = _normalize_cwe_id(item)
            if normalized:
                return normalized
        return None
    return _normalize_cwe_id(references)


def _resolve_vulnerability_profile(
    vulnerability_type: Optional[str],
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> Dict[str, str]:
    return resolve_vulnerability_profile_util(
        vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _resolve_cwe_id(
    explicit_cwe: Any,
    vulnerability_type: Optional[str],
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> Optional[str]:
    return resolve_cwe_id_util(
        explicit_cwe,
        vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _build_structured_cn_description(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
    cwe_id: Optional[str],
    raw_description: Optional[str],
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    verification_evidence: Optional[str] = None,
    function_trigger_flow: Optional[List[str]] = None,
    code_context: Optional[str] = None,
) -> str:
    return build_cn_structured_description(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
        cwe_id=cwe_id,
        raw_description=raw_description,
        line_start=line_start,
        line_end=line_end,
        verification_evidence=verification_evidence,
        function_trigger_flow=function_trigger_flow,
        code_context=code_context,
    )


def _build_structured_cn_description_markdown(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
    code_context: Optional[str],
    cwe_id: Optional[str],
    raw_description: Optional[str],
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    verification_evidence: Optional[str] = None,
    function_trigger_flow: Optional[List[str]] = None,
) -> str:
    return build_cn_structured_description_markdown(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
        code_context=code_context,
        cwe_id=cwe_id,
        raw_description=raw_description,
        line_start=line_start,
        line_end=line_end,
        verification_evidence=verification_evidence,
        function_trigger_flow=function_trigger_flow,
    )


def _build_structured_cn_display_title(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
) -> str:
    return build_cn_structured_title(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _extract_flow_call_chain(
    verification_payload: Dict[str, Any],
    dataflow_path: Optional[List[str]],
) -> List[str]:
    if isinstance(verification_payload, dict):
        flow_payload = verification_payload.get("flow")
        if isinstance(flow_payload, dict):
            raw_chain = flow_payload.get("call_chain")
            if isinstance(raw_chain, list):
                chain = [str(item).strip() for item in raw_chain if str(item).strip()]
                if chain:
                    return chain
    if isinstance(dataflow_path, list):
        chain = [str(item).strip() for item in dataflow_path if str(item).strip()]
        if chain:
            return chain
    return []


def _build_function_trigger_flow(
    *,
    call_chain: List[str],
    function_name: Optional[str],
    file_path: Optional[str],
    line_start: Optional[int],
    line_end: Optional[int],
) -> List[str]:
    filtered: List[str] = []
    if call_chain:
        if function_name:
            needle = function_name.lower()
            hit_index = -1
            for idx, step in enumerate(call_chain):
                if needle and needle in step.lower():
                    hit_index = idx
                    break
            if hit_index >= 0:
                filtered = call_chain[: hit_index + 1]
            else:
                filtered = call_chain[: min(3, len(call_chain))]
        else:
            filtered = call_chain[: min(3, len(call_chain))]

    location_text = file_path or "未知路径"
    if line_start is not None:
        if line_end is not None and line_end != line_start:
            location_text = f"{location_text}:{line_start}-{line_end}"
        else:
            location_text = f"{location_text}:{line_start}"

    terminal = (
        f"命中函数：{function_name}（{location_text}）"
        if function_name
        else f"命中位置：{location_text}"
    )
    if not filtered or filtered[-1] != terminal:
        filtered.append(terminal)
    return filtered


def _build_default_remediation(vuln_type: str) -> Tuple[str, str]:
    normalized = (vuln_type or "").lower()
    mapping: Dict[str, Tuple[str, str]] = {
        "sql_injection": (
            "使用参数化查询并对输入进行严格校验，避免字符串拼接 SQL。",
            'query = "SELECT * FROM users WHERE id = %s"\ncursor.execute(query, (user_id,))',
        ),
        "xss": (
            "对输出到页面的用户输入进行转义或使用安全模板 API。",
            "safe_output = html.escape(user_input)\nrender(safe_output)",
        ),
        "command_injection": (
            "禁止将用户输入直接拼接命令；改用白名单参数与安全 API。",
            "subprocess.run([\"cmd\", safe_arg], check=True)",
        ),
        "path_traversal": (
            "规范化并校验路径，限制访问在允许目录内。",
            "resolved = (base_dir / user_path).resolve()\nif not str(resolved).startswith(str(base_dir.resolve())):\n    raise ValueError(\"invalid path\")",
        ),
        "ssrf": (
            "对目标地址做白名单校验并阻断内网地址访问。",
            "if not is_allowed_url(target_url):\n    raise ValueError(\"blocked url\")",
        ),
    }
    if normalized in mapping:
        return mapping[normalized]
    return (
        "补充输入校验与边界检查，移除危险调用并增加安全防护。",
        "// TODO: apply secure validation and safe API usage here",
    )


async def _enrich_findings_with_flow_and_logic(
    findings: List[Dict[str, Any]],
    *,
    project_root: Optional[str],
    target_files: Optional[List[str]],
    llm_service: Optional[Any] = None,
    event_emitter: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """三轨流分析增强（Smart Audit 已禁用）。

    Smart audit policy disables the whole "flow enrichment / evidence generation" stage:
    - do not auto-run flow enrichment at the end of the audit
    - do not auto-generate trigger_flow / poc_trigger_chain evidence

    This function is kept as a stable API surface for backward compatibility, but always
    returns the input findings unchanged with a disabled summary.
    """
    _ = (project_root, target_files, llm_service, event_emitter)  # keep signature stable
    summary: Dict[str, Any] = {
        "total": len(findings or []),
        "enabled": False,
        "blocked_reason": "disabled_by_policy",
    }
    return findings, summary


async def _save_findings(
    db: AsyncSession,
    task_id: str,
    findings: List[Dict],
    project_root: Optional[str] = None,
    save_diagnostics: Optional[Dict[str, Any]] = None,
    _retry_on_conflict: bool = True,
) -> int:
    """
    保存发现到数据库

    严格门禁版：
    - normalize -> enrich -> validate -> persist
    - 无文件定位、无可用上下文、无合法真实性/可达性的发现不入库

    Args:
        db: 数据库会话
        task_id: 任务ID
        findings: 发现列表
        project_root: 项目根目录（用于验证文件路径）

    Returns:
        int: 实际保存的发现数量
    """
    from app.models.agent_task import VulnerabilityType
    from app.services.agent.tools.verification_result_tools import ensure_finding_identity

    logger.info(f"[SaveFindings] Starting to save {len(findings)} findings for task {task_id}")

    if not findings:
        logger.warning(f"[SaveFindings] No findings to save for task {task_id}")
        return 0

    #  Case-insensitive mapping preparation
    severity_map = {
        "critical": VulnerabilitySeverity.CRITICAL,
        "high": VulnerabilitySeverity.HIGH,
        "medium": VulnerabilitySeverity.MEDIUM,
        "low": VulnerabilitySeverity.LOW,
        "info": VulnerabilitySeverity.INFO,
    }

    type_map = {
        "sql_injection": VulnerabilityType.SQL_INJECTION,
        "nosql_injection": VulnerabilityType.NOSQL_INJECTION,
        "xss": VulnerabilityType.XSS,
        "command_injection": VulnerabilityType.COMMAND_INJECTION,
        "code_injection": VulnerabilityType.CODE_INJECTION,
        "path_traversal": VulnerabilityType.PATH_TRAVERSAL,
        "ssrf": VulnerabilityType.SSRF,
        "xxe": VulnerabilityType.XXE,
        "auth_bypass": VulnerabilityType.AUTH_BYPASS,
        "idor": VulnerabilityType.IDOR,
        "sensitive_data_exposure": VulnerabilityType.SENSITIVE_DATA_EXPOSURE,
        "hardcoded_secret": VulnerabilityType.HARDCODED_SECRET,
        "deserialization": VulnerabilityType.DESERIALIZATION,
        "weak_crypto": VulnerabilityType.WEAK_CRYPTO,
        "file_inclusion": VulnerabilityType.FILE_INCLUSION,
        "race_condition": VulnerabilityType.RACE_CONDITION,
        "business_logic": VulnerabilityType.BUSINESS_LOGIC,
        "memory_corruption": VulnerabilityType.MEMORY_CORRUPTION,
    }

    saved_count = 0
    filtered_reasons: Dict[str, int] = {}
    logger.info(f"Saving {len(findings)} findings for task {task_id}")

    function_locator = None
    if project_root:
        try:
            from app.services.agent.flow.lightweight.function_locator import EnclosingFunctionLocator

            function_locator = EnclosingFunctionLocator(project_root=project_root)
        except Exception as exc:
            logger.warning("[SaveFindings] Function locator init failed: %s", exc)
            function_locator = None

    def mark_filtered(reason: str, payload: Optional[Dict[str, Any]] = None) -> None:
        filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1
        if payload:
            logger.warning(
                f"[SaveFindings] 🚫 Filtered finding ({reason}): "
                f"title={str(payload.get('title', 'N/A'))[:80]}"
            )

    def _infer_function_name_for_save(payload: Dict[str, Any], normalized_line_start: Optional[int]) -> str:
        direct_name = str(payload.get("function_name") or "").strip()
        if direct_name:
            return direct_name

        title_text = str(payload.get("title") or "").strip()
        if title_text:
            patterns = [
                r"中([A-Za-z_][A-Za-z0-9_]*)函数",
                r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            ]
            for pattern in patterns:
                matched = re.search(pattern, title_text)
                if matched:
                    candidate = str(matched.group(1) or "").strip()
                    if candidate:
                        return candidate

        verification_payload = payload.get("verification_result")
        if isinstance(verification_payload, dict):
            target_payload = verification_payload.get("reachability_target")
            if isinstance(target_payload, dict):
                candidate = str(target_payload.get("function") or "").strip()
                if candidate:
                    return candidate

        if normalized_line_start is not None:
            return f"<function_at_line_{normalized_line_start}>"
        return "<function_not_localized>"

    def _merge_finding_metadata_payload(
        existing_payload: Optional[Dict[str, Any]],
        incoming_payload: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        merged = dict(existing_payload or {})
        incoming = dict(incoming_payload or {})
        if not incoming:
            return merged or None

        for key, value in incoming.items():
            if key == "extra_tool_input":
                merged_extra = dict(merged.get("extra_tool_input") or {})
                incoming_extra = dict(value or {}) if isinstance(value, dict) else {}
                merged_extra.update(incoming_extra)
                if merged_extra:
                    merged["extra_tool_input"] = merged_extra
                continue
            merged[key] = value
        return merged or None

    for finding in findings:
        if not isinstance(finding, dict):
            logger.debug(f"[SaveFindings] Skipping non-dict finding: {type(finding)}")
            continue

        try:
            finding_identity = ensure_finding_identity(task_id, finding)
            # 1) normalize severity
            raw_severity = str(
                finding.get("severity") or
                finding.get("risk") or
                "medium"
            ).lower().strip()
            severity_enum = severity_map.get(raw_severity, VulnerabilitySeverity.MEDIUM)

            # 2) normalize vulnerability type
            raw_type = str(
                finding.get("vulnerability_type") or
                finding.get("type") or
                finding.get("vuln_type") or
                "other"
            ).lower().strip().replace(" ", "_").replace("-", "_")
            type_profile = resolve_vulnerability_profile_util(
                raw_type,
                title=str(finding.get("title") or ""),
                description=str(finding.get("description") or ""),
                code_snippet=str(finding.get("code_snippet") or ""),
            )
            raw_type = str(type_profile.get("key") or raw_type)

            type_enum = type_map.get(raw_type, VulnerabilityType.OTHER)

            #  Additional fallback for common Agent output variations
            if "sqli" in raw_type or "sql" in raw_type:
                type_enum = VulnerabilityType.SQL_INJECTION
            if "xss" in raw_type:
                type_enum = VulnerabilityType.XSS
            if "rce" in raw_type or "command" in raw_type or "cmd" in raw_type:
                type_enum = VulnerabilityType.COMMAND_INJECTION
            if "traversal" in raw_type or "lfi" in raw_type or "rfi" in raw_type:
                type_enum = VulnerabilityType.PATH_TRAVERSAL
            if "ssrf" in raw_type:
                type_enum = VulnerabilityType.SSRF
            if "xxe" in raw_type:
                type_enum = VulnerabilityType.XXE
            if "auth" in raw_type:
                type_enum = VulnerabilityType.AUTH_BYPASS
            if "secret" in raw_type or "credential" in raw_type or "password" in raw_type:
                type_enum = VulnerabilityType.HARDCODED_SECRET
            if "deserial" in raw_type:
                type_enum = VulnerabilityType.DESERIALIZATION
            if raw_type in {
                "buffer_overflow",
                "stack_overflow",
                "heap_overflow",
                "use_after_free",
                "double_free",
                "out_of_bounds",
                "integer_overflow",
                "format_string",
                "null_pointer_deref",
            }:
                type_enum = VulnerabilityType.MEMORY_CORRUPTION

            # 3) normalize confidence
            confidence = finding.get("confidence") or finding.get("ai_confidence") or 0.5
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except ValueError:
                    confidence = 0.5
            confidence = max(0.0, min(float(confidence), 1.0))

            verification_result_payload_input = finding.get("verification_result")
            if not isinstance(verification_result_payload_input, dict):
                verification_result_payload_input = {}

            # 4) verification compatibility gate (allow synthesis from top-level)
            authenticity_raw = (
                finding.get("authenticity")
                or finding.get("verdict")
                or verification_result_payload_input.get("authenticity")
                or verification_result_payload_input.get("verdict")
            )
            authenticity = _normalize_optional_text(authenticity_raw)
            authenticity = authenticity.lower() if authenticity else None
            if authenticity not in {"confirmed", "likely", "uncertain", "false_positive"}:
                status_hint_raw = (
                    finding.get("status")
                    or verification_result_payload_input.get("status")
                )
                status_hint = str(status_hint_raw or "").strip().lower()
                if status_hint in {"verified", "true_positive", "exists", "vulnerable", "confirmed", "likely"}:
                    authenticity = "likely"
                elif status_hint in {"false_positive", "false-positive", "not_vulnerable", "not_exists", "non_vuln"}:
                    authenticity = "false_positive"
                elif status_hint in {"uncertain", "unknown", "needs_review", "needs-review"}:
                    authenticity = "uncertain"
            if authenticity not in {"confirmed", "likely", "uncertain", "false_positive"}:
                authenticity = _normalize_authenticity_verdict(finding, confidence)
            if authenticity not in {"confirmed", "likely", "uncertain", "false_positive"}:
                mark_filtered("missing_verification_result", finding)
                continue

            status_raw = (
                finding.get("status")
                or verification_result_payload_input.get("status")
            )
            normalized_status = _normalize_verification_status(status_raw, authenticity)
            if normalized_status == FindingStatus.FALSE_POSITIVE and authenticity in {"confirmed", "likely"}:
                authenticity = "false_positive"
            elif normalized_status == FindingStatus.VERIFIED and authenticity == "false_positive":
                authenticity = "likely"
            elif normalized_status == FindingStatus.UNCERTAIN and authenticity in {"confirmed", "likely", "false_positive"}:
                authenticity = "uncertain"

            verification_stage_completed = bool(
                finding.get("verification_stage_completed")
                or verification_result_payload_input.get("verification_stage_completed")
            )
            if not verification_stage_completed and isinstance(status_raw, str) and status_raw.strip():
                verification_stage_completed = True
            if not verification_stage_completed:
                source_value = str(finding.get("source") or "").strip().lower()
                if source_value in {"verification", "verification_agent", "agent_verification"}:
                    verification_stage_completed = True

            reachability_raw = (
                finding.get("reachability")
                or verification_result_payload_input.get("reachability")
            )
            reachability = _normalize_optional_text(reachability_raw)
            reachability = reachability.lower() if reachability else None
            if reachability not in {"reachable", "likely_reachable", "unknown", "unreachable"}:
                reachability = _normalize_reachability(finding, authenticity)
            if reachability not in {"reachable", "likely_reachable", "unknown", "unreachable"}:
                mark_filtered("missing_verification_result", finding)
                continue

            evidence_raw = (
                finding.get("verification_details")
                or finding.get("verification_evidence")
                or verification_result_payload_input.get("verification_details")
                or verification_result_payload_input.get("verification_evidence")
                or verification_result_payload_input.get("evidence")
                or finding.get("description")
                or finding.get("reason")
            )
            verification_details_text = _normalize_optional_text(evidence_raw)
            if not verification_details_text:
                verification_details_text = (
                    "verification_result auto synthesized during persistence; "
                    f"verdict={authenticity}; confidence={confidence:.2f}"
                )

            if authenticity == "false_positive":
                logger.debug(
                    f"[SaveFindings] Finding with false_positive verdict will be marked separately: {str(finding.get('title'))[:60]}"
                )

            verification_result_payload_input = {
                **verification_result_payload_input,
                "authenticity": authenticity,
                "verdict": authenticity,
                "status": normalized_status,
                "confidence": confidence,
                "reachability": reachability,
                "verification_stage_completed": verification_stage_completed,
                "verification_evidence": verification_details_text,
            }
            verification_todo_id = _normalize_optional_text(
                finding.get("verification_todo_id")
                or verification_result_payload_input.get("verification_todo_id")
            )
            verification_fingerprint = _normalize_optional_text(
                finding.get("verification_fingerprint")
                or verification_result_payload_input.get("verification_fingerprint")
            )
            if authenticity == "false_positive" and not verification_fingerprint:
                fingerprint_basis = "|".join(
                    [
                        str(task_id or "").strip(),
                        _normalize_optional_text(finding.get("title")) or "",
                        _normalize_optional_text(finding.get("vulnerability_type")) or "",
                        _normalize_optional_text(finding.get("description")) or "",
                        _normalize_optional_text(finding.get("file_path")) or "",
                        str(_to_int(finding.get("line_start")) or ""),
                        str(_to_int(finding.get("line_end")) or ""),
                        _normalize_optional_text(finding.get("code_snippet")) or "",
                        verification_details_text,
                    ]
                )
                verification_fingerprint = (
                    f"fp:{str(task_id or '').strip()}:{uuid5(NAMESPACE_URL, fingerprint_basis)}"
                )
            if verification_todo_id:
                verification_result_payload_input["verification_todo_id"] = verification_todo_id
            if verification_fingerprint:
                verification_result_payload_input["verification_fingerprint"] = verification_fingerprint

            # 5) normalize file location
            location_file, location_line = _extract_location_parts(finding)
            raw_file_path = finding.get("file_path") or finding.get("file") or location_file
            # 7) normalize snippets
            code_snippet = (
                finding.get("code_snippet") or
                finding.get("code") or
                finding.get("vulnerable_code")
            )
            code_snippet_text = _normalize_optional_text(code_snippet)
            line_start = _to_int(finding.get("line_start")) or _to_int(finding.get("line")) or location_line
            line_end = _to_int(finding.get("line_end"))
            stored_file_path = None
            full_file_path = None
            file_lines: List[str] = []
            snippet_text = code_snippet_text
            context_text = None
            context_start_line = None
            context_end_line = None

            if authenticity == "false_positive":
                if raw_file_path:
                    stored_file_path = _normalize_relative_file_path(
                        str(raw_file_path),
                        project_root,
                    )
                if line_end is None and line_start is not None:
                    line_end = line_start
            else:
                stored_file_path, full_file_path = _resolve_finding_file_path(
                    str(raw_file_path) if raw_file_path else None,
                    project_root,
                )
                if not stored_file_path or not full_file_path:
                    mark_filtered("missing_or_invalid_file_path", finding)
                    continue
                if _is_core_ignored_path(stored_file_path):
                    mark_filtered("ignored_scope_path", finding)
                    continue

                try:
                    file_content = Path(full_file_path).read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except Exception:
                    mark_filtered("file_read_failed", finding)
                    continue

                file_lines = file_content.splitlines()
                if not file_lines:
                    mark_filtered("empty_file_content", finding)
                    continue

                if line_start is None:
                    inferred_start, inferred_end = _infer_line_range_from_snippet(
                        file_lines,
                        code_snippet_text,
                    )
                    line_start = inferred_start
                    if inferred_end is not None:
                        line_end = inferred_end

                if line_start is None:
                    mark_filtered("missing_line_start", finding)
                    continue
                if line_end is None:
                    line_end = line_start

                total_lines = len(file_lines)
                line_start = max(1, min(line_start, total_lines))
                line_end = max(line_start, min(line_end, total_lines))

                snippet_text, context_text, context_start_line, context_end_line = _build_code_windows(
                    file_lines=file_lines,
                    line_start=line_start,
                    line_end=line_end,
                    radius=12,
                )
                if not context_text or context_start_line is None or context_end_line is None:
                    mark_filtered("missing_code_context", finding)
                    continue
                if not snippet_text:
                    snippet_text = code_snippet_text
                if not snippet_text:
                    snippet_text = "\n".join(file_lines[line_start - 1 : line_end]).strip()

            # 7.5) 获取函数定位信息，但允许定位失败时仍然保存（降级模式）
            reachability_target_function = _infer_function_name_for_save(finding, line_start)
            reachability_target_start_line = None
            reachability_target_end_line = None
            locator_language = None
            locator_resolution_engine = None
            locator_diagnostics = None
            locator_resolution_method = None
            localization_status = "unknown"  # success|failed|partial

            if function_locator and full_file_path and line_start is not None and file_lines:
                try:
                    located = function_locator.locate(
                        full_file_path=full_file_path,
                        line_start=line_start,
                        relative_file_path=stored_file_path,
                        file_lines=file_lines,
                    )
                    func_name = located.get("function")
                    if isinstance(func_name, str) and func_name.strip():
                        reachability_target_function = func_name.strip()
                        reachability_target_start_line = _to_int(located.get("start_line"))
                        reachability_target_end_line = _to_int(located.get("end_line"))
                        localization_status = "success"
                    else:
                        localization_status = "failed"
                    locator_language = located.get("language")
                    locator_resolution_engine = located.get("resolution_engine")
                    locator_resolution_method = located.get("resolution_method")
                    locator_diagnostics = located.get("diagnostics")
                except Exception as loc_exc:
                    logger.debug(f"[SaveFindings] Function locator error: {loc_exc}")
                    localization_status = "failed"

            if (
                authenticity != "false_positive"
                and function_locator
                and full_file_path
                and line_start is not None
                and file_lines
                and localization_status == "failed"
            ):
                # 定位失败不再作为硬过滤条件：保留发现并记录降级状态，避免有效漏洞被误丢弃
                mark_filtered("missing_enclosing_function")
                localization_status = "partial"
            
            # 降级策略：函数定位失败时仍允许保存，且确保 function_name 始终非空
            if not reachability_target_function:
                reachability_target_function = _infer_function_name_for_save(finding, line_start)
                logger.debug(
                    f"[SaveFindings] Fallback function_name for {stored_file_path}:{line_start} -> "
                    f"{reachability_target_function} (localization_status={localization_status})"
                )

            # 8) title/description/suggestion
            title = finding.get("title")
            if not title:
                type_display = raw_type.replace("_", " ").title()
                if stored_file_path:
                    title = f"{type_display} in {os.path.basename(stored_file_path)}"
                else:
                    title = f"{type_display} Vulnerability"
            title_text = str(title).strip() if title is not None else "Unknown Vulnerability"
            if not title_text:
                title_text = "Unknown Vulnerability"

            description = (
                finding.get("description") or
                finding.get("details") or
                finding.get("explanation") or
                finding.get("impact") or
                ""
            )
            description_text = _safe_text(description)

            suggestion = (
                finding.get("suggestion") or
                finding.get("recommendation") or
                finding.get("remediation") or
                finding.get("fix")
            )
            suggestion_text = _safe_text(suggestion) if suggestion is not None else None
            fix_code_text = _normalize_optional_text(
                finding.get("fix_code")
                or finding.get("patch")
                or finding.get("patch_snippet")
            )
            fix_description_text = _normalize_optional_text(
                finding.get("fix_description")
                or finding.get("fix_explanation")
                or finding.get("remediation_details")
            )
            report_text = _normalize_optional_text(
                finding.get("vulnerability_report")
                or finding.get("report")
            )

            if not suggestion_text or not fix_code_text:
                default_suggestion, default_fix_code = _build_default_remediation(raw_type)
                if not suggestion_text:
                    suggestion_text = default_suggestion
                if not fix_code_text:
                    fix_code_text = default_fix_code
                if not fix_description_text:
                    fix_description_text = "基于漏洞类型自动补全修复建议，请结合业务逻辑复核。"

            # 9) verification metadata
            is_verified = verification_stage_completed
            verification_method_text = _normalize_optional_text(finding.get("verification_method"))
            if not verification_method_text:
                verification_method_text = "agent_verification"

            # 获取或构建新的规范化字段：verdict、confidence、reachability
            verdict_value = authenticity  # confirmed|likely|uncertain|false_positive
            confidence_value = confidence  # 已在第3步规范化
            reachability_value = reachability  # reachable|likely_reachable|unknown|unreachable

            verification_result_payload = dict(verification_result_payload_input)
            if finding_identity:
                verification_result_payload["finding_identity"] = finding_identity
            verification_result_payload["status"] = normalized_status
            verification_result_payload["verification_stage_completed"] = verification_stage_completed
            existing_reachability_target = (
                verification_result_payload_input.get("reachability_target")
                if isinstance(verification_result_payload_input, dict)
                else None
            )
            if not isinstance(existing_reachability_target, dict):
                existing_reachability_target = {}
            # status 映射：由 LLM/status 输入表达漏洞是否存在，程序只负责规范化
            if normalized_status == FindingStatus.FALSE_POSITIVE:
                db_status = FindingStatus.FALSE_POSITIVE
            elif normalized_status == FindingStatus.UNCERTAIN:
                db_status = FindingStatus.UNCERTAIN
            else:
                db_status = FindingStatus.VERIFIED
            
            # verification_result_payload 中添加新字段
            existing_reachability_target = (
                verification_result_payload_input.get("reachability_target")
                if isinstance(verification_result_payload_input, dict)
                else None
            )
            if not isinstance(existing_reachability_target, dict):
                existing_reachability_target = {}

            # 9.5) Smart audit policy: do not require trigger_flow evidence as a persistence gate.

            dataflow_path = finding.get("dataflow_path")
            if not isinstance(dataflow_path, list):
                flow_payload = verification_result_payload.get("flow")
                if isinstance(flow_payload, dict):
                    chain = flow_payload.get("call_chain")
                    if isinstance(chain, list):
                        dataflow_path = [str(item) for item in chain if str(item).strip()]
            if not isinstance(dataflow_path, list):
                dataflow_path = None
            flow_chain = _extract_flow_call_chain(
                verification_payload=verification_result_payload,
                dataflow_path=dataflow_path,
            )
            function_trigger_flow = _build_function_trigger_flow(
                call_chain=flow_chain,
                function_name=reachability_target_function,
                file_path=stored_file_path,
                line_start=line_start,
                line_end=line_end,
            )
            verification_result_payload["function_trigger_flow"] = function_trigger_flow
            dataflow_path = function_trigger_flow if function_trigger_flow else dataflow_path
            source_text = _normalize_optional_text(finding.get("source"))
            sink_text = _normalize_optional_text(finding.get("sink"))
            raw_finding_metadata = finding.get("finding_metadata")
            finding_metadata_payload: Dict[str, Any] = (
                dict(raw_finding_metadata) if isinstance(raw_finding_metadata, dict) else {}
            )
            if verification_todo_id:
                finding_metadata_payload["verification_todo_id"] = verification_todo_id
            if verification_fingerprint:
                finding_metadata_payload["verification_fingerprint"] = verification_fingerprint
            if finding_identity:
                finding_metadata_payload["finding_identity"] = finding_identity
            finding_metadata_payload["verification_stage_completed"] = verification_stage_completed
            if raw_file_path:
                finding_metadata_payload["raw_file_path"] = _normalize_relative_file_path(
                    str(raw_file_path),
                    project_root,
                )
            if line_start is not None:
                finding_metadata_payload["raw_line_start"] = line_start
            if line_end is not None:
                finding_metadata_payload["raw_line_end"] = line_end
            attacker_flow_text = _normalize_optional_text(finding.get("attacker_flow"))
            if attacker_flow_text:
                finding_metadata_payload["attacker_flow"] = attacker_flow_text
            for list_key in ("evidence_chain", "missing_checks", "taint_flow"):
                raw_list = finding.get(list_key)
                if isinstance(raw_list, list):
                    normalized_list = [
                        str(item).strip()
                        for item in raw_list
                        if str(item).strip()
                    ]
                    if normalized_list:
                        finding_metadata_payload[list_key] = normalized_list

            # 10) PoC info
            poc_data = finding.get("poc", {})
            has_poc = bool(poc_data)
            poc_code = None
            poc_description = None
            poc_steps = None

            if isinstance(poc_data, dict):
                poc_description = poc_data.get("description")
                poc_steps = poc_data.get("steps")
                poc_code = poc_data.get("payload") or poc_data.get("code")
            elif isinstance(poc_data, str):
                poc_description = poc_data

            allow_poc = authenticity == "confirmed" and str(severity_enum).lower() in {"critical", "high"}
            if not allow_poc:
                has_poc = False
                poc_code = None
                poc_description = None
                poc_steps = None

    # 11) optional CVSS/CWE
            cwe_id = _resolve_cwe_id(
                finding.get("cwe_id") or finding.get("cwe"),
                raw_type,
                title=title_text,
                description=description_text,
                code_snippet=snippet_text,
            )
            cvss_score = finding.get("cvss_score") or finding.get("cvss")
            if isinstance(cvss_score, str):
                try:
                    cvss_score = float(cvss_score)
                except ValueError:
                    cvss_score = None
            cvss_vector = _normalize_optional_text(finding.get("cvss_vector"))

            # 12) Deduplication and Persistence
            # Logic: If a finding with same fingerprint exists for this task, update it.
            # fingerprint components: type, file_path, line_start, function_name, code_snippet(prefix)
            temp_finding = AgentFinding(
                vulnerability_type=type_enum,
                file_path=stored_file_path,
                line_start=line_start,
                function_name=reachability_target_function,
                code_snippet=snippet_text,
            )
            fingerprint = (
                verification_fingerprint
                if authenticity == "false_positive" and verification_fingerprint
                else temp_finding.generate_fingerprint()
            )

            # Find existing finding in current task
            existing_finding_stmt = select(AgentFinding).where(
                AgentFinding.task_id == task_id,
                AgentFinding.finding_identity == finding_identity,
            )
            existing_finding_result = await db.execute(existing_finding_stmt)
            db_finding = existing_finding_result.scalar_one_or_none()
            if db_finding is None:
                existing_finding_stmt = select(AgentFinding).where(
                    AgentFinding.task_id == task_id,
                    AgentFinding.fingerprint == fingerprint
                )
                existing_finding_result = await db.execute(existing_finding_stmt)
                db_finding = existing_finding_result.scalar_one_or_none()

            if db_finding:
                logger.info(f"[SaveFindings] Updating existing finding {db_finding.id} (fingerprint: {fingerprint})")
                # Update fields
                db_finding.severity = severity_enum
                db_finding.title = title_text
                db_finding.description = description_text
                db_finding.file_path = stored_file_path
                db_finding.line_start = line_start
                db_finding.line_end = line_end
                db_finding.code_snippet = snippet_text
                db_finding.code_context = context_text
                db_finding.function_name = reachability_target_function
                db_finding.source = source_text
                db_finding.sink = sink_text
                db_finding.dataflow_path = dataflow_path
                db_finding.suggestion = suggestion_text
                db_finding.fix_code = fix_code_text
                db_finding.fix_description = fix_description_text
                if report_text is not None:
                    db_finding.report = report_text
                db_finding.is_verified = is_verified
                db_finding.ai_confidence = confidence
                db_finding.status = db_status
                db_finding.verdict = verdict_value  # 新增：确实的 verdict
                db_finding.confidence = confidence_value  # 新增：规范化的置信度
                db_finding.reachability = reachability_value  # 新增：规范化的可达性
                db_finding.verification_evidence = verification_details_text  # 新增：验证证据
                db_finding.has_poc = has_poc
                db_finding.poc_code = poc_code
                db_finding.poc_description = poc_description
                db_finding.poc_steps = poc_steps
                db_finding.verification_method = verification_method_text
                db_finding.verification_result = verification_result_payload
                db_finding.finding_metadata = _merge_finding_metadata_payload(
                    db_finding.finding_metadata if isinstance(db_finding.finding_metadata, dict) else None,
                    finding_metadata_payload or None,
                )
                db_finding.finding_identity = finding_identity
                db_finding.cvss_score = cvss_score
                db_finding.cvss_vector = cvss_vector
                db_finding.references = [{"cwe": cwe_id}] if cwe_id else None
                db_finding.fingerprint = fingerprint
                db_finding.updated_at = func.now()
            else:
                db_finding = AgentFinding(
                    id=str(uuid4()),
                    task_id=task_id,
                    vulnerability_type=type_enum,
                    severity=severity_enum,
                    title=title_text,
                    description=description_text,
                    file_path=stored_file_path,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=snippet_text,
                    code_context=context_text,
                    function_name=reachability_target_function,
                    source=source_text,
                    sink=sink_text,
                    dataflow_path=dataflow_path,
                    suggestion=suggestion_text,
                    fix_code=fix_code_text,
                    fix_description=fix_description_text,
                    report=report_text,
                    is_verified=is_verified,
                    ai_confidence=confidence,
                    status=db_status,
                    verdict=verdict_value,  # 新增：确实的 verdict
                    confidence=confidence_value,  # 新增：规范化的置信度
                    reachability=reachability_value,  # 新增：规范化的可达性
                    verification_evidence=verification_details_text,  # 新增：验证证据
                    has_poc=has_poc,
                    poc_code=poc_code,
                    poc_description=poc_description,
                    poc_steps=poc_steps,
                    verification_method=verification_method_text,
                    verification_result=verification_result_payload,
                    finding_metadata=finding_metadata_payload or None,
                    finding_identity=finding_identity,
                    cvss_score=cvss_score,
                    cvss_vector=cvss_vector,
                    references=[{"cwe": cwe_id}] if cwe_id else None,
                    fingerprint=fingerprint,
                )
                db.add(db_finding)
            
            saved_count += 1
            logger.debug(f"[SaveFindings] Prepared finding: {title_text[:50]}... ({severity_enum})")

        except Exception as e:
            logger.warning(f"Failed to save finding: {e}, data: {finding}")
            import traceback
            logger.debug(f"[SaveFindings] Traceback: {traceback.format_exc()}")

    logger.info(f"Successfully prepared {saved_count} findings for commit")
    if filtered_reasons:
        logger.info(
            "[SaveFindings] Filter summary for task %s: %s",
            task_id,
            json.dumps(filtered_reasons, ensure_ascii=False),
        )
    if isinstance(save_diagnostics, dict):
        save_diagnostics.clear()
        save_diagnostics.update(
            {
                "input_count": len(findings),
                "saved_count": saved_count,
                "filtered_count": sum(filtered_reasons.values()),
                "filtered_reasons": dict(filtered_reasons),
            }
        )

    try:
        await db.commit()
        logger.info(f"[SaveFindings] Successfully committed {saved_count} findings to database")
    except IntegrityError as e:
        logger.warning(
            "[SaveFindings] Integrity conflict on commit for task %s: %s",
            task_id,
            e,
        )
        await db.rollback()
        if _retry_on_conflict:
            logger.info("[SaveFindings] Retrying once after integrity conflict for task %s", task_id)
            return await _save_findings(
                db,
                task_id,
                findings,
                project_root=project_root,
                save_diagnostics=save_diagnostics,
                _retry_on_conflict=False,
            )
        if isinstance(save_diagnostics, dict):
            save_diagnostics["commit_failed"] = True
            save_diagnostics["commit_failed_reason"] = "integrity_conflict"
        return 0
    except Exception as e:
        logger.error(f"Failed to commit findings: {e}")
        await db.rollback()
        if isinstance(save_diagnostics, dict):
            save_diagnostics["commit_failed"] = True
        return 0

    return saved_count


def _calculate_security_score(findings: List[Dict]) -> float:
    """计算安全评分"""
    if not findings:
        return 100.0

    # 基于发现的严重程度计算扣分
    deductions = {
        "critical": 25,
        "high": 15,
        "medium": 8,
        "low": 3,
        "info": 1,
    }

    total_deduction = 0
    for f in findings:
        if isinstance(f, dict):
            sev = f.get("severity", "low")
            total_deduction += deductions.get(sev, 3)

    score = max(0, 100 - total_deduction)
    return float(score)

def _serialize_agent_findings(
    findings: List[AgentFinding],
    *,
    include_false_positive: bool,
) -> List[AgentFindingResponse]:
    responses: List[AgentFindingResponse] = []
    for item in findings:
        verification_payload = (
            item.verification_result
            if isinstance(item.verification_result, dict)
            else {}
        )
        finding_metadata = (
            item.finding_metadata
            if isinstance(getattr(item, "finding_metadata", None), dict)
            else {}
        )
        normalized_item_file_path = _normalize_relative_file_path(
            str(item.file_path or ""),
            None,
        )
        authenticity = verification_payload.get("authenticity") or verification_payload.get("verdict")
        if not authenticity:
            authenticity = (
                "false_positive"
                if str(item.status) == FindingStatus.FALSE_POSITIVE
                else (
                    str(getattr(item, "verdict", "") or "").strip().lower()
                    or "uncertain"
                )
            )
        authenticity = str(authenticity).lower()

        if not include_false_positive and authenticity == "false_positive":
            continue

        reachability = verification_payload.get("reachability")
        verification_evidence = (
            verification_payload.get("verification_evidence")
            or verification_payload.get("evidence")
            or verification_payload.get("details")
            or getattr(item, "verification_evidence", None)
        )
        verification_todo_id = (
            finding_metadata.get("verification_todo_id")
            or verification_payload.get("verification_todo_id")
        )
        verification_fingerprint = (
            finding_metadata.get("verification_fingerprint")
            or verification_payload.get("verification_fingerprint")
        )
        context_start_line = _to_int(verification_payload.get("context_start_line"))
        context_end_line = _to_int(verification_payload.get("context_end_line"))
        reachability_file = None
        reachability_function = None
        reachability_function_start_line = None
        reachability_function_end_line = None
        reachability_target = (
            verification_payload.get("reachability_target")
            if isinstance(verification_payload, dict)
            else None
        )
        if isinstance(reachability_target, dict):
            file_value = reachability_target.get("file_path")
            func_value = reachability_target.get("function")
            if isinstance(file_value, str) and file_value.strip():
                reachability_file = _normalize_relative_file_path(
                    file_value.strip(),
                    None,
                )
            if isinstance(func_value, str) and func_value.strip():
                reachability_function = func_value.strip()
            reachability_function_start_line = _to_int(
                reachability_target.get("start_line")
            )
            reachability_function_end_line = _to_int(
                reachability_target.get("end_line")
            )
        if not reachability_function:
            raw_function_name = getattr(item, "function_name", None)
            if isinstance(raw_function_name, str) and raw_function_name.strip():
                reachability_function = raw_function_name.strip()
        if not reachability_file and normalized_item_file_path:
            reachability_file = normalized_item_file_path
        flow_payload = (
            verification_payload.get("flow")
            if isinstance(verification_payload, dict)
            else None
        )
        flow_path_score = None
        flow_call_chain = None
        function_trigger_flow = None
        flow_control_conditions = None
        if isinstance(flow_payload, dict):
            try:
                flow_path_score = (
                    float(flow_payload.get("path_score"))
                    if flow_payload.get("path_score") is not None
                    else None
                )
            except Exception:
                flow_path_score = None
            raw_chain = flow_payload.get("call_chain")
            if isinstance(raw_chain, list):
                flow_call_chain = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_chain
                    if str(step).strip()
                ]
                flow_call_chain = [step for step in flow_call_chain if step]
            raw_function_chain = flow_payload.get("function_trigger_flow")
            if isinstance(raw_function_chain, list):
                function_trigger_flow = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_function_chain
                    if str(step).strip()
                ]
                function_trigger_flow = [
                    step for step in function_trigger_flow if step
                ]
            raw_controls = flow_payload.get("control_conditions")
            if isinstance(raw_controls, list):
                flow_control_conditions = [
                    _sanitize_text_paths(ctrl, None) or ""
                    for ctrl in raw_controls
                    if str(ctrl).strip()
                ]
                flow_control_conditions = [
                    ctrl for ctrl in flow_control_conditions if ctrl
                ]
        if not function_trigger_flow:
            raw_function_chain = verification_payload.get("function_trigger_flow")
            if isinstance(raw_function_chain, list):
                function_trigger_flow = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_function_chain
                    if str(step).strip()
                ]
                function_trigger_flow = [
                    step for step in function_trigger_flow if step
                ]
        if not function_trigger_flow:
            function_trigger_flow = _build_function_trigger_flow(
                call_chain=flow_call_chain or [],
                function_name=reachability_function,
                file_path=reachability_file or normalized_item_file_path,
                line_start=item.line_start,
                line_end=item.line_end,
            )
        function_trigger_flow = [
            _sanitize_text_paths(step, None) or ""
            for step in (function_trigger_flow or [])
            if str(step).strip()
        ]
        function_trigger_flow = [step for step in function_trigger_flow if step]
        if function_trigger_flow:
            flow_call_chain = function_trigger_flow

        logic_payload = (
            verification_payload.get("logic_authz")
            if isinstance(verification_payload, dict)
            else None
        )
        logic_authz_evidence = None
        if isinstance(logic_payload, dict):
            raw_logic_evidence = logic_payload.get("evidence")
            if isinstance(raw_logic_evidence, list):
                logic_authz_evidence = [
                    str(raw_item)
                    for raw_item in raw_logic_evidence
                    if str(raw_item).strip()
                ]
            elif isinstance(raw_logic_evidence, str) and raw_logic_evidence.strip():
                logic_authz_evidence = [raw_logic_evidence.strip()]

        cwe_id = _extract_cwe_from_references(getattr(item, "references", None))
        if not cwe_id:
            cwe_id = _resolve_cwe_id(
                verification_payload.get("cwe_id") or verification_payload.get("cwe"),
                item.vulnerability_type,
                title=item.title,
                description=item.description,
                code_snippet=item.code_snippet,
            )
        profile = _resolve_vulnerability_profile(
            item.vulnerability_type,
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
        )
        structured_description = _build_structured_cn_description(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
            code_context=item.code_context,
            cwe_id=cwe_id,
            raw_description=item.description,
            line_start=item.line_start,
            line_end=item.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        structured_description_markdown = _build_structured_cn_description_markdown(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
            code_context=item.code_context,
            cwe_id=cwe_id,
            raw_description=item.description,
            line_start=item.line_start,
            line_end=item.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        display_title = _build_structured_cn_display_title(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
        )

        responses.append(
            AgentFindingResponse.model_validate(
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "vulnerability_type": profile["key"],
                    "severity": item.severity,
                    "title": item.title,
                    "display_title": display_title,
                    "description": structured_description,
                    "description_markdown": structured_description_markdown,
                    "file_path": normalized_item_file_path,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "code_snippet": item.code_snippet,
                    "code_context": item.code_context,
                    "cwe_id": cwe_id,
                    "cwe_name": profile["name"],
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                    "is_verified": item.is_verified,
                    "confidence": (
                        item.ai_confidence if item.ai_confidence is not None else 0.5
                    ),
                    "reachability": reachability,
                    "authenticity": authenticity,
                    "verification_evidence": verification_evidence,
                    "verification_todo_id": verification_todo_id,
                    "verification_fingerprint": verification_fingerprint,
                    "flow_path_score": flow_path_score,
                    "flow_call_chain": flow_call_chain,
                    "function_trigger_flow": function_trigger_flow,
                    "flow_control_conditions": flow_control_conditions,
                    "logic_authz_evidence": logic_authz_evidence,
                    "reachability_file": reachability_file,
                    "reachability_function": reachability_function,
                    "reachability_function_start_line": reachability_function_start_line,
                    "reachability_function_end_line": reachability_function_end_line,
                    "trigger_flow": (
                        verification_payload.get("trigger_flow")
                        if isinstance(verification_payload, dict)
                        else None
                    ),
                    "poc_trigger_chain": (
                        verification_payload.get("poc_trigger_chain")
                        if isinstance(verification_payload, dict)
                        else None
                    ),
                    "status": item.status,
                    "suggestion": item.suggestion,
                    # Backward-compatible for test stubs / older schemas.
                    "fix_code": getattr(item, "fix_code", None),
                    "fix_description": getattr(item, "fix_description", None),
                    "report": getattr(item, "report", None),
                    "has_poc": bool(item.has_poc),
                    "poc_code": item.poc_code,
                    "poc_description": item.poc_description,
                    "poc_steps": (
                        item.poc_steps if isinstance(item.poc_steps, list) else None
                    ),
                    "poc": (
                        {
                            "code": item.poc_code,
                            "description": item.poc_description,
                            "steps": item.poc_steps,
                        }
                        if item.has_poc
                        else None
                    ),
                    "created_at": item.created_at,
                }
            )
        )
    return responses


__all__ = [name for name in globals() if not name.startswith("__")]
