from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import agent_tasks_reporting as reporting_endpoint
from app.api.v1.endpoints.agent_tasks import generate_audit_report


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _make_task(task_id: str = "task-1", report: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        project_id="project-1",
        status="completed",
        completed_at=datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc),
        security_score=75,
        analyzed_files=10,
        total_files=10,
        total_iterations=20,
        tool_calls_count=30,
        tokens_used=2048,
        report=report,
    )


def _make_finding(**overrides) -> SimpleNamespace:
    payload = {
        "id": "finding-1",
        "severity": "high",
        "title": "Sample Finding",
        "vulnerability_type": "xss",
        "description": "description",
        "file_path": "src/app.py",
        "line_start": 12,
        "line_end": 15,
        "code_snippet": None,
        "code_context": None,
        "function_name": None,
        "references": None,
        "is_verified": False,
        "has_poc": False,
        "poc_code": None,
        "poc_description": None,
        "poc_steps": None,
        "ai_confidence": 0.92,
        "confidence": None,
        "suggestion": None,
        "fix_code": None,
        "report": None,
        "finding_identity": None,
        "verification_result": None,
        "verification_evidence": None,
        "reachability": None,
        "verdict": None,
        "created_at": datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_generate_report_keeps_long_text_and_escapes_markdown_fields():
    task_id = "task-1"
    long_description = "这是一段很长的漏洞描述。" * 600
    long_path = "src/security/[core](module)#file.py"
    title_with_markdown = "Unsafe [link](x) #1 | critical"

    finding = _make_finding(
        id="finding-1",
        title=title_with_markdown,
        description=long_description,
        file_path=long_path,
    )

    task = _make_task(task_id=task_id)
    project = SimpleNamespace(id="project-1", name="Demo [Project] #1")

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id=task_id,
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert response.media_type == "text/markdown; charset=utf-8"

    assert "Unsafe \\[link\\]\\(x\\) \\#1 \\| critical" in body
    assert "src/security/\\[core\\]\\(module\\)\\#file.py:12-15" in body
    assert long_description in body
    assert "VulHunter" not in body


@pytest.mark.asyncio
async def test_generate_report_exports_project_then_each_finding_report_in_order():
    task = _make_task(report="## 项目级风险评估\n\n项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")

    low = _make_finding(
        id="finding-low",
        severity="low",
        title="low title",
        report="# LOW report",
        created_at=datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc),
    )
    high = _make_finding(
        id="finding-high",
        severity="high",
        title="high title",
        report="# HIGH report",
        created_at=datetime(2026, 2, 12, 9, 0, 0, tzinfo=timezone.utc),
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([low, high]))

    response = await generate_audit_report(
        task_id="task-1",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    project_idx = body.find("项目报告正文")
    high_idx = body.find("# HIGH report")
    low_idx = body.find("# LOW report")

    assert project_idx != -1
    assert high_idx != -1
    assert low_idx != -1
    assert project_idx < high_idx < low_idx


@pytest.mark.asyncio
async def test_generate_report_falls_back_to_generated_finding_report_when_missing_stored_report():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-1",
        title="Fallback Finding",
        report=None,
        description="fallback detail",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-1",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "## 漏洞报告 1" in body
    assert "漏洞详情报告：Fallback Finding" not in body
    assert "### 报告信息" in body
    assert "Fallback Finding" in body


def test_markdown_to_html_renders_markdown_tables():
    markdown = """# 标题

| 属性 | 内容 |
|------|------|
| 项目 | ImageMagick |
| 风险 | 高 |
"""

    html = reporting_endpoint._markdown_to_html(markdown)

    assert "<table>" in html
    assert "<thead><tr>" in html
    assert "<th>属性</th>" in html
    assert "<td>ImageMagick</td>" in html


def test_markdown_to_html_supports_parenthesized_ordered_list():
    markdown = """漏洞描述：
1) 代码证据：MagickCore/delegate.c lines 408-422
2）危险调用：system(sanitize_command)
"""
    html = reporting_endpoint._markdown_to_html(markdown)

    assert "<ol>" in html
    assert "<li>代码证据：MagickCore/delegate.c lines 408-422</li>" in html
    assert "<li>危险调用：system(sanitize_command)</li>" in html


def test_build_finding_markdown_report_hides_fix_code_and_uses_mock_poc():
    task = _make_task(task_id="task-1")
    project = SimpleNamespace(id="project-1", name="Demo")
    report = reporting_endpoint._build_finding_markdown_report(
        task=task,
        project=project,
        finding_id="finding-1",
        finding_data={
            "display_title": "Mock PoC Finding",
            "severity": "high",
            "vulnerability_type": "command_injection",
            "has_poc": True,
            "poc_description": "Mock PoC: 仅用于测试环境复现",
            "poc_code": "echo 'mock'",
            "fix_code": "should not be rendered",
        },
    )

    assert "参考修复代码" not in report
    assert "概念验证 (PoC)" not in report
    assert "## Mock PoC" in report
    assert "### Mock PoC 代码" in report


@pytest.mark.asyncio
async def test_generate_report_strips_redundant_embedded_titles():
    task = _make_task(
        report="# 安全审计报告\n\n## 报告信息\n\n| 字段 | 值 |\n|---|---|\n| 项目 | Demo |"
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-1",
        report="# 漏洞详情报告：XSS\n\n## 报告信息\n\n- 位置: src/app.py:1",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-1",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert body.count("# 安全审计导出报告") == 1
    assert "# 安全审计报告" not in body
    assert "漏洞详情报告：XSS" not in body
    assert "### 报告信息" in body


@pytest.mark.asyncio
async def test_generate_report_supports_pdf_export(monkeypatch):
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(report="# FINDING report")

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    monkeypatch.setattr(
        reporting_endpoint,
        "_render_markdown_to_pdf_bytes",
        lambda markdown_text: b"%PDF-1.4\nmock",
    )

    response = await generate_audit_report(
        task_id="task-1",
        format="pdf",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-1.4")
    assert response.headers["content-disposition"].endswith(".pdf")


@pytest.mark.asyncio
async def test_generate_report_json_shape_compatible():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(id="finding-1")

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    payload = await generate_audit_report(
        task_id="task-1",
        format="json",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert "report_metadata" in payload
    assert "summary" in payload
    assert "findings" in payload
    assert payload["summary"]["total_findings"] == 1
    assert payload["report_metadata"]["project_name"] == "Demo"
