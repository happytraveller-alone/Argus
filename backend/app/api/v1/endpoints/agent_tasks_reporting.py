"""Report rendering helpers for agent tasks."""

import html
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import get_db
from app.models.agent_task import AgentFinding, AgentTask
from app.models.project import Project
from app.models.user import User

from .agent_tasks_findings import *

router = APIRouter()
logger = logging.getLogger(__name__)

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


def _normalize_severity(sev: Optional[str]) -> str:
    return str(sev).lower().strip() if sev else ""


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


def _build_finding_markdown_report(
    *,
    task: AgentTask,
    project: Project,
    finding_id: str,
    finding_data: Dict[str, Any],
) -> str:
    sections: List[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    title = str(finding_data.get("display_title") or finding_data.get("title") or "未命名漏洞")
    severity = str(finding_data.get("severity") or "unknown").upper()
    vuln_type = str(finding_data.get("vulnerability_type") or "unknown")
    authenticity = str(finding_data.get("authenticity") or "unknown")
    reachability = str(finding_data.get("reachability") or "unknown")

    sections.append(f"# 漏洞详情报告：{_escape_markdown_inline(title)}")
    sections.append("")
    sections.append("---")
    sections.append("")
    sections.append("## 报告信息")
    sections.append("")
    sections.append("| 属性 | 内容 |")
    sections.append("|----------|-------|")
    sections.append(f"| **项目名称** | {_escape_markdown_table_cell(project.name)} |")
    sections.append(f"| **任务 ID** | `{task.id[:8]}...` |")
    sections.append(f"| **漏洞 ID** | `{finding_id}` |")
    sections.append(f"| **生成时间** | {timestamp} |")
    sections.append("")

    sections.append("## 漏洞概览")
    sections.append("")
    sections.append(f"- **严重程度:** {severity}")
    sections.append(f"- **漏洞类型:** `{_escape_markdown_inline(vuln_type)}`")
    sections.append(f"- **真实性判定:** {_escape_markdown_inline(authenticity)}")
    sections.append(f"- **可达性:** {_escape_markdown_inline(reachability)}")

    confidence = finding_data.get("confidence")
    if isinstance(confidence, (int, float)):
        sections.append(f"- **AI 置信度:** {float(confidence) * 100:.1f}%")

    file_path = finding_data.get("file_path")
    line_start = finding_data.get("line_start")
    line_end = finding_data.get("line_end")
    if file_path:
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
    if code_snippet:
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
    if suggestion:
        sections.append("## 修复建议")
        sections.append("")
        sections.append(str(suggestion))
        sections.append("")

    fix_code = finding_data.get("fix_code")
    if fix_code:
        lang = infer_code_fence_language(str(file_path or ""))
        sections.append("## 参考修复代码")
        sections.append("")
        sections.append(f"```{lang if file_path else 'text'}")
        sections.append(str(fix_code).strip())
        sections.append("```")
        sections.append("")

    if bool(finding_data.get("has_poc")):
        sections.append("## 概念验证 (PoC)")
        sections.append("")
        poc_description = finding_data.get("poc_description")
        if poc_description:
            sections.append(str(poc_description))
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
            sections.append("### PoC 代码")
            sections.append("")
            sections.append("```")
            sections.append(str(poc_code).strip())
            sections.append("```")
            sections.append("")

    sections.append("---")
    sections.append("")
    sections.append("*本报告由自动化安全审计系统生成*")
    sections.append("")
    return "\n".join(sections)


def _build_finding_payload_from_row(
    finding_row: AgentFinding,
    report_descriptions: Dict[str, Dict[str, Optional[str]]],
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
        "display_title": getattr(finding_row, "title", None),
        "title": getattr(finding_row, "title", None),
        "severity": getattr(finding_row, "severity", None),
        "vulnerability_type": getattr(finding_row, "vulnerability_type", None),
        "authenticity": authenticity,
        "reachability": getattr(finding_row, "reachability", None) or "unknown",
        "confidence": confidence,
        "file_path": getattr(finding_row, "file_path", None),
        "line_start": getattr(finding_row, "line_start", None),
        "line_end": getattr(finding_row, "line_end", None),
        "description_markdown": description_markdown,
        "description": getattr(finding_row, "description", None),
        "code_snippet": getattr(finding_row, "code_snippet", None),
        "verification_evidence": evidence,
        "suggestion": getattr(finding_row, "suggestion", None),
        "fix_code": getattr(finding_row, "fix_code", None),
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
    return escaped


def _markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html_parts: List[str] = []
    paragraph_lines: List[str] = []
    code_lines: List[str] = []
    in_code_block = False
    # list_stack: list of (indent_level, list_type) where list_type is "ul" or "ol"
    list_stack: List[tuple] = []

    def _flush_paragraph() -> None:
        if not paragraph_lines:
            return
        rendered = "<br/>".join(_render_inline_markdown(line) for line in paragraph_lines)
        html_parts.append(f"<p>{rendered}</p>")
        paragraph_lines.clear()

    def _close_all_lists() -> None:
        while list_stack:
            _, ltype = list_stack.pop()
            html_parts.append(f"</{ltype}>")

    def _adjust_list_stack(indent: int, list_type: str) -> None:
        """打开/关闭嵌套列表，使栈顶与当前缩进匹配。"""
        if list_stack and list_stack[-1][0] == indent and list_stack[-1][1] != list_type:
            # 同级但类型切换
            _, ltype = list_stack.pop()
            html_parts.append(f"</{ltype}>")

        if not list_stack or indent > list_stack[-1][0]:
            # 更深缩进：开新列表
            html_parts.append(f"<{list_type}>")
            list_stack.append((indent, list_type))
        elif indent < list_stack[-1][0]:
            # 缩进减少：弹出直到匹配或为空
            while list_stack and list_stack[-1][0] > indent:
                _, ltype = list_stack.pop()
                html_parts.append(f"</{ltype}>")
            if not list_stack or list_stack[-1][0] < indent:
                html_parts.append(f"<{list_type}>")
                list_stack.append((indent, list_type))
        # else: 同级同类型，无需操作

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if line.lstrip().startswith("```") and not in_code_block:
            _flush_paragraph()
            _close_all_lists()
            in_code_block = True
            continue

        if in_code_block:
            if line.strip().startswith("```"):
                code_html = html.escape("\n".join(code_lines))
                html_parts.append(f"<pre><code>{code_html}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                code_lines.append(line)
            continue

        if not stripped:
            _flush_paragraph()
            _close_all_lists()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            _flush_paragraph()
            _close_all_lists()
            level = len(heading_match.group(1))
            title = _render_inline_markdown(heading_match.group(2))
            html_parts.append(f"<h{level}>{title}</h{level}>")
            continue

        if stripped in {"---", "***", "___"}:
            _flush_paragraph()
            _close_all_lists()
            html_parts.append("<hr/>")
            continue

        # 计算缩进级别（以2空格为1级，tab=4空格）
        indent_spaces = len(line) - len(line.lstrip(" \t"))
        indent_level = indent_spaces // 2

        ul_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if ul_match:
            _flush_paragraph()
            _adjust_list_stack(indent_level, "ul")
            html_parts.append(f"<li>{_render_inline_markdown(ul_match.group(1))}</li>")
            continue

        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            _flush_paragraph()
            _adjust_list_stack(indent_level, "ol")
            html_parts.append(f"<li>{_render_inline_markdown(ol_match.group(1))}</li>")
            continue

        _close_all_lists()
        paragraph_lines.append(line)

    _flush_paragraph()
    _close_all_lists()
    if in_code_block:
        code_html = html.escape("\n".join(code_lines))
        html_parts.append(f"<pre><code>{code_html}</code></pre>")

    return "\n".join(html_parts)


def _render_markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:
        logger.exception("PDF export unavailable: failed to import WeasyPrint")
        raise HTTPException(status_code=500, detail="PDF 导出不可用，请检查 weasyprint 依赖") from exc

    html_body = _markdown_to_html(markdown_text)
    html_document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <style>
    @page {{ size: A4; margin: 20mm 15mm; }}
    body {{ font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 12px; line-height: 1.6; color: #111827; }}
    h1, h2, h3, h4, h5, h6 {{ color: #111827; margin-top: 16px; margin-bottom: 8px; }}
    h1 {{ font-size: 22px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }}
    h2 {{ font-size: 18px; }}
    h3 {{ font-size: 15px; }}
    p {{ margin: 8px 0; word-break: break-word; }}
    hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 14px 0; }}
    pre {{ background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 10px; overflow-wrap: anywhere; white-space: pre-wrap; }}
    code {{ font-family: "Menlo", "Consolas", monospace; }}
    ul, ol {{ margin: 8px 0 8px 22px; }}
    li {{ margin: 4px 0; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""

    try:
        return HTML(string=html_document).write_pdf()
    except Exception as exc:
        logger.exception("PDF export failed while rendering report")
        raise HTTPException(status_code=500, detail="PDF 报告生成失败") from exc


def _build_task_export_markdown(
    *,
    task: AgentTask,
    project: Project,
    findings: List[AgentFinding],
    report_descriptions: Dict[str, Dict[str, Optional[str]]],
    project_report_fallback: str,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project_report = _normalize_optional_text(getattr(task, "report", None)) or project_report_fallback

    lines: List[str] = []
    lines.append("# 安全审计导出报告")
    lines.append("")
    lines.append(f"- **项目名称:** {_escape_markdown_inline(project.name)}")
    lines.append(f"- **任务 ID:** `{str(task.id)[:8]}...`")
    lines.append(f"- **导出时间:** {generated_at}")
    lines.append("")
    lines.append("## 项目报告")
    lines.append("")
    lines.append(str(project_report).strip() if project_report else "_无项目报告内容_")
    lines.append("")

    if not findings:
        lines.append("## 漏洞报告")
        lines.append("")
        lines.append("_本任务无漏洞报告_")
        lines.append("")
        return "\n".join(lines)

    for index, finding_row in enumerate(findings, start=1):
        finding_report = _normalize_optional_text(getattr(finding_row, "report", None))
        if not finding_report:
            finding_payload = _build_finding_payload_from_row(finding_row, report_descriptions)
            finding_report = _build_finding_markdown_report(
                task=task,
                project=project,
                finding_id=str(getattr(finding_row, "id", "") or ""),
                finding_data=finding_payload,
            )
        lines.append(f"## 漏洞报告 {index}")
        lines.append("")
        lines.append(str(finding_report).strip())
        lines.append("")

    return "\n".join(lines)


@router.get("/{task_id}/report")
async def generate_audit_report(
    task_id: str,
    format: str = Query("markdown", pattern="^(markdown|json|pdf)$"),
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
    
    # 获取此任务已验证的发现（仅导出 is_verified=True 的条目）
    findings = await db.execute(
        select(AgentFinding)
        .where(AgentFinding.task_id == task_id, AgentFinding.is_verified == True)
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
    findings = findings.scalars().all()
    findings = sorted(findings, key=_finding_sort_key)
    
    #  Helper function to normalize severity for comparison (case-insensitive)
    def normalize_severity(sev: str) -> str:
        return str(sev).lower().strip() if sev else ""
    
    # Log findings for debugging
    logger.info(f"[Report] Task {task_id}: Found {len(findings)} findings from database")
    if findings:
        for i, f in enumerate(findings[:3]):  # Log first 3
            logger.debug(f"[Report] Finding {i+1}: severity='{f.severity}', title='{f.title[:50] if f.title else 'N/A'}'")

    def _build_report_descriptions(
        finding_row: AgentFinding,
    ) -> Tuple[Optional[str], Optional[str]]:
        verification_raw = getattr(finding_row, "verification_result", None)
        verification_payload = (
            verification_raw
            if isinstance(verification_raw, dict)
            else {}
        )
        verification_evidence = (
            verification_payload.get("evidence")
            or verification_payload.get("verification_evidence")
            or verification_payload.get("verification_details")
            or verification_payload.get("details")
        )
        flow_payload = verification_payload.get("flow") if isinstance(verification_payload, dict) else None
        function_trigger_flow: Optional[List[str]] = None
        if isinstance(flow_payload, dict):
            raw_flow = flow_payload.get("function_trigger_flow")
            if isinstance(raw_flow, list):
                function_trigger_flow = [
                    str(step).strip()
                    for step in raw_flow
                    if isinstance(step, str) and str(step).strip()
                ]
            if not function_trigger_flow:
                raw_chain = flow_payload.get("call_chain")
                if isinstance(raw_chain, list):
                    function_trigger_flow = [
                        str(step).strip()
                        for step in raw_chain
                        if isinstance(step, str) and str(step).strip()
                    ]
        if not function_trigger_flow:
            raw_flow = verification_payload.get("function_trigger_flow")
            if isinstance(raw_flow, list):
                function_trigger_flow = [
                    str(step).strip()
                    for step in raw_flow
                    if isinstance(step, str) and str(step).strip()
                ]

        raw_description = getattr(finding_row, "description", None)
        if raw_description and not verification_payload and not function_trigger_flow:
            # 兼容历史报告导出：在缺少验证结构化数据时保留原始描述全文，避免长文本被压缩。
            description_text = str(raw_description)
            return description_text, description_text

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
        function_name = (
            str(verification_payload.get("function") or "").strip()
            or str(getattr(finding_row, "function_name", "") or "").strip()
            or None
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
        return structured_text, structured_markdown

    report_descriptions: Dict[str, Dict[str, Optional[str]]] = {}
    for finding_row in findings:
        structured_text, structured_markdown = _build_report_descriptions(finding_row)
        report_descriptions[str(finding_row.id)] = {
            "description": structured_text,
            "description_markdown": structured_markdown,
        }
    
    if format == "json":
        # Enhanced JSON report with full metadata
        return {
            "report_metadata": {
                "task_id": task.id,
                "project_id": task.project_id,
                "project_name": project.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "task_status": task.status,
                "duration_seconds": int((task.completed_at - task.started_at).total_seconds()) if task.completed_at and task.started_at else None,
            },
            "summary": {
                "security_score": task.security_score,
                "total_files_analyzed": task.analyzed_files,
                "total_findings": len(findings),
                "verified_findings": sum(1 for f in findings if f.is_verified),
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
                    "finding_identity": getattr(f, "finding_identity", None),
                    "title": f.title,
                    "severity": f.severity,
                    "vulnerability_type": f.vulnerability_type,
                    "description": f.description,
                    "description_markdown": report_descriptions.get(str(f.id), {}).get("description_markdown"),
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "code_snippet": f.code_snippet,
                    "is_verified": f.is_verified,
                    "has_poc": f.has_poc,
                    "poc_code": f.poc_code,
                    "poc_description": f.poc_description,
                    "poc_steps": f.poc_steps,
                    "confidence": f.ai_confidence,
                    "suggestion": f.suggestion,
                    "fix_code": f.fix_code,
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
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                } for f in findings
            ]
        }

    # Generate Enhanced Markdown Report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate statistics
    total = len(findings)
    critical = sum(1 for f in findings if normalize_severity(f.severity) == 'critical')
    high = sum(1 for f in findings if normalize_severity(f.severity) == 'high')
    medium = sum(1 for f in findings if normalize_severity(f.severity) == 'medium')
    low = sum(1 for f in findings if normalize_severity(f.severity) == 'low')
    verified = sum(1 for f in findings if f.is_verified)
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
    md_lines.append(f"| 严重程度 | 数量 | 已验证 |")
    md_lines.append(f"|----------|-------|----------|")
    if critical > 0:
        md_lines.append(f"| **严重 (CRITICAL)** | {critical} | {sum(1 for f in findings if normalize_severity(f.severity) == 'critical' and f.is_verified)} |")
    if high > 0:
        md_lines.append(f"| **高危 (HIGH)** | {high} | {sum(1 for f in findings if normalize_severity(f.severity) == 'high' and f.is_verified)} |")
    if medium > 0:
        md_lines.append(f"| **中危 (MEDIUM)** | {medium} | {sum(1 for f in findings if normalize_severity(f.severity) == 'medium' and f.is_verified)} |")
    if low > 0:
        md_lines.append(f"| **低危 (LOW)** | {low} | {sum(1 for f in findings if normalize_severity(f.severity) == 'low' and f.is_verified)} |")
    md_lines.append(f"| **总计** | {total} | {verified} |")
    md_lines.append("")

    # Audit Metrics
    md_lines.append("### 审计指标")
    md_lines.append("")
    md_lines.append(f"- **分析文件数:** {task.analyzed_files} / {task.total_files}")
    md_lines.append(f"- **Agent 迭代次数:** {task.total_iterations}")
    md_lines.append(f"- **工具调用次数:** {task.tool_calls_count}")
    md_lines.append(f"- **Token 消耗:** {task.tokens_used:,}")
    if with_poc > 0:
        md_lines.append(f"- **生成的 PoC:** {with_poc}")
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
                verified_badge = "[已验证]" if f.is_verified else "[未验证]"
                poc_badge = " [含 PoC]" if f.has_poc else ""

                md_lines.append(
                    f"### {severity_level.upper()}-{i}: {_escape_markdown_inline(f.title)}"
                )
                md_lines.append("")
                md_lines.append(
                    f"**{verified_badge}**{poc_badge} | 类型: `{_escape_markdown_inline(f.vulnerability_type)}`"
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
                                md_lines.append(f"- `{_escape_markdown_inline(str(call_item))}`")
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

                if f.fix_code:
                    md_lines.append("**参考修复代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang if f.file_path else 'text'}")
                    md_lines.append(f.fix_code.strip().replace('\\n', '\n').replace('\r\n', '\n'))
                    md_lines.append("```")
                    md_lines.append("")

                #  添加 PoC 详情
                if f.has_poc:
                    md_lines.append("**概念验证 (PoC):**")
                    md_lines.append("")

                    if f.poc_description:
                        md_lines.append(f"*{f.poc_description}*")
                        md_lines.append("")

                    if f.poc_steps:
                        md_lines.append("**复现步骤:**")
                        md_lines.append("")
                        for step_idx, step in enumerate(f.poc_steps, 1):
                            md_lines.append(f"{step_idx}. {step}")
                        md_lines.append("")

                    if f.poc_code:
                        md_lines.append("**PoC 代码:**")
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
    md_lines.append("*本报告由自动化安全审计系统生成*")
    md_lines.append("")
    legacy_content = "\n".join(md_lines)
    export_markdown = _build_task_export_markdown(
        task=task,
        project=project,
        findings=findings,
        report_descriptions=report_descriptions,
        project_report_fallback=legacy_content,
    )

    if format == "pdf":
        pdf_content = _render_markdown_to_pdf_bytes(export_markdown)
        filename = f"audit_report_{task.id[:8]}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )

    filename = f"audit_report_{task.id[:8]}_{datetime.now().strftime('%Y%m%d')}.md"
    return Response(
        content=export_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
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
