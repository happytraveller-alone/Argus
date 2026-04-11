from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _save_findings
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_save_findings_keeps_long_text_fields_without_truncation(tmp_path):
    long_title = "T" * 1200
    long_description = "D" * 12000
    long_file_path = "src/module/vuln.py"
    long_suggestion = "S" * 9000
    long_snippet = "print('x')\n" * 3000

    target_file = tmp_path / "src" / "module" / "vuln.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        "\n".join(["def handler():", *[f"    line {i}" for i in range(1, 60)]]),
        encoding="utf-8",
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": long_title,
            "severity": "high",
            "vulnerability_type": "xss",
            "description": long_description,
            "file_path": long_file_path,
            "line_start": 10,
            "line_end": 11,
            "suggestion": long_suggestion,
            "fix_code": "safe_query = \"SELECT * FROM users WHERE id = %s\"\ncursor.execute(safe_query, (user_id,))",
            "fix_description": "改为参数化查询，避免拼接 SQL 字符串。",
            "code_snippet": long_snippet,
            "verdict": "confirmed",
            "reachability": "reachable",
            "verification_details": "verified by unit harness",
            "verification_result": {},
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-1",
        findings=findings,
        project_root=str(tmp_path),
    )

    assert saved_count == 1
    db.add.assert_called_once()
    db.commit.assert_awaited_once()

    saved_finding = db.add.call_args.args[0]
    assert saved_finding.title == long_title
    assert saved_finding.description == long_description
    assert saved_finding.file_path == long_file_path
    assert saved_finding.suggestion == long_suggestion
    assert saved_finding.code_snippet
    assert saved_finding.code_context
    assert saved_finding.fix_code
    assert "参数化查询" in (saved_finding.fix_description or "")
    assert saved_finding.verification_result["authenticity"] == "confirmed"
    assert saved_finding.verification_result["reachability"] == "reachable"


@pytest.mark.asyncio
async def test_save_findings_persists_false_positive_without_resolved_source_file(tmp_path):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": "示例配置命中并非真实漏洞",
            "severity": "low",
            "vulnerability_type": "hardcoded_secret",
            "description": "示例模板，不参与真实运行",
            "file_path": "examples/demo.env.example",
            "line_start": None,
            "line_end": None,
            "code_snippet": None,
            "verdict": "false_positive",
            "authenticity": "false_positive",
            "reachability": "unreachable",
            "verification_evidence": "示例配置模板，不参与实际部署，验证阶段判定为误报。",
            "verification_todo_id": "todo-fp-1",
            "verification_fingerprint": "fingerprint-fp-1",
            "verification_result": {},
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-fp-1",
        findings=findings,
        project_root=str(tmp_path),
    )

    assert saved_count == 1
    db.add.assert_called_once()
    db.commit.assert_awaited_once()

    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == "false_positive"
    assert saved_finding.verdict == "false_positive"
    assert saved_finding.file_path == "examples/demo.env.example"
    assert saved_finding.line_start is None
    assert saved_finding.code_snippet is None
    assert saved_finding.code_context is None
    assert saved_finding.verification_evidence == "示例配置模板，不参与实际部署，验证阶段判定为误报。"
    assert saved_finding.verification_result["verification_todo_id"] == "todo-fp-1"
    assert saved_finding.verification_result["verification_fingerprint"] == "fingerprint-fp-1"
    assert saved_finding.finding_metadata["verification_todo_id"] == "todo-fp-1"


@pytest.mark.asyncio
async def test_save_findings_synthesizes_false_positive_fingerprint_without_location_or_ids(tmp_path):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": "模板文件命中但属于误报",
            "severity": "low",
            "vulnerability_type": "hardcoded_secret",
            "description": "示例配置，不参与真实部署",
            "file_path": None,
            "line_start": None,
            "line_end": None,
            "code_snippet": None,
            "verdict": "false_positive",
            "authenticity": "false_positive",
            "reachability": "unreachable",
            "verification_evidence": "验证阶段确认为误报。",
            "verification_result": {},
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-fp-synth",
        findings=findings,
        project_root=str(tmp_path),
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == "false_positive"
    assert saved_finding.verification_result["verification_fingerprint"].startswith(
        "fp:task-fp-synth:"
    )
    assert (
        saved_finding.finding_metadata["verification_fingerprint"]
        == saved_finding.verification_result["verification_fingerprint"]
    )
    assert saved_finding.fingerprint == saved_finding.verification_result["verification_fingerprint"]


@pytest.mark.asyncio
async def test_save_findings_preserves_rich_analysis_metadata(tmp_path):
    target_file = tmp_path / "src" / "auth" / "login.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        "\n".join(
            [
                "def login(user_input):",
                "    query = 'SELECT * FROM users WHERE name=' + user_input",
                "    return query",
            ]
        ),
        encoding="utf-8",
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": "src/auth/login.py中login函数SQL注入漏洞",
            "severity": "high",
            "vulnerability_type": "sql_injection",
            "description": "拼接 SQL。",
            "file_path": "src/auth/login.py",
            "line_start": 2,
            "line_end": 2,
            "function_name": "login",
            "code_snippet": "query = 'SELECT * FROM users WHERE name=' + user_input",
            "source": "user_input",
            "sink": "cursor.execute",
            "suggestion": "使用参数化查询",
            "attacker_flow": "POST /login -> login -> cursor.execute",
            "evidence_chain": ["代码片段", "数据流分析"],
            "missing_checks": ["输入校验"],
            "taint_flow": ["request", "login", "cursor.execute"],
            "finding_metadata": {
                "finding_identity": "fid-existing",
                "extra_tool_input": {"custom_extra": "custom-value"},
            },
            "verdict": "confirmed",
            "reachability": "reachable",
            "verification_details": "verified by unit harness",
            "verification_result": {},
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-rich-save",
        findings=findings,
        project_root=str(tmp_path),
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.function_name == "login"
    assert "query = 'SELECT * FROM users WHERE name=' + user_input" in (saved_finding.code_snippet or "")
    assert saved_finding.source == "user_input"
    assert saved_finding.sink == "cursor.execute"
    assert saved_finding.suggestion == "使用参数化查询"
    assert saved_finding.finding_metadata["finding_identity"] == "fid-existing"
    assert saved_finding.finding_metadata["attacker_flow"] == "POST /login -> login -> cursor.execute"
    assert saved_finding.finding_metadata["evidence_chain"] == ["代码片段", "数据流分析"]
    assert saved_finding.finding_metadata["missing_checks"] == ["输入校验"]
    assert saved_finding.finding_metadata["taint_flow"] == ["request", "login", "cursor.execute"]
    assert saved_finding.finding_metadata["extra_tool_input"]["custom_extra"] == "custom-value"
