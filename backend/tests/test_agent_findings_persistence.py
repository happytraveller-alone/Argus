from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _save_findings
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


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
            "verification_result": {
                # SaveFindings strict gate requires a minimal trigger_flow diagram.
                "trigger_flow": {
                    "call_chain": ["handler"],
                    "nodes": [
                        {
                            "file_path": long_file_path,
                            "function": "handler",
                            "code": "def handler():",
                        }
                    ],
                }
            },
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
