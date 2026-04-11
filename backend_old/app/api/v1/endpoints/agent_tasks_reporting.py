"""Report rendering helpers for agent tasks."""

import ast
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import get_db
from app.models.agent_task import AgentFinding, AgentTask, FindingStatus
from app.models.project import Project
from app.models.user import User

from .agent_tasks_findings import *

router = APIRouter()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportExportOptions:
    include_code_snippets: bool = True
    include_remediation: bool = True
    include_metadata: bool = True
    compact_mode: bool = False


DEFAULT_REPORT_EXPORT_OPTIONS = ReportExportOptions()
REPORT_EXPORT_FOOTER = "*本报告由自动化安全审计系统自动生成*"


def _uses_default_report_export_options(options: ReportExportOptions) -> bool:
    return options == DEFAULT_REPORT_EXPORT_OPTIONS


def _compact_markdown(markdown_text: str) -> str:
    normalized = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _resolve_query_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    default_value = getattr(value, "default", None)
    if isinstance(default_value, bool):
        return default_value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _sanitize_download_filename_segment(value: Optional[str], fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "-", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _build_report_download_filename(project: Project, extension: str) -> str:
    project_fallback = str(getattr(project, "id", "") or "project")
    project_name = _sanitize_download_filename_segment(
        getattr(project, "name", None),
        project_fallback,
    )
    date_part = datetime.now().strftime("%Y-%m-%d")
    normalized_extension = str(extension or "").lstrip(".") or "txt"
    return f"漏洞报告-{project_name}-{date_part}.{normalized_extension}"


def _build_download_content_disposition(filename: str) -> str:
    extension_match = re.search(r"(\.[A-Za-z0-9]+)$", filename)
    extension = extension_match.group(1) if extension_match else ""
    stem = filename[: -len(extension)] if extension else filename
    ascii_stem = re.sub(r"[^\x20-\x7E]+", "_", stem)
    ascii_stem = re.sub(r"_+", "_", ascii_stem).strip(" ._-") or "vulnerability-report"
    ascii_filename = f"{ascii_stem}{extension}"
    encoded_filename = quote(filename, safe="")
    return (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

def _escape_markdown_inline(text: Optional[str]) -> str:
    """转义 Markdown 行内特殊字符，避免标题/位置等结构被破坏。"""
    if text is None:
        return ""
    escaped = str(text).replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _escape_markdown_table_cell(text: Optional[str]) -> str:
    return _escape_markdown_inline(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


def _render_markdown_heading_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")).strip()


def _render_markdown_code_span(text: Optional[str]) -> str:
    value = "" if text is None else str(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").strip()
    delimiter_width = max((len(run) for run in re.findall(r"`+", value)), default=0) + 1
    delimiter = "`" * delimiter_width
    if value.startswith("`") or value.endswith("`"):
        return f"{delimiter} {value} {delimiter}"
    return f"{delimiter}{value}{delimiter}"


def _strip_markdown_escape_backslashes(text: str) -> str:
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", r"\1", str(text))


def _normalize_severity(sev: Optional[str]) -> str:
    return str(sev).lower().strip() if sev else ""


def _get_report_export_severity_label(severity: Optional[str]) -> str:
    severity_map = {
        "critical": "严重",
        "high": "高危",
        "medium": "中危",
        "low": "低危",
        "info": "信息",
        "unknown": "未知",
    }
    normalized = _normalize_severity(severity)
    if normalized in severity_map:
        return severity_map[normalized]
    fallback = _normalize_optional_text(severity)
    return fallback or "未知"


def _get_report_export_authenticity_label(value: Optional[str]) -> str:
    label_map = {
        "confirmed": "已确认真实漏洞",
        "verified": "已确认真实漏洞",
        "likely": "高概率真实漏洞",
        "uncertain": "待进一步确认",
        "false_positive": "已判定为误报",
        "unknown": "待确认",
    }
    normalized = _normalize_export_finding_token(value)
    if normalized in label_map:
        return label_map[normalized]
    fallback = _normalize_optional_text(value)
    return fallback or "待确认"


def _get_report_export_reachability_label(value: Optional[str]) -> str:
    label_map = {
        "reachable": "可达",
        "likely_reachable": "可能可达",
        "unknown": "暂不明确",
        "unreachable": "不可达",
    }
    normalized = _normalize_export_finding_token(value)
    if normalized in label_map:
        return label_map[normalized]
    fallback = _normalize_optional_text(value)
    return fallback or "暂不明确"


def _get_report_export_vulnerability_type_label(
    vulnerability_type: Optional[str],
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> str:
    raw_type = _normalize_optional_text(vulnerability_type)
    profile = _resolve_vulnerability_profile(
        vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )
    profile_name = _normalize_optional_text(profile.get("name") if isinstance(profile, dict) else None)
    return profile_name or raw_type or "未知类型"


def _get_report_export_project_description(project: Project) -> str:
    description = _normalize_optional_text(getattr(project, "description", None))
    if not description:
        return "暂无项目描述"
    return re.sub(r"\s+", " ", description)


def _build_project_scan_result_lines(
    *,
    project: Project,
    findings: List[AgentFinding],
    export_statuses: Optional[Dict[str, str]] = None,
    export_options: ReportExportOptions = DEFAULT_REPORT_EXPORT_OPTIONS,
) -> List[str]:
    status_map = export_statuses or {}
    severity_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    status_stats = {"pending": 0, "verified": 0, "false_positive": 0}
    vuln_type_stats: Dict[str, int] = {}

    for finding_row in findings:
        severity = _normalize_severity(getattr(finding_row, "severity", None))
        if severity in severity_stats:
            severity_stats[severity] += 1

        export_status = status_map.get(str(getattr(finding_row, "id", "") or ""), "pending")
        if export_status in status_stats:
            status_stats[export_status] += 1

        vuln_type_label = _get_report_export_vulnerability_type_label(
            getattr(finding_row, "vulnerability_type", None),
            title=getattr(finding_row, "title", None),
            description=getattr(finding_row, "description", None),
            code_snippet=getattr(finding_row, "code_snippet", None),
        )
        vuln_type_stats[vuln_type_label] = vuln_type_stats.get(vuln_type_label, 0) + 1

    lines = [
        "## 漏洞扫描结果",
        "",
    ]
    if export_options.include_metadata:
        lines.append(
            f"- 项目描述：{_escape_markdown_inline(_get_report_export_project_description(project))}"
        )
    lines.extend(
        [
            f"- 漏洞总数：{len(findings)}",
            f"- 待确认：{status_stats.get('pending', 0)}",
            f"- 确报：{status_stats.get('verified', 0)}",
            f"- 误报：{status_stats.get('false_positive', 0)}",
            "- 严重程度分布",
            f"  - 严重：{severity_stats.get('critical', 0)}",
            f"  - 高危：{severity_stats.get('high', 0)}",
            f"  - 中危：{severity_stats.get('medium', 0)}",
            f"  - 低危：{severity_stats.get('low', 0)}",
            f"  - 信息：{severity_stats.get('info', 0)}",
            "- 漏洞类型分布",
        ]
    )

    sorted_vuln_types = sorted(
        vuln_type_stats.items(),
        key=lambda item: (-int(item[1]), str(item[0])),
    )
    if sorted_vuln_types:
        for vuln_type, count in sorted_vuln_types:
            lines.append(f"  - {_escape_markdown_inline(vuln_type)}：{count}")
    else:
        lines.append("  - 暂无")
    lines.append("")
    return lines


def _remove_markdown_sections(markdown_text: str, titles: set[str]) -> str:
    content = _normalize_optional_text(markdown_text)
    if not content:
        return ""

    lines = content.split("\n")
    headings: List[Tuple[int, int, str]] = []
    in_code_block = False

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        matched = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if matched:
            headings.append(
                (
                    index,
                    len(matched.group(1)),
                    _normalize_markdown_section_title(matched.group(2)),
                )
            )

    remove_ranges: List[Tuple[int, int]] = []
    for heading_index, (start_line, level, normalized_title) in enumerate(headings):
        if normalized_title not in titles:
            continue

        end_line = len(lines)
        for next_start, next_level, _next_title in headings[heading_index + 1 :]:
            if next_level <= level:
                end_line = next_start
                break
        remove_ranges.append((start_line, end_line))

    if not remove_ranges:
        return content

    merged_ranges: List[Tuple[int, int]] = []
    for start_line, end_line in sorted(remove_ranges):
        if not merged_ranges or start_line > merged_ranges[-1][1]:
            merged_ranges.append((start_line, end_line))
        else:
            prev_start, prev_end = merged_ranges[-1]
            merged_ranges[-1] = (prev_start, max(prev_end, end_line))

    cleaned_lines: List[str] = []
    cursor = 0
    for start_line, end_line in merged_ranges:
        cleaned_lines.extend(lines[cursor:start_line])
        cursor = end_line
    cleaned_lines.extend(lines[cursor:])

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _insert_section_after_title(markdown_text: str, section_markdown: str) -> str:
    content = _normalize_optional_text(markdown_text)
    section = _normalize_optional_text(section_markdown)
    if not section:
        return content or ""
    if not content:
        return section

    lines = content.split("\n")
    in_code_block = False
    title_index: Optional[int] = None

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if re.match(r"^#\s+.+$", stripped):
            title_index = index
            break

    section_lines = [""] + section.split("\n") + [""]
    if title_index is None:
        merged = section.split("\n") + [""] + lines
    else:
        insert_at = title_index + 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        merged = lines[:insert_at] + section_lines + lines[insert_at:]

    normalized = "\n".join(merged)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _ensure_project_report_title(markdown_text: str, project: Project) -> str:
    content = _normalize_optional_text(markdown_text)
    title_line = f"# 项目风险评估报告：{project.name}"
    if not content:
        return title_line

    lines = content.split("\n")
    first_non_empty_index: Optional[int] = None
    for index, line in enumerate(lines):
        if line.strip():
            first_non_empty_index = index
            break

    if first_non_empty_index is None:
        return title_line

    first_line = lines[first_non_empty_index].strip()
    if re.match(r"^#\s+.+$", first_line):
        lines[first_non_empty_index] = title_line
        return "\n".join(lines).strip()

    return f"{title_line}\n\n{content}".strip()


def _strip_report_export_footer(markdown_text: Optional[str]) -> str:
    content = _normalize_optional_text(markdown_text)
    if not content:
        return ""

    content = re.sub(
        r"\n*---\n\*(?:本报告由自动化安全审计系统(?:自动)?生成)\*\s*$",
        "",
        content.strip(),
    )
    content = re.sub(
        r"(?m)^\*(?:本报告由自动化安全审计系统(?:自动)?生成)\*\s*$",
        "",
        content,
    )
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def _append_report_export_footer(markdown_text: str) -> str:
    content = _strip_report_export_footer(markdown_text)
    if not content:
        return REPORT_EXPORT_FOOTER
    return f"{content.rstrip()}\n\n---\n\n{REPORT_EXPORT_FOOTER}"


def _normalize_poc_reference_text(text: Optional[str]) -> str:
    normalized = _normalize_optional_text(text)
    if not normalized:
        return ""
    return re.sub(r"(?i)\bmock\s*poc\b", "PoC 参考", normalized)


def _normalize_top_risk_entries(markdown_text: str) -> str:
    content = _normalize_optional_text(markdown_text)
    if not content:
        return ""

    lines = content.split("\n")
    in_code_block = False
    active_top_risk_level: Optional[int] = None

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            heading_level = len(heading_match.group(1))
            heading_title = _normalize_markdown_section_title(heading_match.group(2))
            if heading_title == "top 风险条目":
                active_top_risk_level = heading_level
            elif active_top_risk_level is not None and heading_level <= active_top_risk_level:
                active_top_risk_level = None
            continue

        if active_top_risk_level is None:
            continue

        if re.match(r"^\d+\.\s+", stripped):
            lines[index] = _strip_markdown_escape_backslashes(raw_line)

    return "\n".join(lines).strip()


def _finding_sort_key(finding: AgentFinding) -> Tuple[int, float]:
    severity_rank = {
        "critical": 1,
        "high": 2,
        "medium": 3,
        "low": 4,
    }
    rank = severity_rank.get(_normalize_severity(getattr(finding, "severity", None)), 5)
    created_at = getattr(finding, "created_at", None)
    created_ts = 0.0
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_ts = created_at.timestamp()
    return rank, -created_ts


def _looks_like_degraded_function_text(text: Optional[str]) -> bool:
    normalized = _normalize_optional_text(text)
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in {"unknown", "n/a", "-", "none"}:
        return True
    if "未知函数" in normalized:
        return True
    if "<function_" in lowered:
        return True
    if lowered in {"[failed]", "[partial]", "[unknown]"}:
        return True
    return False


def _count_degraded_function_markers(text: Optional[str]) -> int:
    normalized = _normalize_optional_text(text) or ""
    lowered = normalized.lower()
    return (
        normalized.count("未知函数")
        + lowered.count("<function_")
        + lowered.count("[failed]")
        + lowered.count("[partial]")
        + lowered.count("[unknown]")
    )


def _normalize_export_function_name(candidate: Optional[str]) -> Optional[str]:
    normalized = _normalize_optional_text(candidate)
    if not normalized or _looks_like_degraded_function_text(normalized):
        return None
    return normalized


def _extract_function_name_from_title(title: Optional[str]) -> Optional[str]:
    normalized = _normalize_optional_text(title)
    if not normalized:
        return None
    for pattern in (
        r"中([A-Za-z_~][A-Za-z0-9_:$<>~]*)函数",
        r"\b([A-Za-z_~][A-Za-z0-9_:$<>~]*)\s*\(",
    ):
        matched = re.search(pattern, normalized)
        if matched:
            candidate = _normalize_export_function_name(matched.group(1))
            if candidate:
                return candidate
    return None


def _extract_function_name_from_flow_steps(steps: Optional[List[str]]) -> Optional[str]:
    if not isinstance(steps, list):
        return None
    for raw_step in reversed(steps):
        step = _normalize_optional_text(raw_step)
        if not step:
            continue
        step = re.sub(r"^命中位置:\s*", "", step)
        step = re.sub(r"\s*\([^)]*\)\s*$", "", step).strip()

        arrow_matches = re.findall(r"->\s*([A-Za-z_~][A-Za-z0-9_:$<>~]*)", step)
        for candidate in reversed(arrow_matches):
            normalized = _normalize_export_function_name(candidate)
            if normalized:
                return normalized

        if ":" in step:
            tail = step.rsplit(":", 1)[-1].strip()
            tail = tail.split("->")[-1].strip()
            matched = re.match(r"^([A-Za-z_~][A-Za-z0-9_:$<>~]*)$", tail)
            if matched:
                normalized = _normalize_export_function_name(matched.group(1))
                if normalized:
                    return normalized
    return None


def _normalize_report_flow_steps(raw_steps: Any) -> List[str]:
    if not isinstance(raw_steps, list):
        return []
    return [
        str(step).strip()
        for step in raw_steps
        if isinstance(step, str) and str(step).strip()
    ]


def _extract_report_function_context(
    finding_row: AgentFinding,
) -> Dict[str, Any]:
    verification_payload = (
        getattr(finding_row, "verification_result", None)
        if isinstance(getattr(finding_row, "verification_result", None), dict)
        else {}
    )
    flow_payload = (
        verification_payload.get("flow")
        if isinstance(verification_payload, dict)
        else None
    )
    reachability_target = (
        verification_payload.get("reachability_target")
        if isinstance(verification_payload, dict)
        else None
    )

    function_trigger_flow = _normalize_report_flow_steps(
        flow_payload.get("function_trigger_flow")
        if isinstance(flow_payload, dict)
        else None
    )
    flow_call_chain = _normalize_report_flow_steps(
        flow_payload.get("call_chain")
        if isinstance(flow_payload, dict)
        else None
    )
    root_function_flow = _normalize_report_flow_steps(
        verification_payload.get("function_trigger_flow")
        if isinstance(verification_payload, dict)
        else None
    )
    if not function_trigger_flow and root_function_flow:
        function_trigger_flow = root_function_flow
    if not flow_call_chain and root_function_flow:
        flow_call_chain = root_function_flow

    function_name: Optional[str] = None
    for candidate in (
        verification_payload.get("function")
        if isinstance(verification_payload, dict)
        else None,
        reachability_target.get("function")
        if isinstance(reachability_target, dict)
        else None,
        getattr(finding_row, "function_name", None),
        _extract_function_name_from_flow_steps(function_trigger_flow),
        _extract_function_name_from_flow_steps(flow_call_chain),
        _extract_function_name_from_title(getattr(finding_row, "title", None)),
    ):
        normalized = _normalize_export_function_name(candidate)
        if normalized:
            function_name = normalized
            break

    return {
        "verification_payload": verification_payload,
        "function_name": function_name,
        "function_trigger_flow": function_trigger_flow,
    }


def _build_export_finding_display_title(
    finding_row: AgentFinding,
    *,
    function_name: Optional[str],
) -> str:
    title_text = _normalize_optional_text(getattr(finding_row, "title", None))
    if title_text and not _looks_like_degraded_function_text(title_text):
        return title_text

    normalized_file_path = _normalize_relative_file_path(
        str(getattr(finding_row, "file_path", "") or ""),
        None,
    )
    vulnerability_type = str(getattr(finding_row, "vulnerability_type", "") or "")
    description_text = getattr(finding_row, "description", None)
    code_snippet_text = getattr(finding_row, "code_snippet", None)

    if function_name:
        return _build_structured_cn_display_title(
            file_path=normalized_file_path,
            function_name=function_name,
            vulnerability_type=vulnerability_type,
            title=title_text,
            description=description_text,
            code_snippet=code_snippet_text,
        )

    profile = _resolve_vulnerability_profile(
        vulnerability_type,
        title=title_text,
        description=description_text,
        code_snippet=code_snippet_text,
    )
    vuln_name = str(profile.get("name") or "安全漏洞").strip() or "安全漏洞"
    if not vuln_name.endswith("漏洞"):
        vuln_name = f"{vuln_name}漏洞"

    location_text = normalized_file_path or "未知路径"
    line_start = getattr(finding_row, "line_start", None)
    line_end = getattr(finding_row, "line_end", None)
    if line_start:
        location_text = f"{location_text}:{line_start}"
        if line_end and line_end != line_start:
            location_text += f"-{line_end}"
    return f"{location_text}附近{vuln_name}"


def _coerce_export_finding_confidence(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return 0.0
    try:
        return float(text.rstrip("%"))
    except Exception:
        pass
    severity_alias = {
        "critical": 0.95,
        "严重": 0.95,
        "high": 0.85,
        "高危": 0.85,
        "medium": 0.6,
        "中危": 0.6,
        "low": 0.35,
        "低危": 0.35,
        "info": 0.2,
        "信息": 0.2,
    }
    return severity_alias.get(text, 0.0)


def _normalize_export_finding_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _resolve_report_export_finding_status(finding_row: AgentFinding) -> str:
    verification_payload = (
        getattr(finding_row, "verification_result", None)
        if isinstance(getattr(finding_row, "verification_result", None), dict)
        else {}
    )
    return _normalize_export_finding_token(
        getattr(finding_row, "status", None) or verification_payload.get("status")
    )


def _resolve_report_export_finding_verdict(finding_row: AgentFinding) -> str:
    verification_payload = (
        getattr(finding_row, "verification_result", None)
        if isinstance(getattr(finding_row, "verification_result", None), dict)
        else {}
    )
    return _normalize_export_finding_token(
        getattr(finding_row, "verdict", None)
        or verification_payload.get("verdict")
        or verification_payload.get("authenticity")
    )


def _resolve_report_export_status(finding_row: AgentFinding) -> Optional[str]:
    normalized_status = _resolve_report_export_finding_status(finding_row)
    normalized_verdict = _resolve_report_export_finding_verdict(finding_row)

    if normalized_status in {FindingStatus.FIXED, FindingStatus.WONT_FIX, FindingStatus.DUPLICATE}:
        return None
    if normalized_status == FindingStatus.FALSE_POSITIVE:
        return FindingStatus.FALSE_POSITIVE
    if normalized_verdict == "false_positive":
        return FindingStatus.FALSE_POSITIVE
    if normalized_status == FindingStatus.VERIFIED:
        return FindingStatus.VERIFIED
    if normalized_verdict == "confirmed":
        return FindingStatus.VERIFIED
    if normalized_status in {
        FindingStatus.NEW,
        FindingStatus.ANALYZING,
        FindingStatus.NEEDS_REVIEW,
        FindingStatus.LIKELY,
        FindingStatus.UNCERTAIN,
    }:
        return "pending"
    if normalized_verdict in {"likely", "uncertain"}:
        return "pending"
    if normalized_status in {"open", "pending"}:
        return "pending"
    if bool(getattr(finding_row, "is_verified", False)):
        return FindingStatus.VERIFIED
    return "pending"


def _get_report_export_status_label(status: str) -> str:
    if status == FindingStatus.VERIFIED:
        return "确报"
    if status == FindingStatus.FALSE_POSITIVE:
        return "误报"
    return "待确认"


def _get_report_export_status_rank(status: str) -> int:
    if status == FindingStatus.VERIFIED:
        return 0
    if status == "pending":
        return 1
    if status == FindingStatus.FALSE_POSITIVE:
        return 2
    return 3


def _parse_inline_distribution_pairs(raw_text: Optional[str]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for chunk in re.split(r",\s*", str(raw_text or "").strip()):
        candidate = chunk.strip()
        if not candidate:
            continue
        matched = re.match(r"^([^:=：]+?)\s*[:=：]\s*(.+)$", candidate)
        if not matched:
            continue
        key = matched.group(1).strip()
        value = matched.group(2).strip()
        if key:
            pairs.append((key, value))
    return pairs


def _parse_vuln_type_distribution_entries(raw_text: Optional[str]) -> List[Tuple[str, str]]:
    normalized = str(raw_text or "").strip()
    if not normalized or normalized == "{}":
        return []

    parsed: Any
    try:
        parsed = json.loads(normalized)
    except Exception:
        try:
            parsed = ast.literal_eval(normalized)
        except Exception:
            return _parse_inline_distribution_pairs(normalized)

    if not isinstance(parsed, dict):
        return []

    entries: List[Tuple[str, str]] = []
    for key, value in parsed.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        entries.append((normalized_key, str(value).strip()))
    return entries


def _normalize_project_report_risk_overview(
    markdown_text: str,
    *,
    project: Project,
    findings: List[AgentFinding],
    export_statuses: Optional[Dict[str, str]] = None,
    export_options: ReportExportOptions = DEFAULT_REPORT_EXPORT_OPTIONS,
) -> str:
    normalized_content = _strip_report_export_footer(markdown_text)
    summary_section = "\n".join(
        _build_project_scan_result_lines(
            project=project,
            findings=findings,
            export_statuses=export_statuses,
            export_options=export_options,
        )
    ).strip()

    stripped_content = _remove_markdown_sections(
        normalized_content,
        {"项目概览", "漏洞扫描结果", "风险总览", "业务影响评估"},
    )
    content_with_summary = _insert_section_after_title(stripped_content, summary_section)
    content_with_summary = _normalize_top_risk_entries(content_with_summary)
    return _ensure_project_report_title(content_with_summary, project)


def _build_project_report_fallback(
    *,
    project: Project,
    findings: List[AgentFinding],
    report_descriptions: Dict[str, Dict[str, Optional[str]]],
    export_statuses: Optional[Dict[str, str]] = None,
    export_options: ReportExportOptions = DEFAULT_REPORT_EXPORT_OPTIONS,
) -> str:
    status_map = export_statuses or {}
    if not findings:
        return "\n".join(
            [
                f"# 项目风险评估报告：{project.name}",
                "",
                "## 结论",
                "",
                "本次导出范围内无可导出的漏洞条目。",
                "",
                "## 说明",
                "",
                "导出报告默认按待确认、确报、误报三态汇总当前任务的漏洞结果。",
                "",
                "## 建议",
                "",
                "建议继续保持基线安全扫描、代码审查和发布前复测。",
            ]
        )

    top_findings = sorted(
        findings,
        key=lambda item: (
            _finding_sort_key(item)[0],
            -_coerce_export_finding_confidence(
                getattr(item, "confidence", None) or getattr(item, "ai_confidence", None)
            ),
            _finding_sort_key(item)[1],
        ),
    )[:10]

    lines = [
        f"# 项目风险评估报告：{project.name}",
        "",
        *_build_project_scan_result_lines(
            project=project,
            findings=findings,
            export_statuses=status_map,
            export_options=export_options,
        ),
        "## Top 风险条目",
        "",
    ]

    if not top_findings:
        lines.extend(
            [
                "- 当前未发现可确认风险，建议继续保持基线安全扫描与代码审查。",
                "",
            ]
        )
    else:
        for index, finding_row in enumerate(top_findings, start=1):
            finding_id = str(getattr(finding_row, "id", "") or "")
            display_title = (
                report_descriptions.get(finding_id, {}).get("display_title")
                or _normalize_optional_text(getattr(finding_row, "title", None))
                or "未命名漏洞"
            )
            severity = _normalize_severity(getattr(finding_row, "severity", None)) or "unknown"
            severity_label = _get_report_export_severity_label(severity)
            if export_options.include_metadata:
                file_path = _normalize_relative_file_path(
                    str(getattr(finding_row, "file_path", "") or ""),
                    None,
                ) or "-"
                line_start = getattr(finding_row, "line_start", None) or "-"
                lines.append(
                    f"{index}. {_render_markdown_heading_text(display_title)} | "
                    f"{severity_label} | "
                    f"{_render_markdown_heading_text(file_path)}:{line_start}"
                )
            else:
                lines.append(
                    f"{index}. {_render_markdown_heading_text(display_title)} | {severity_label}"
                )
        lines.append("")
    if export_options.include_remediation:
        lines.extend(
            [
                "## 优先级修复计划",
                "",
                "- P0：确报且严重程度为严重/高危的漏洞，立即修复并回归验证。",
                "- P1：待确认或中危风险漏洞，纳入最近迭代复核与修复计划。",
                "- P2：误报条目保留判定依据，作为规则调优和验证样本。",
                "",
                "## 后续治理建议",
                "",
                "- 将漏洞类型热点沉淀为编码规范与静态规则。",
                "- 对关键入口补充单元/集成安全测试和运行时告警。",
                "- 在发布前执行最小化回归与复测，确保修复不引入新缺陷。",
            ]
        )
    return "\n".join(lines)


def _should_use_project_report_fallback(
    stored_report: Optional[str],
    fallback_report: str,
) -> bool:
    stored_unknown_count = _count_degraded_function_markers(stored_report)
    fallback_unknown_count = _count_degraded_function_markers(fallback_report)
    if not _normalize_optional_text(stored_report):
        return True
    return stored_unknown_count > 0 and fallback_unknown_count < stored_unknown_count


def _normalize_markdown_section_title(title: str) -> str:
    text = re.sub(r"`", "", str(title or "")).strip().lower()
    text = re.sub(r"^\d+\s*[.)、．]\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _section_body_is_empty_markdown(body: str) -> bool:
    normalized = re.sub(r"```[^\n]*\n?", "", str(body or ""))
    normalized = re.sub(r"[\s`>*_\-]+", "", normalized)
    return not normalized


def _section_is_placeholder_call_chain(body: str) -> bool:
    normalized = str(body or "").strip()
    if not normalized:
        return True
    return "未明确 source" in normalized and "未明确 sink" in normalized


def _section_is_placeholder_poc(body: str) -> bool:
    normalized = str(body or "").strip()
    if not normalized:
        return True
    if "暂无可执行 PoC" in normalized:
        return True
    return _section_body_is_empty_markdown(normalized)


def _strip_finding_export_noise(markdown_text: Optional[str]) -> str:
    content = _normalize_optional_text(markdown_text)
    if not content:
        return ""

    lines = str(content).split("\n")
    headings: List[Tuple[int, int, str]] = []
    in_code_block = False

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        matched = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if matched:
            headings.append((index, len(matched.group(1)), matched.group(2).strip()))

    if not headings:
        return content

    remove_ranges: List[Tuple[int, int]] = []
    for heading_index, (start_line, level, title) in enumerate(headings):
        end_line = len(lines)
        for next_start, next_level, _next_title in headings[heading_index + 1 :]:
            if next_level <= level:
                end_line = next_start
                break

        normalized_title = _normalize_markdown_section_title(title)
        body = "\n".join(lines[start_line + 1 : end_line]).strip()
        should_remove = False

        if normalized_title == "报告信息":
            should_remove = True
        elif normalized_title == "调用链" and _section_is_placeholder_call_chain(body):
            should_remove = True
        elif normalized_title in {"poc", "mock poc", "poc 参考", "poc参考"} and _section_is_placeholder_poc(body):
            should_remove = True

        if should_remove:
            remove_ranges.append((start_line, end_line))

    if not remove_ranges:
        return content

    merged_ranges: List[Tuple[int, int]] = []
    for start_line, end_line in sorted(remove_ranges):
        if not merged_ranges or start_line > merged_ranges[-1][1]:
            merged_ranges.append((start_line, end_line))
        else:
            prev_start, prev_end = merged_ranges[-1]
            merged_ranges[-1] = (prev_start, max(prev_end, end_line))

    cleaned_lines: List[str] = []
    cursor = 0
    for start_line, end_line in merged_ranges:
        cleaned_lines.extend(lines[cursor:start_line])
        cursor = end_line
    cleaned_lines.extend(lines[cursor:])

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _build_finding_markdown_report(
    *,
    task: AgentTask,
    project: Project,
    finding_id: str,
    finding_data: Dict[str, Any],
    export_options: ReportExportOptions = DEFAULT_REPORT_EXPORT_OPTIONS,
) -> str:
    sections: List[str] = []

    title = str(finding_data.get("display_title") or finding_data.get("title") or "未命名漏洞")
    severity = _get_report_export_severity_label(finding_data.get("severity"))
    vuln_type = _get_report_export_vulnerability_type_label(
        finding_data.get("vulnerability_type"),
        title=finding_data.get("title"),
        description=finding_data.get("description"),
        code_snippet=finding_data.get("code_snippet"),
    )
    authenticity = _get_report_export_authenticity_label(finding_data.get("authenticity"))
    reachability = _get_report_export_reachability_label(finding_data.get("reachability"))
    status_label = str(finding_data.get("status_label") or "").strip()

    sections.append(f"# 漏洞详情报告：{_render_markdown_heading_text(title)}")
    sections.append("")
    sections.append("---")
    sections.append("")

    sections.append("## 漏洞概览")
    sections.append("")
    if status_label:
        sections.append(f"- **状态:** {_escape_markdown_inline(status_label)}")
    sections.append(f"- **严重程度:** {severity}")
    sections.append(f"- **漏洞类型:** {_escape_markdown_inline(vuln_type)}")
    sections.append(f"- **真实性判定:** {_escape_markdown_inline(authenticity)}")
    sections.append(f"- **可达性:** {_escape_markdown_inline(reachability)}")

    confidence = finding_data.get("confidence")
    if isinstance(confidence, (int, float)):
        sections.append(f"- **AI 置信度:** {float(confidence) * 100:.1f}%")

    file_path = finding_data.get("file_path")
    line_start = finding_data.get("line_start")
    line_end = finding_data.get("line_end")
    if export_options.include_metadata and file_path:
        location = _escape_markdown_inline(str(file_path))
        if line_start:
            location += f":{line_start}"
            if line_end and line_end != line_start:
                location += f"-{line_end}"
        sections.append(f"- **位置:** {location}")
    sections.append("")

    description_markdown = finding_data.get("description_markdown") or finding_data.get("description")
    if description_markdown:
        sections.append("## 漏洞描述")
        sections.append("")
        sections.append(str(description_markdown))
        sections.append("")

    code_snippet = finding_data.get("code_snippet")
    if export_options.include_code_snippets and code_snippet:
        lang = infer_code_fence_language(str(file_path or ""))
        sections.append("## 漏洞代码")
        sections.append("")
        sections.append(f"```{lang}")
        sections.append(str(code_snippet).strip())
        sections.append("```")
        sections.append("")

    verification_evidence = finding_data.get("verification_evidence")
    if verification_evidence:
        sections.append("## 验证证据")
        sections.append("")
        sections.append(str(verification_evidence))
        sections.append("")

    suggestion = finding_data.get("suggestion")
    if export_options.include_remediation and suggestion:
        sections.append("## 修复建议")
        sections.append("")
        sections.append(str(suggestion))
        sections.append("")

    if bool(finding_data.get("has_poc")):
        sections.append("## PoC 参考")
        sections.append("")
        poc_description = finding_data.get("poc_description")
        if poc_description:
            sections.append(_normalize_poc_reference_text(str(poc_description)))
            sections.append("")

        poc_steps = finding_data.get("poc_steps")
        if isinstance(poc_steps, list) and poc_steps:
            sections.append("### 复现步骤")
            sections.append("")
            for index, step in enumerate(poc_steps, start=1):
                sections.append(f"{index}. {step}")
            sections.append("")

        poc_code = finding_data.get("poc_code")
        if poc_code:
            sections.append("### PoC 参考代码")
            sections.append("")
            sections.append("```")
            sections.append(str(poc_code).strip())
            sections.append("```")
            sections.append("")

    sections.append("---")
    sections.append("")
    sections.append(REPORT_EXPORT_FOOTER)
    sections.append("")
    return "\n".join(sections)


def _build_finding_payload_from_row(
    finding_row: AgentFinding,
    report_descriptions: Dict[str, Dict[str, Optional[str]]],
    export_status: str,
    export_options: ReportExportOptions = DEFAULT_REPORT_EXPORT_OPTIONS,
) -> Dict[str, Any]:
    finding_id = str(getattr(finding_row, "id", "") or "")
    verification_payload = (
        getattr(finding_row, "verification_result", None)
        if isinstance(getattr(finding_row, "verification_result", None), dict)
        else {}
    )
    evidence = (
        getattr(finding_row, "verification_evidence", None)
        or verification_payload.get("evidence")
        or verification_payload.get("verification_evidence")
        or verification_payload.get("verification_details")
        or verification_payload.get("details")
    )
    description_markdown = (
        report_descriptions.get(finding_id, {}).get("description_markdown")
        or report_descriptions.get(finding_id, {}).get("description")
        or getattr(finding_row, "description", None)
    )
    confidence = getattr(finding_row, "confidence", None)
    if confidence is None:
        confidence = getattr(finding_row, "ai_confidence", None)
    authenticity = getattr(finding_row, "verdict", None)
    if not authenticity:
        authenticity = "verified" if bool(getattr(finding_row, "is_verified", False)) else "unknown"

    return {
        "display_title": (
            report_descriptions.get(finding_id, {}).get("display_title")
            or getattr(finding_row, "title", None)
        ),
        "status": export_status,
        "status_label": _get_report_export_status_label(export_status),
        "title": getattr(finding_row, "title", None),
        "severity": getattr(finding_row, "severity", None),
        "vulnerability_type": getattr(finding_row, "vulnerability_type", None),
        "authenticity": authenticity,
        "reachability": getattr(finding_row, "reachability", None) or "unknown",
        "confidence": confidence,
        "file_path": (
            getattr(finding_row, "file_path", None)
            if export_options.include_metadata
            else None
        ),
        "line_start": (
            getattr(finding_row, "line_start", None)
            if export_options.include_metadata
            else None
        ),
        "line_end": (
            getattr(finding_row, "line_end", None)
            if export_options.include_metadata
            else None
        ),
        "description_markdown": description_markdown,
        "description": getattr(finding_row, "description", None),
        "code_snippet": (
            getattr(finding_row, "code_snippet", None)
            if export_options.include_code_snippets
            else None
        ),
        "verification_evidence": evidence,
        "suggestion": (
            getattr(finding_row, "suggestion", None)
            if export_options.include_remediation
            else None
        ),
        "fix_code": (
            getattr(finding_row, "fix_code", None)
            if export_options.include_remediation
            else None
        ),
        "has_poc": bool(getattr(finding_row, "has_poc", False)),
        "poc_description": getattr(finding_row, "poc_description", None),
        "poc_steps": getattr(finding_row, "poc_steps", None),
        "poc_code": getattr(finding_row, "poc_code", None),
    }


def _render_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return _strip_markdown_escape_backslashes(escaped)


def _normalize_inline_code_escapes(markdown_text: str) -> str:
    def _replace_inline_code(match: re.Match[str]) -> str:
        delimiter = match.group("ticks")
        code_text = match.group("code")
        return f"{delimiter}{_strip_markdown_escape_backslashes(code_text)}{delimiter}"

    return re.sub(
        r"(?P<ticks>`+)(?P<code>[^\n]*?)(?P=ticks)",
        _replace_inline_code,
        markdown_text,
    )


def _split_markdown_table_row(line: str) -> List[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = re.split(r"(?<!\\)\|", stripped)
    return [cell.replace("\\|", "|").strip() for cell in cells]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_markdown_table_row(line)
    if not cells:
        return False
    return all(re.match(r"^:?-{3,}:?$", cell) for cell in cells)


def _markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html_parts: List[str] = []
    paragraph_lines: List[str] = []
    code_lines: List[str] = []
    in_code_block = False
    list_stack: List[Dict[str, Any]] = []

    def _flush_paragraph() -> None:
        if not paragraph_lines:
            return
        rendered = "<br/>".join(_render_inline_markdown(line) for line in paragraph_lines)
        html_parts.append(f"<p>{rendered}</p>")
        paragraph_lines.clear()

    def _close_current_list_item() -> None:
        if not list_stack:
            return
        if list_stack[-1].get("li_open"):
            html_parts.append("</li>")
            list_stack[-1]["li_open"] = False

    def _close_all_lists() -> None:
        while list_stack:
            _close_current_list_item()
            ltype = str(list_stack.pop().get("type") or "ul")
            html_parts.append(f"</{ltype}>")

    def _open_list(indent: int, list_type: str) -> None:
        html_parts.append(f"<{list_type}>")
        list_stack.append({"indent": indent, "type": list_type, "li_open": False})

    def _prepare_list_item(indent: int, list_type: str) -> None:
        """调整到目标层级，并为当前 item 留出正确的父列表结构。"""
        if not list_stack:
            _open_list(indent, list_type)
        else:
            current_indent = int(list_stack[-1]["indent"])
            current_type = str(list_stack[-1]["type"])

            if indent > current_indent:
                # 嵌套列表必须挂在当前打开的 <li> 下。
                if not list_stack[-1].get("li_open"):
                    html_parts.append("<li>")
                    list_stack[-1]["li_open"] = True
                _open_list(indent, list_type)
            else:
                while list_stack and int(list_stack[-1]["indent"]) > indent:
                    _close_current_list_item()
                    ltype = str(list_stack.pop().get("type") or "ul")
                    html_parts.append(f"</{ltype}>")

                if not list_stack or int(list_stack[-1]["indent"]) < indent:
                    _open_list(indent, list_type)
                elif str(list_stack[-1]["type"]) != list_type:
                    _close_current_list_item()
                    ltype = str(list_stack.pop().get("type") or "ul")
                    html_parts.append(f"</{ltype}>")
                    _open_list(indent, list_type)
                else:
                    _close_current_list_item()

        html_parts.append("<li>")
        list_stack[-1]["li_open"] = True

    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\n")
        stripped = line.strip()

        if line.lstrip().startswith("```") and not in_code_block:
            _flush_paragraph()
            _close_all_lists()
            in_code_block = True
            index += 1
            continue

        if in_code_block:
            if line.strip().startswith("```"):
                code_html = html.escape("\n".join(code_lines))
                html_parts.append(f"<pre><code>{code_html}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                code_lines.append(line)
            index += 1
            continue

        if not stripped:
            _flush_paragraph()
            _close_all_lists()
            index += 1
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if "|" in stripped and next_line and _is_markdown_table_separator(next_line):
            _flush_paragraph()
            _close_all_lists()
            headers = _split_markdown_table_row(stripped)
            separators = _split_markdown_table_row(next_line)
            column_count = min(len(headers), len(separators))
            if column_count == 0:
                paragraph_lines.append(line)
                index += 1
                continue

            html_parts.append("<table>")
            html_parts.append("<thead><tr>")
            for header in headers[:column_count]:
                html_parts.append(f"<th>{_render_inline_markdown(header)}</th>")
            html_parts.append("</tr></thead>")
            html_parts.append("<tbody>")

            index += 2
            while index < len(lines):
                row_line = lines[index]
                row_stripped = row_line.strip()
                if not row_stripped or "|" not in row_stripped:
                    break
                row_cells = _split_markdown_table_row(row_stripped)
                if len(row_cells) < column_count:
                    break
                html_parts.append("<tr>")
                for cell in row_cells[:column_count]:
                    html_parts.append(f"<td>{_render_inline_markdown(cell)}</td>")
                html_parts.append("</tr>")
                index += 1

            html_parts.append("</tbody></table>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            _flush_paragraph()
            _close_all_lists()
            level = len(heading_match.group(1))
            title = _render_inline_markdown(heading_match.group(2))
            html_parts.append(f"<h{level}>{title}</h{level}>")
            index += 1
            continue

        if stripped in {"---", "***", "___"}:
            _flush_paragraph()
            _close_all_lists()
            html_parts.append("<hr/>")
            index += 1
            continue

        # 计算缩进级别（以2空格为1级，tab=4空格）
        indent_spaces = len(line) - len(line.lstrip(" \t"))
        indent_level = indent_spaces // 2

        ul_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if ul_match:
            _flush_paragraph()
            _prepare_list_item(indent_level, "ul")
            html_parts.append(_render_inline_markdown(ul_match.group(1)))
            index += 1
            continue

        ol_match = re.match(r"^\d+[.)）]\s*(.+)$", stripped)
        if ol_match:
            _flush_paragraph()
            _prepare_list_item(indent_level, "ol")
            html_parts.append(_render_inline_markdown(ol_match.group(1)))
            index += 1
            continue

        _close_all_lists()
        paragraph_lines.append(line)
        index += 1

    _flush_paragraph()
    _close_all_lists()
    if in_code_block:
        code_html = html.escape("\n".join(code_lines))
        html_parts.append(f"<pre><code>{code_html}</code></pre>")

    return "\n".join(html_parts)


def _strip_leading_markdown_heading(markdown_text: str, title_patterns: List[str]) -> str:
    lines = markdown_text.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return ""

    heading_match = re.match(r"^(#{1,6})\s+(.+)$", lines[index].strip())
    if not heading_match:
        return markdown_text

    heading_text = heading_match.group(2).strip()
    if not any(re.search(pattern, heading_text, re.IGNORECASE) for pattern in title_patterns):
        return markdown_text

    index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return "\n".join(lines[index:])


def _strip_leading_markdown_rules(markdown_text: str) -> str:
    lines = markdown_text.split("\n")
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped in {"---", "***", "___"}:
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            continue
        break
    return "\n".join(lines[index:])


def _shift_markdown_headings(markdown_text: str, level_offset: int = 1) -> str:
    if not markdown_text:
        return markdown_text
    shifted_lines: List[str] = []
    in_code_block = False
    for raw_line in markdown_text.split("\n"):
        stripped = raw_line.lstrip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            shifted_lines.append(raw_line)
            continue
        if not in_code_block:
            heading_match = re.match(r"^(#{1,6})(\s+.+)$", raw_line)
            if heading_match:
                level = min(6, len(heading_match.group(1)) + level_offset)
                shifted_lines.append(f"{'#' * level}{heading_match.group(2)}")
                continue
        shifted_lines.append(raw_line)
    return "\n".join(shifted_lines)


def _normalize_embedded_markdown(
    markdown_text: Optional[str],
    *,
    title_patterns: List[str],
    level_offset: int = 1,
) -> str:
    content = _normalize_optional_text(markdown_text)
    if not content:
        return ""
    content = str(content).strip()
    content = _strip_leading_markdown_heading(content, title_patterns)
    content = _strip_leading_markdown_rules(content)
    content = _shift_markdown_headings(content, level_offset=level_offset)
    content = _normalize_inline_code_escapes(content)
    return content.strip()


def _build_pdf_stylesheet() -> str:
    return """
    @page { size: A4; margin: 20mm 15mm; }
    body {
      font-family: "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Zen Hei", sans-serif;
      font-size: 12px;
      line-height: 1.65;
      color: #111827;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    h1, h2, h3, h4, h5, h6 { color: #111827; margin-top: 16px; margin-bottom: 8px; }
    h1 { font-size: 22px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }
    h2 { font-size: 18px; }
    h3 { font-size: 15px; }
    p { margin: 8px 0; word-break: break-word; overflow-wrap: anywhere; }
    hr { border: none; border-top: 1px solid #e5e7eb; margin: 14px 0; }
    pre {
      background: #f3f4f6;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      padding: 10px;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    code, pre, pre code {
      font-family: "Noto Sans Mono CJK SC", "Menlo", "Consolas", monospace;
    }
    ul, ol {
      margin: 6px 0;
      padding-left: 16px;
      list-style-position: outside;
    }
    ul ul, ol ol, ul ol, ol ul {
      margin: 4px 0;
      padding-left: 14px;
    }
    li { margin: 2px 0; }
    li > p { margin: 0; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; table-layout: fixed; }
    thead { display: table-header-group; }
    thead th { background: #f9fafb; }
    th, td {
      border: 1px solid #e5e7eb;
      padding: 6px 8px;
      text-align: left;
      vertical-align: top;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    tr { break-inside: avoid; }
    """


def _render_markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    try:
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration
    except Exception as exc:
        logger.exception("PDF export unavailable: failed to import WeasyPrint")
        raise HTTPException(status_code=500, detail="PDF 导出不可用，请检查 weasyprint 依赖") from exc

    html_body = _markdown_to_html(markdown_text)
    html_document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
</head>
<body>
{html_body}
</body>
</html>"""

    try:
        font_config = FontConfiguration()
        stylesheet = CSS(string=_build_pdf_stylesheet(), font_config=font_config)
        return HTML(string=html_document).write_pdf(
            stylesheets=[stylesheet],
            font_config=font_config,
        )
    except Exception as exc:
        logger.exception("PDF export failed while rendering report")
        raise HTTPException(status_code=500, detail="PDF 报告生成失败") from exc


def _build_task_export_markdown(
    *,
    task: AgentTask,
    project: Project,
    findings: List[AgentFinding],
    report_descriptions: Dict[str, Dict[str, Optional[str]]],
    export_statuses: Dict[str, str],
    project_report_fallback: str,
    export_options: ReportExportOptions,
) -> str:
    stored_project_report = _normalize_optional_text(getattr(task, "report", None))
    if not findings or not _uses_default_report_export_options(export_options):
        project_report_raw = project_report_fallback
    elif any(
        export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending") != FindingStatus.VERIFIED
        for finding_row in findings
    ):
        project_report_raw = project_report_fallback
    elif _should_use_project_report_fallback(stored_project_report, project_report_fallback):
        project_report_raw = project_report_fallback
    else:
        project_report_raw = stored_project_report or project_report_fallback
    project_report = _normalize_embedded_markdown(
        project_report_raw,
        title_patterns=[
            r"安全审计.*报告",
            r"安全扫描.*报告",
            r"审计导出报告",
        ],
        level_offset=0,
    )
    project_report = _normalize_project_report_risk_overview(
        project_report,
        project=project,
        findings=findings,
        export_statuses=export_statuses,
        export_options=export_options,
    )
    project_report = _strip_report_export_footer(project_report)

    lines: List[str] = []
    if export_options.include_metadata:
        lines.append(str(project_report).strip() if project_report else "_无项目报告内容_")
        lines.append("")

    if not findings:
        lines.append("## 漏洞报告")
        lines.append("")
        lines.append("本次导出范围内无可导出的漏洞条目。")
        lines.append("")
        content = _append_report_export_footer("\n".join(lines))
        if export_options.compact_mode:
            return _compact_markdown(content)
        return content

    section_order = [
        (FindingStatus.VERIFIED, "确报"),
        ("pending", "待确认"),
        (FindingStatus.FALSE_POSITIVE, "误报"),
    ]
    finding_index = 1

    for export_status, _section_title in section_order:
        section_findings = [
            finding_row
            for finding_row in findings
            if export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending") == export_status
        ]
        if not section_findings:
            continue

        for finding_row in section_findings:
            finding_report = None
            if (
                _uses_default_report_export_options(export_options)
                and export_status == FindingStatus.VERIFIED
            ):
                finding_report = _normalize_optional_text(getattr(finding_row, "report", None))
            if not finding_report:
                finding_payload = _build_finding_payload_from_row(
                    finding_row,
                    report_descriptions,
                    export_status=export_status,
                    export_options=export_options,
                )
                finding_report = _build_finding_markdown_report(
                    task=task,
                    project=project,
                    finding_id=str(getattr(finding_row, "id", "") or ""),
                    finding_data=finding_payload,
                    export_options=export_options,
                )
            finding_report = _normalize_embedded_markdown(
                finding_report,
                title_patterns=[
                    r"漏洞详情报告",
                    r"漏洞报告",
                ],
                level_offset=1,
            )
            finding_report = _strip_finding_export_noise(finding_report)
            finding_report = _strip_report_export_footer(finding_report)
            finding_title = (
                report_descriptions.get(str(getattr(finding_row, "id", "") or ""), {}).get("display_title")
                or _normalize_optional_text(getattr(finding_row, "title", None))
            )
            if finding_title:
                lines.append(
                    f"### 漏洞报告 {finding_index}: {_render_markdown_heading_text(finding_title)}"
                )
            else:
                lines.append(f"### 漏洞报告 {finding_index}")
            lines.append("")
            lines.append(str(finding_report).strip() if finding_report else "_无漏洞报告内容_")
            lines.append("")
            finding_index += 1

    content = _append_report_export_footer("\n".join(lines))
    if export_options.compact_mode:
        return _compact_markdown(content)
    return content


@router.get("/{task_id}/report")
async def generate_audit_report(
    task_id: str,
    format: str = Query("markdown", pattern="^(markdown|json|pdf)$"),
    include_code_snippets: bool = Query(True),
    include_remediation: bool = Query(True),
    include_metadata: bool = Query(True),
    compact_mode: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    生成审计报告
    
    支持 Markdown / JSON / PDF 格式
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 读取任务下全部 findings，由导出层统一按 status/verdict 做兼容归一化。
    findings_result = await db.execute(
        select(AgentFinding)
        .where(AgentFinding.task_id == task_id)
        .order_by(
            case(
                (AgentFinding.severity == 'critical', 1),
                (AgentFinding.severity == 'high', 2),
                (AgentFinding.severity == 'medium', 3),
                (AgentFinding.severity == 'low', 4),
                else_=5
            ),
            AgentFinding.created_at.desc()
        )
    )
    all_task_findings = findings_result.scalars().all()
    export_statuses: Dict[str, str] = {}
    findings: List[AgentFinding] = []
    for finding_row in all_task_findings:
        export_status = _resolve_report_export_status(finding_row)
        if export_status is None:
            continue
        finding_id = str(getattr(finding_row, "id", "") or "")
        export_statuses[finding_id] = export_status
        findings.append(finding_row)
    findings = sorted(
        findings,
        key=lambda finding_row: (
            _get_report_export_status_rank(
                export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending")
            ),
            _finding_sort_key(finding_row)[0],
            _finding_sort_key(finding_row)[1],
        ),
    )
    
    #  Helper function to normalize severity for comparison (case-insensitive)
    def normalize_severity(sev: str) -> str:
        return str(sev).lower().strip() if sev else ""
    
    # Log findings for debugging
    logger.info(
        "[Report] Task %s: found %d task findings, exporting %d report findings",
        task_id,
        len(all_task_findings),
        len(findings),
    )
    if findings:
        for i, f in enumerate(findings[:3]):  # Log first 3
            logger.debug(f"[Report] Finding {i+1}: severity='{f.severity}', title='{f.title[:50] if f.title else 'N/A'}'")

    export_options = ReportExportOptions(
        include_code_snippets=_resolve_query_bool(include_code_snippets, True),
        include_remediation=_resolve_query_bool(include_remediation, True),
        include_metadata=_resolve_query_bool(include_metadata, True),
        compact_mode=_resolve_query_bool(compact_mode, False),
    )

    def _build_report_descriptions(
        finding_row: AgentFinding,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        function_context = _extract_report_function_context(finding_row)
        verification_payload = function_context["verification_payload"]
        function_trigger_flow = function_context["function_trigger_flow"]
        function_name = function_context["function_name"]
        display_title = _build_export_finding_display_title(
            finding_row,
            function_name=function_name,
        )
        verification_evidence = (
            verification_payload.get("evidence")
            or verification_payload.get("verification_evidence")
            or verification_payload.get("verification_details")
            or verification_payload.get("details")
        )

        raw_description = getattr(finding_row, "description", None)
        if raw_description and not verification_payload and not function_trigger_flow:
            # 兼容历史报告导出：在缺少验证结构化数据时保留原始描述全文，避免长文本被压缩。
            description_text = str(raw_description)
            return description_text, description_text, display_title

        normalized_file_path = _normalize_relative_file_path(
            str(getattr(finding_row, "file_path", "") or ""),
            None,
        )
        vulnerability_type = str(getattr(finding_row, "vulnerability_type", "") or "")
        title_text = str(getattr(finding_row, "title", "") or "")
        description_text = getattr(finding_row, "description", None)
        code_snippet_text = getattr(finding_row, "code_snippet", None)
        code_context_text = getattr(finding_row, "code_context", None)
        line_start = getattr(finding_row, "line_start", None)
        line_end = getattr(finding_row, "line_end", None)
        cwe_id = _extract_cwe_from_references(getattr(finding_row, "references", None))
        if not cwe_id:
            cwe_id = _resolve_cwe_id(
                verification_payload.get("cwe_id") or verification_payload.get("cwe"),
                vulnerability_type,
                title=title_text,
                description=description_text,
                code_snippet=code_snippet_text,
            )
        profile = _resolve_vulnerability_profile(
            vulnerability_type,
            title=title_text,
            description=description_text,
            code_snippet=code_snippet_text,
        )
        structured_text = _build_structured_cn_description(
            file_path=normalized_file_path,
            function_name=function_name,
            vulnerability_type=profile["key"],
            title=title_text,
            description=description_text,
            code_snippet=code_snippet_text,
            code_context=code_context_text,
            cwe_id=cwe_id,
            raw_description=description_text,
            line_start=line_start,
            line_end=line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        structured_markdown = _build_structured_cn_description_markdown(
            file_path=normalized_file_path,
            function_name=function_name,
            vulnerability_type=profile["key"],
            title=title_text,
            description=description_text,
            code_snippet=code_snippet_text,
            code_context=code_context_text,
            cwe_id=cwe_id,
            raw_description=description_text,
            line_start=line_start,
            line_end=line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        return structured_text, structured_markdown, display_title

    report_descriptions: Dict[str, Dict[str, Optional[str]]] = {}
    for finding_row in findings:
        structured_text, structured_markdown, display_title = _build_report_descriptions(finding_row)
        report_descriptions[str(finding_row.id)] = {
            "description": structured_text,
            "description_markdown": structured_markdown,
            "display_title": display_title,
        }
    
    if format == "json":
        status_distribution = {
            "pending": sum(
                1
                for finding_row in findings
                if export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending") == "pending"
            ),
            "verified": sum(
                1
                for finding_row in findings
                if export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending") == FindingStatus.VERIFIED
            ),
            "false_positive": sum(
                1
                for finding_row in findings
                if export_statuses.get(str(getattr(finding_row, "id", "") or ""), "pending") == FindingStatus.FALSE_POSITIVE
            ),
        }
        # Enhanced JSON report with full metadata
        payload: Dict[str, Any] = {
            "summary": {
                "security_score": task.security_score,
                "total_files_analyzed": task.analyzed_files,
                "total_findings": len(findings),
                "verified_findings": status_distribution["verified"],
                "pending_findings": status_distribution["pending"],
                "false_positive_findings": status_distribution["false_positive"],
                "status_distribution": status_distribution,
                "severity_distribution": {
                    "critical": sum(1 for f in findings if normalize_severity(f.severity) == 'critical'),
                    "high": sum(1 for f in findings if normalize_severity(f.severity) == 'high'),
                    "medium": sum(1 for f in findings if normalize_severity(f.severity) == 'medium'),
                    "low": sum(1 for f in findings if normalize_severity(f.severity) == 'low'),
                },
                "agent_metrics": {
                    "total_iterations": task.total_iterations,
                    "tool_calls": task.tool_calls_count,
                    "tokens_used": task.tokens_used,
                }
            },
            "findings": [
                {
                    "id": f.id,
                    "status": export_statuses.get(str(f.id), "pending"),
                    "status_label": _get_report_export_status_label(
                        export_statuses.get(str(f.id), "pending")
                    ),
                    "finding_identity": (
                        getattr(f, "finding_identity", None)
                        if export_options.include_metadata
                        else None
                    ),
                    "title": f.title,
                    "severity": f.severity,
                    "vulnerability_type": f.vulnerability_type,
                    "description": f.description,
                    "description_markdown": report_descriptions.get(str(f.id), {}).get("description_markdown"),
                    "file_path": (
                        f.file_path if export_options.include_metadata else None
                    ),
                    "line_start": (
                        f.line_start if export_options.include_metadata else None
                    ),
                    "line_end": (
                        f.line_end if export_options.include_metadata else None
                    ),
                    "code_snippet": (
                        f.code_snippet if export_options.include_code_snippets else None
                    ),
                    "is_verified": (
                        export_statuses.get(str(f.id), "pending")
                        == FindingStatus.VERIFIED
                    ),
                    "has_poc": f.has_poc,
                    "poc_code": f.poc_code,
                    "poc_description": f.poc_description,
                    "poc_steps": f.poc_steps,
                    "confidence": f.ai_confidence,
                    "suggestion": (
                        f.suggestion if export_options.include_remediation else None
                    ),
                    "fix_code": (
                        f.fix_code if export_options.include_remediation else None
                    ),
                    "verification_result": (
                        getattr(f, "verification_result", None)
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "flow": (
                        getattr(f, "verification_result", {}).get("flow")
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "logic_authz": (
                        getattr(f, "verification_result", {}).get("logic_authz")
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "created_at": (
                        f.created_at.isoformat()
                        if export_options.include_metadata and f.created_at
                        else None
                    ),
                } for f in findings
            ]
        }
        if export_options.include_metadata:
            payload["report_metadata"] = {
                "task_id": task.id,
                "project_id": task.project_id,
                "project_name": project.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "task_status": task.status,
                "duration_seconds": int((task.completed_at - task.started_at).total_seconds()) if task.completed_at and task.started_at else None,
            }
        return payload

    # Generate Enhanced Markdown Report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate statistics
    total = len(findings)
    critical = sum(1 for f in findings if normalize_severity(f.severity) == 'critical')
    high = sum(1 for f in findings if normalize_severity(f.severity) == 'high')
    medium = sum(1 for f in findings if normalize_severity(f.severity) == 'medium')
    low = sum(1 for f in findings if normalize_severity(f.severity) == 'low')
    verified = sum(
        1
        for f in findings
        if export_statuses.get(str(getattr(f, "id", "") or ""), "pending") == FindingStatus.VERIFIED
    )
    pending = sum(
        1
        for f in findings
        if export_statuses.get(str(getattr(f, "id", "") or ""), "pending") == "pending"
    )
    false_positive = sum(
        1
        for f in findings
        if export_statuses.get(str(getattr(f, "id", "") or ""), "pending") == FindingStatus.FALSE_POSITIVE
    )
    with_poc = sum(1 for f in findings if f.has_poc)

    # Calculate duration
    duration_str = "N/A"
    if task.completed_at and task.started_at:
        duration = (task.completed_at - task.started_at).total_seconds()
        if duration >= 3600:
            duration_str = f"{duration / 3600:.1f} 小时"
        elif duration >= 60:
            duration_str = f"{duration / 60:.1f} 分钟"
        else:
            duration_str = f"{int(duration)} 秒"

    md_lines = []

    # Header
    md_lines.append("# 安全审计报告")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Report Info
    md_lines.append("## 报告信息")
    md_lines.append("")
    md_lines.append(f"| 属性 | 内容 |")
    md_lines.append(f"|----------|-------|")
    md_lines.append(f"| **项目名称** | {_escape_markdown_table_cell(project.name)} |")
    md_lines.append(f"| **任务 ID** | `{task.id[:8]}...` |")
    md_lines.append(f"| **生成时间** | {timestamp} |")
    md_lines.append(f"| **任务状态** | {_escape_markdown_table_cell(str(task.status).upper())} |")
    md_lines.append(f"| **耗时** | {duration_str} |")
    md_lines.append("")

    # Executive Summary
    md_lines.append("## 执行摘要")
    md_lines.append("")

    score = task.security_score
    if score is not None:
        if score >= 80:
            score_assessment = "良好 - 建议进行少量优化"
            score_icon = "通过"
        elif score >= 60:
            score_assessment = "中等 - 存在若干问题需要关注"
            score_icon = "警告"
        else:
            score_assessment = "严重 - 需要立即进行修复"
            score_icon = "未通过"
        md_lines.append(f"**安全评分: {int(score)}/100** [{score_icon}]")
        md_lines.append(f"*{score_assessment}*")
    else:
        md_lines.append("**安全评分:** 未计算")
    md_lines.append("")

    # Findings Summary
    md_lines.append("### 漏洞发现概览")
    md_lines.append("")
    md_lines.append(f"| 严重程度 | 数量 |")
    md_lines.append(f"|----------|-------|")
    if critical > 0:
        md_lines.append(f"| **严重 (CRITICAL)** | {critical} |")
    if high > 0:
        md_lines.append(f"| **高危 (HIGH)** | {high} |")
    if medium > 0:
        md_lines.append(f"| **中危 (MEDIUM)** | {medium} |")
    if low > 0:
        md_lines.append(f"| **低危 (LOW)** | {low} |")
    md_lines.append(f"| **总计** | {total} |")
    md_lines.append("")
    md_lines.append(f"- **确报:** {verified}")
    md_lines.append(f"- **待确认:** {pending}")
    md_lines.append(f"- **误报:** {false_positive}")
    md_lines.append("")

    # Audit Metrics
    md_lines.append("### 审计指标")
    md_lines.append("")
    md_lines.append(f"- **分析文件数:** {task.analyzed_files} / {task.total_files}")
    md_lines.append(f"- **Agent 迭代次数:** {task.total_iterations}")
    md_lines.append(f"- **工具调用次数:** {task.tool_calls_count}")
    md_lines.append(f"- **Token 消耗:** {task.tokens_used:,}")
    if with_poc > 0:
        md_lines.append(f"- **生成的 PoC 参考:** {with_poc}")
    md_lines.append("")

    # Detailed Findings
    if not findings:
        md_lines.append("## 漏洞详情")
        md_lines.append("")
        md_lines.append("*本次审计未发现安全漏洞。*")
        md_lines.append("")
    else:
        # Group findings by severity
        severity_map = {
            'critical': '严重 (Critical)',
            'high': '高危 (High)',
            'medium': '中危 (Medium)',
            'low': '低危 (Low)'
        }
        
        for severity_level, severity_name in severity_map.items():
            severity_findings = [f for f in findings if normalize_severity(f.severity) == severity_level]
            if not severity_findings:
                continue

            md_lines.append(f"## {severity_name} 漏洞")
            md_lines.append("")

            for i, f in enumerate(severity_findings, 1):
                export_status = export_statuses.get(
                    str(getattr(f, "id", "") or ""),
                    "pending",
                )
                verified_badge = (
                    "[已验证]"
                    if export_status == FindingStatus.VERIFIED
                    else "[未验证]"
                )
                poc_badge = " [含 PoC 参考]" if f.has_poc else ""

                md_lines.append(
                    f"### {severity_level.upper()}-{i}: {_escape_markdown_inline(f.title)}"
                )
                md_lines.append("")
                md_lines.append(
                    f"**{verified_badge}**{poc_badge} | 类型: {_render_markdown_code_span(f.vulnerability_type)}"
                )
                md_lines.append("")

                if f.file_path:
                    location = _escape_markdown_inline(f.file_path)
                    if f.line_start:
                        location += f":{f.line_start}"
                        if f.line_end and f.line_end != f.line_start:
                            location += f"-{f.line_end}"
                    md_lines.append(f"**位置:** {location}")
                    md_lines.append("")

                if f.ai_confidence:
                    md_lines.append(f"**AI 置信度:** {int(f.ai_confidence * 100)}%")
                    md_lines.append("")

                verification_result = getattr(f, "verification_result", None)
                if isinstance(verification_result, dict):
                    flow_payload = verification_result.get("flow")
                    if isinstance(flow_payload, dict):
                        flow_score = flow_payload.get("path_score")
                        chain = flow_payload.get("call_chain")
                        if flow_score is not None:
                            try:
                                md_lines.append(f"**可达性评分:** {float(flow_score) * 100:.1f}%")
                            except Exception:
                                md_lines.append(f"**可达性评分:** {flow_score}")
                            md_lines.append("")
                        if isinstance(chain, list) and chain:
                            md_lines.append("**可达性调用链:**")
                            md_lines.append("")
                            for call_item in chain[:12]:
                                md_lines.append(f"- {_render_markdown_code_span(str(call_item))}")
                            md_lines.append("")

                    logic_payload = verification_result.get("logic_authz")
                    if isinstance(logic_payload, dict):
                        evidence = logic_payload.get("evidence")
                        if isinstance(evidence, list) and evidence:
                            md_lines.append("**逻辑漏洞证据:**")
                            md_lines.append("")
                            for evidence_item in evidence[:10]:
                                md_lines.append(f"- {_escape_markdown_inline(str(evidence_item))}")
                            md_lines.append("")

                finding_markdown = (
                    report_descriptions.get(str(f.id), {}).get("description_markdown")
                    or report_descriptions.get(str(f.id), {}).get("description")
                    or f.description
                )
                if finding_markdown:
                    md_lines.append("**漏洞描述:**")
                    md_lines.append("")
                    md_lines.append(str(finding_markdown))
                    md_lines.append("")

                lang = infer_code_fence_language(f.file_path)
                if f.code_snippet:
                    md_lines.append("**漏洞代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang}")
                    md_lines.append(f.code_snippet.strip().replace('\\n', '\n').replace('\r\n', '\n'))
                    md_lines.append("```")
                    md_lines.append("")

                if f.suggestion:
                    md_lines.append("**修复建议:**")
                    md_lines.append("")
                    md_lines.append(f.suggestion)
                    md_lines.append("")

                #  添加 PoC 参考详情
                if f.has_poc:
                    md_lines.append("**PoC 参考:**")
                    md_lines.append("")

                    if f.poc_description:
                        md_lines.append(f"*{_normalize_poc_reference_text(f.poc_description)}*")
                        md_lines.append("")

                    if f.poc_steps:
                        md_lines.append("**复现步骤:**")
                        md_lines.append("")
                        for step_idx, step in enumerate(f.poc_steps, 1):
                            md_lines.append(f"{step_idx}. {step}")
                        md_lines.append("")

                    if f.poc_code:
                        md_lines.append("**PoC 参考代码:**")
                        md_lines.append("")
                        md_lines.append("```")
                        md_lines.append(f.poc_code.strip().replace('\\n', '\n').replace('\r\n', '\n'))
                        md_lines.append("```")
                        md_lines.append("")

                md_lines.append("---")
                md_lines.append("")

    # Remediation Priority
    if critical > 0 or high > 0:
        md_lines.append("## 修复优先级建议")
        md_lines.append("")
        md_lines.append("基于已发现的漏洞，我们建议按以下优先级进行修复：")
        md_lines.append("")
        priority_idx = 1
        if critical > 0:
            md_lines.append(f"{priority_idx}. **立即修复:** 处理 {critical} 个严重漏洞 - 可能造成严重影响")
            priority_idx += 1
        if high > 0:
            md_lines.append(f"{priority_idx}. **高优先级:** 在 1 周内修复 {high} 个高危漏洞")
            priority_idx += 1
        if medium > 0:
            md_lines.append(f"{priority_idx}. **中优先级:** 在 2-4 周内修复 {medium} 个中危漏洞")
            priority_idx += 1
        if low > 0:
            md_lines.append(f"{priority_idx}. **低优先级:** 在日常维护中处理 {low} 个低危漏洞")
            priority_idx += 1
        md_lines.append("")

    # Footer
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(REPORT_EXPORT_FOOTER)
    md_lines.append("")
    legacy_content = "\n".join(md_lines)
    project_report_fallback = (
        _build_project_report_fallback(
            project=project,
            findings=findings,
            report_descriptions=report_descriptions,
            export_statuses=export_statuses,
            export_options=export_options,
        )
        or legacy_content
    )
    export_markdown = _build_task_export_markdown(
        task=task,
        project=project,
        findings=findings,
        report_descriptions=report_descriptions,
        export_statuses=export_statuses,
        project_report_fallback=project_report_fallback,
        export_options=export_options,
    )

    if format == "pdf":
        pdf_content = _render_markdown_to_pdf_bytes(export_markdown)
        filename = _build_report_download_filename(project, "pdf")
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": _build_download_content_disposition(filename)
            },
        )

    filename = _build_report_download_filename(project, "md")
    return Response(
        content=export_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": _build_download_content_disposition(filename)
        }
    )


@router.get("/{task_id}/findings/{finding_id}/report")
async def get_finding_report(
    task_id: str,
    finding_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """按 finding_id 获取单条漏洞详情报告（Markdown/JSON）。"""
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    finding_result = await db.execute(
        select(AgentFinding).where(
            AgentFinding.task_id == task_id,
            AgentFinding.id == finding_id,
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    serialized = _serialize_agent_findings(
        [finding],
        include_false_positive=True,
    )
    if not serialized:
        raise HTTPException(status_code=404, detail="漏洞不存在或已被过滤")

    finding_data = serialized[0].model_dump()
    stored_report = _normalize_optional_text(finding_data.get("report"))

    if format == "json":
        return {
            "report_metadata": {
                "task_id": task.id,
                "finding_id": finding.id,
                "project_id": task.project_id,
                "project_name": project.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "task_status": task.status,
            },
            "finding": finding_data,
        }

    if stored_report:
        filename = f"finding_report_{task.id[:8]}_{finding.id[:8]}.md"
        from fastapi.responses import Response
        return Response(
            content=stored_report,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )

    content = _build_finding_markdown_report(
        task=task,
        project=project,
        finding_id=str(finding.id),
        finding_data=finding_data,
    )
    filename = f"finding_report_{task.id[:8]}_{finding.id[:8]}.md"

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
        },
    )
