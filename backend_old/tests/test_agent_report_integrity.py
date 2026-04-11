import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.errors = types.SimpleNamespace(
        DockerException=Exception,
        NotFound=Exception,
    )
    docker_stub.from_env = lambda: None
    sys.modules["docker"] = docker_stub

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
        "status": "verified",
        "is_verified": True,
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
        "verdict": "confirmed",
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

    assert "### 漏洞报告 1: Unsafe [link](x) #1 | critical" in body
    assert "Unsafe \\[link\\]\\(x\\) \\#1 \\| critical" not in body
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
    assert "### 报告信息" not in body
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
    assert html.count("<li>") == 2
    assert "代码证据：MagickCore/delegate.c lines 408-422" in html
    assert "危险调用：system(sanitize_command)" in html


def test_markdown_to_html_supports_nested_lists():
    markdown = """- 严重程度分布
  - critical：0
  - high：12
- 漏洞类型分布
  - memory_corruption：10
  - other：1
"""

    html = reporting_endpoint._markdown_to_html(markdown)

    assert "<ul>" in html
    assert "<li>\n严重程度分布\n<ul>" in html
    assert "<li>\ncritical：0\n</li>" in html
    assert "<li>\n漏洞类型分布\n<ul>" in html
    assert "<li>\nmemory_corruption：10\n</li>" in html


def test_build_finding_markdown_report_uses_chinese_overview_and_poc_reference():
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
            "authenticity": "confirmed",
            "reachability": "likely_reachable",
            "has_poc": True,
            "poc_description": "Mock PoC: 仅用于测试环境复现",
            "poc_code": "echo 'mock'",
            "fix_code": "should not be rendered",
        },
    )

    assert "## 报告信息" not in report
    assert "参考修复代码" not in report
    assert "概念验证 (PoC)" not in report
    assert "- **严重程度:** 高危" in report
    assert "- **漏洞类型:** 命令注入漏洞" in report
    assert "- **真实性判定:** 已确认真实漏洞" in report
    assert "- **可达性:** 可能可达" in report
    assert "## PoC 参考" in report
    assert "### PoC 参考代码" in report
    assert report.rstrip().endswith("*本报告由自动化安全审计系统自动生成*")


def test_build_finding_markdown_report_keeps_vulnerability_type_values_without_escape_backslashes():
    task = _make_task(task_id="task-1")
    project = SimpleNamespace(id="project-1", name="Demo")
    report = reporting_endpoint._build_finding_markdown_report(
        task=task,
        project=project,
        finding_id="finding-1",
        finding_data={
            "display_title": "Memory Corruption Finding",
            "severity": "high",
            "vulnerability_type": "memory_corruption",
            "has_poc": False,
        },
    )

    assert "内存破坏漏洞" in report
    assert "memory_corruption" not in report
    assert "memory\\_corruption" not in report


def test_build_project_report_fallback_formats_risk_overview_as_nested_lists():
    markdown = reporting_endpoint._build_project_report_fallback(
        project=SimpleNamespace(name="Demo", description="演示项目"),
        findings=[
            _make_finding(
                id="finding-1",
                severity="high",
                vulnerability_type="command_injection",
                title="delegate command injection",
            )
        ],
        report_descriptions={},
    )

    assert "## 漏洞扫描结果" in markdown
    assert "## 风险总览" not in markdown
    assert "## 业务影响评估" not in markdown
    assert "- 项目描述：演示项目" in markdown
    assert "- 严重程度分布\n  - 严重：0\n  - 高危：1" in markdown
    assert "- 漏洞类型分布\n  - 命令注入漏洞：1" in markdown


def test_strip_finding_export_noise_removes_empty_sections():
    markdown = """## 报告信息

| 属性 | 内容 |
|---|---|
| 漏洞 ID | abc |

## 漏洞概览

- 严重程度：HIGH

## 6. 调用链

- Source：`未明确 source`
- Sink：`未明确 sink`
- 路径：未明确 source -> 未明确 sink

## 7. PoC

```text
暂无可执行 PoC，可基于 source->sink 路径补充 Fuzzing Harness。
```

## 修复建议

尽快修复
"""

    cleaned = reporting_endpoint._strip_finding_export_noise(markdown)

    assert "## 报告信息" not in cleaned
    assert "## 6. 调用链" not in cleaned
    assert "## 7. PoC" not in cleaned
    assert "## 漏洞概览" in cleaned
    assert "## 修复建议" in cleaned


def test_markdown_to_html_unescapes_code_span_underscores():
    html = reporting_endpoint._markdown_to_html("- **漏洞类型:** `memory\\_corruption`")

    assert "<code>memory_corruption</code>" in html
    assert "memory\\_corruption" not in html


@pytest.mark.asyncio
async def test_generate_report_strips_redundant_embedded_titles():
    task = _make_task(
        report="# 安全审计报告\n\n## 报告信息\n\n| 字段 | 值 |\n|---|---|\n| 项目 | Demo |"
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-1",
        report=(
            "# 漏洞详情报告：XSS\n\n"
            "## 报告信息\n\n"
            "| 字段 | 值 |\n|---|---|\n| 位置 | src/app.py:1 |\n\n"
            "## 6. 调用链\n\n"
            "- Source：`未明确 source`\n"
            "- Sink：`未明确 sink`\n"
            "- 路径：未明确 source -> 未明确 sink\n\n"
            "## 7. PoC\n\n"
            "```text\n暂无可执行 PoC，可基于 source->sink 路径补充 Fuzzing Harness。\n```"
        ),
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
    assert "# 安全审计导出报告" not in body
    assert "## 项目报告" not in body
    assert body.count("# 项目风险评估报告：Demo") == 1
    assert "# 安全审计报告" not in body
    assert "漏洞详情报告：XSS" not in body
    assert "| **漏洞 ID** |" not in body
    assert "暂无可执行 PoC" not in body
    assert "未明确 source" not in body
    assert "## 报告信息" in body


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


def test_render_markdown_to_pdf_bytes_uses_cjk_stylesheet(monkeypatch):
    captured = {}

    class _FakeHTML:
        def __init__(self, string):
            captured["html"] = string

        def write_pdf(self, stylesheets=None, font_config=None):
            captured["stylesheets"] = stylesheets
            captured["font_config"] = font_config
            return b"%PDF-1.7\nfake"

    class _FakeCSS:
        def __init__(self, string, font_config=None):
            captured["css"] = string
            captured["css_font_config"] = font_config

    class _FakeFontConfiguration:
        pass

    fake_weasyprint = types.ModuleType("weasyprint")
    fake_weasyprint.HTML = _FakeHTML
    fake_weasyprint.CSS = _FakeCSS
    fake_weasyprint_text = types.ModuleType("weasyprint.text")
    fake_weasyprint_fonts = types.ModuleType("weasyprint.text.fonts")
    fake_weasyprint_fonts.FontConfiguration = _FakeFontConfiguration

    monkeypatch.setitem(sys.modules, "weasyprint", fake_weasyprint)
    monkeypatch.setitem(sys.modules, "weasyprint.text", fake_weasyprint_text)
    monkeypatch.setitem(sys.modules, "weasyprint.text.fonts", fake_weasyprint_fonts)

    pdf_bytes = reporting_endpoint._render_markdown_to_pdf_bytes("# 标题")

    assert pdf_bytes.startswith(b"%PDF-1.7")
    assert "Noto Sans CJK SC" in captured["css"]
    assert "padding-left: 16px" in captured["css"]
    assert "li > p { margin: 0; }" in captured["css"]
    assert captured["stylesheets"]
    assert isinstance(captured["font_config"], _FakeFontConfiguration)
    assert captured["css_font_config"] is captured["font_config"]


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


@pytest.mark.asyncio
async def test_generate_report_markdown_respects_export_options():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-1",
        title="Configurable Finding",
        description="漏洞描述正文",
        code_snippet="dangerous_call(user_input)",
        suggestion="请添加输入校验",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-export-options",
        format="markdown",
        include_code_snippets=False,
        include_remediation=False,
        include_metadata=False,
        compact_mode=True,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "## 项目报告" not in body
    assert "### 报告信息" not in body
    assert "## 漏洞代码" not in body
    assert "dangerous_call(user_input)" not in body
    assert "## 修复建议" not in body
    assert "请添加输入校验" not in body
    assert "\n\n\n" not in body
    assert "Configurable Finding" in body
    assert "漏洞描述正文" in body


@pytest.mark.asyncio
async def test_generate_report_json_respects_export_options():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-1",
        title="JSON Configurable Finding",
        code_snippet="dangerous_call(user_input)",
        suggestion="请添加输入校验",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    payload = await generate_audit_report(
        task_id="task-export-options-json",
        format="json",
        include_code_snippets=False,
        include_remediation=False,
        include_metadata=False,
        compact_mode=False,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert "report_metadata" not in payload
    assert "project_report" not in payload
    assert payload["summary"]["total_findings"] == 1
    assert payload["findings"][0]["title"] == "JSON Configurable Finding"
    assert payload["findings"][0]["code_snippet"] is None
    assert payload["findings"][0]["suggestion"] is None


@pytest.mark.asyncio
async def test_generate_report_exports_pending_findings_from_legacy_uncertain_rows():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    confirmed = _make_finding(
        id="finding-confirmed",
        title="Confirmed Finding",
        status="verified",
        is_verified=True,
        verdict="confirmed",
        confidence=0.91,
        ai_confidence=0.91,
    )
    uncertain = _make_finding(
        id="finding-uncertain",
        title="Uncertain Finding",
        status="uncertain",
        is_verified=True,
        verdict="uncertain",
        confidence=0.5,
        ai_confidence=0.5,
        description="should not be exported",
    )

    markdown_db = AsyncMock()
    markdown_db.get = AsyncMock(side_effect=[task, project])
    markdown_db.execute = AsyncMock(return_value=_ScalarListResult([uncertain, confirmed]))

    markdown_response = await generate_audit_report(
        task_id="task-1",
        format="markdown",
        db=markdown_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = markdown_response.body.decode("utf-8")
    assert "Confirmed Finding" in body
    assert "Uncertain Finding" in body
    assert "should not be exported" in body
    assert "待确认" in body

    json_db = AsyncMock()
    json_db.get = AsyncMock(side_effect=[task, project])
    json_db.execute = AsyncMock(return_value=_ScalarListResult([uncertain, confirmed]))

    payload = await generate_audit_report(
        task_id="task-1",
        format="json",
        db=json_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert payload["summary"]["total_findings"] == 2
    assert payload["summary"]["status_distribution"] == {
        "pending": 1,
        "verified": 1,
        "false_positive": 0,
    }
    assert payload["summary"]["pending_findings"] == 1
    assert payload["summary"]["false_positive_findings"] == 0
    assert [item["id"] for item in payload["findings"]] == [
        "finding-confirmed",
        "finding-uncertain",
    ]
    assert payload["findings"][1]["status"] == "pending"
    assert payload["findings"][1]["status_label"] == "待确认"
    assert payload["findings"][1]["is_verified"] is False


@pytest.mark.asyncio
async def test_generate_report_keeps_status_verified_findings_even_when_is_verified_is_false():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    likely_verified = _make_finding(
        id="finding-likely-verified",
        title="Likely Verified Finding",
        status="verified",
        is_verified=False,
        verdict="uncertain",
        confidence=0.9,
        ai_confidence=0.9,
        description="should be exported because status is verified",
    )
    uncertain = _make_finding(
        id="finding-uncertain",
        title="Uncertain Finding",
        status="uncertain",
        is_verified=True,
        verdict="uncertain",
        confidence=0.5,
        ai_confidence=0.5,
        description="should not be exported",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([uncertain, likely_verified]))

    response = await generate_audit_report(
        task_id="task-status-verified",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "Likely Verified Finding" in body
    assert "should be exported because status is verified" in body
    assert "Uncertain Finding" in body
    assert "should not be exported" in body
    assert "- 待确认：1" in body
    assert "- 确报：1" in body
    assert "- 误报：0" in body


@pytest.mark.asyncio
async def test_generate_report_normalizes_flat_project_risk_overview_to_nested_lists():
    task = _make_task(
        report=(
            "# 项目风险评估报告：Demo\n\n"
            "## 风险总览\n\n"
            "- 严重程度分布：critical=0, high=12, medium=1, low=0, info=0\n"
            '- 漏洞类型分布：{"memory_corruption": 10, "other": 1, "command_injection": 2}\n'
        )
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-confirmed",
        title="Confirmed Finding",
        status="verified",
        is_verified=True,
        verdict="confirmed",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-risk-overview",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "## 漏洞扫描结果" in body
    assert "## 风险总览" not in body
    assert "- 严重程度分布\n  - 严重：0\n  - 高危：1\n  - 中危：0\n  - 低危：0\n  - 信息：0" in body
    assert "- 漏洞类型分布\n  - 跨站脚本漏洞：1" in body
    assert "严重程度分布：critical=0, high=12" not in body
    assert '漏洞类型分布：{"memory_corruption": 10' not in body


@pytest.mark.asyncio
async def test_generate_report_keeps_single_footer_at_end():
    task = _make_task(report="## 项目级风险评估\n\n项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    finding_a = _make_finding(
        id="finding-a",
        title="Finding A",
        report=None,
        has_poc=True,
        poc_code="echo A",
    )
    finding_b = _make_finding(
        id="finding-b",
        title="Finding B",
        report=None,
        severity="low",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding_a, finding_b]))

    response = await generate_audit_report(
        task_id="task-single-footer",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert body.count("本报告由自动化安全审计系统自动生成") == 1
    assert body.rstrip().endswith("*本报告由自动化安全审计系统自动生成*")


@pytest.mark.asyncio
async def test_generate_report_normalizes_inline_code_escapes_in_stored_reports():
    task = _make_task(
        report=(
            "# 项目风险评估报告：Demo\n\n"
            "## 风险总览\n\n"
            "- 漏洞类型：`memory\\_corruption`\n"
        )
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-confirmed",
        title="Confirmed Finding",
        status="verified",
        is_verified=True,
        verdict="confirmed",
        report="# 漏洞详情报告：X\n\n- **漏洞类型:** `memory\\_corruption`\n",
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-inline-code-unescape",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "`memory_corruption`" in body
    assert "memory\\_corruption" not in body


@pytest.mark.asyncio
async def test_generate_report_keeps_pending_only_tasks_non_empty():
    task = _make_task(
        report=(
            "# 项目风险评估报告：Demo\n\n"
            "- uncertain：3\n"
            "- false_positive：1\n"
            "- uncertain 项建议安排人工复核\n"
        )
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    uncertain = _make_finding(
        id="finding-uncertain-only",
        title="Uncertain Finding",
        status="uncertain",
        is_verified=True,
        verdict="uncertain",
        confidence=0.5,
        ai_confidence=0.5,
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([uncertain]))

    response = await generate_audit_report(
        task_id="task-empty-export",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "本次导出范围内未发现可确认风险。" not in body
    assert "导出报告仅保留可确认的漏洞结论" not in body
    assert "本次导出范围内无可确认漏洞。" not in body
    assert "Uncertain Finding" in body
    assert "待确认" in body


@pytest.mark.asyncio
async def test_generate_report_exports_verified_pending_and_false_positive_sections():
    task = _make_task(report="项目报告正文")
    project = SimpleNamespace(id="project-1", name="Demo")
    verified = _make_finding(
        id="finding-verified",
        title="Verified Finding",
        status="verified",
        is_verified=True,
        verdict="confirmed",
        severity="critical",
    )
    pending = _make_finding(
        id="finding-pending",
        title="Pending Finding",
        status="needs_review",
        is_verified=False,
        verdict="likely",
        severity="high",
    )
    false_positive = _make_finding(
        id="finding-fp",
        title="False Positive Finding",
        status="false_positive",
        is_verified=False,
        verdict="false_positive",
        severity="medium",
    )

    markdown_db = AsyncMock()
    markdown_db.get = AsyncMock(side_effect=[task, project])
    markdown_db.execute = AsyncMock(return_value=_ScalarListResult([false_positive, pending, verified]))

    markdown_response = await generate_audit_report(
        task_id="task-three-status",
        format="markdown",
        db=markdown_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    markdown_body = markdown_response.body.decode("utf-8")
    assert "## 确报" not in markdown_body
    assert "## 待确认" not in markdown_body
    assert "## 误报" not in markdown_body
    assert "Verified Finding" in markdown_body
    assert "Pending Finding" in markdown_body
    assert "False Positive Finding" in markdown_body

    json_db = AsyncMock()
    json_db.get = AsyncMock(side_effect=[task, project])
    json_db.execute = AsyncMock(return_value=_ScalarListResult([false_positive, pending, verified]))

    payload = await generate_audit_report(
        task_id="task-three-status",
        format="json",
        db=json_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert payload["summary"]["status_distribution"] == {
        "pending": 1,
        "verified": 1,
        "false_positive": 1,
    }
    assert payload["summary"]["pending_findings"] == 1
    assert payload["summary"]["false_positive_findings"] == 1
    assert [item["status"] for item in payload["findings"]] == [
        "verified",
        "pending",
        "false_positive",
    ]
    assert [item["status_label"] for item in payload["findings"]] == [
        "确报",
        "待确认",
        "误报",
    ]
    assert [item["is_verified"] for item in payload["findings"]] == [
        True,
        False,
        False,
    ]


@pytest.mark.asyncio
async def test_generate_report_uses_reachability_target_function_for_generated_sections():
    task = _make_task(task_id="task-func", report=None)
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-rt",
        title="delegate command injection",
        vulnerability_type="command_injection",
        file_path="MagickCore/delegate.c",
        line_start=408,
        line_end=412,
        function_name=None,
        report=None,
        verification_result={
            "verdict": "confirmed",
            "evidence": "用户可控参数进入危险调用点。",
            "reachability_target": {
                "file_path": "MagickCore/delegate.c",
                "function": "ExternalDelegateCommand",
                "start_line": 390,
                "end_line": 450,
            },
            "function_trigger_flow": [
                "MagickCore/delegate.c:ExternalDelegateCommand (390-450)",
                "命中位置: MagickCore/delegate.c:408-412",
            ],
        },
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-func",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "ExternalDelegateCommand" in body
    assert "未知函数" not in body


@pytest.mark.asyncio
async def test_generate_report_rebuilds_degraded_project_summary_titles():
    task = _make_task(
        task_id="task-summary",
        report=(
            "# 项目风险评估报告：Demo\n\n"
            "## Top 风险条目\n\n"
            "1. MagickCore/delegate.c中未知函数命令注入漏洞 | high | MagickCore/delegate.c:408\n"
        ),
    )
    project = SimpleNamespace(id="project-1", name="Demo")
    finding = _make_finding(
        id="finding-summary",
        title="MagickCore/delegate.c中未知函数命令注入漏洞",
        vulnerability_type="command_injection",
        file_path="MagickCore/delegate.c",
        line_start=408,
        line_end=412,
        function_name=None,
        report=None,
        verification_result={
            "verdict": "confirmed",
            "evidence": "用户可控参数进入危险调用点。",
            "reachability_target": {
                "file_path": "MagickCore/delegate.c",
                "function": "ExternalDelegateCommand",
                "start_line": 390,
                "end_line": 450,
            },
            "function_trigger_flow": [
                "MagickCore/delegate.c:ExternalDelegateCommand (390-450)",
                "命中位置: MagickCore/delegate.c:408-412",
            ],
        },
    )

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, project])
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    response = await generate_audit_report(
        task_id="task-summary",
        format="markdown",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    body = response.body.decode("utf-8")
    assert "## Top 风险条目" in body
    assert "ExternalDelegateCommand" in body
    assert "MagickCore/delegate.c中未知函数命令注入漏洞" not in body
    assert "\\" not in body.split("## Top 风险条目", 1)[1].split("---", 1)[0]
