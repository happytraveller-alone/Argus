from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _save_findings
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_save_findings_autofill_and_diagnostics(tmp_path):
    source_file = tmp_path / "src" / "service.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def handle(payload):",
                "    query = \"SELECT * FROM t WHERE id=\" + payload",
                "    return query",
            ]
        ),
        encoding="utf-8",
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    diagnostics = {}
    findings = [
        {
            "title": "SQLi maybe",
            "severity": "high",
            "vulnerability_type": "sql_injection",
            "file_path": "repo-prefix/src/service.py",
            "line_start": 2,
            "description": "query string concatenation",
            "confidence": 0.9,
            "verification_result": {
                "trigger_flow": {
                    "call_chain": ["handle"],
                    "nodes": [
                        {
                            "file_path": "src/service.py",
                            "function": "handle",
                            "code": "def handle(payload):",
                        }
                    ],
                }
            },
        },
        {
            "title": "invalid finding without file",
            "severity": "medium",
            "vulnerability_type": "xss",
            "description": "missing location",
        },
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-consistency-1",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics=diagnostics,
    )

    assert saved_count == 1
    db.add.assert_called_once()
    db.commit.assert_awaited_once()

    saved_finding = db.add.call_args.args[0]
    assert saved_finding.file_path == "src/service.py"
    assert saved_finding.suggestion
    assert saved_finding.fix_code
    assert saved_finding.verification_result["authenticity"] == "likely"
    assert saved_finding.verification_result["reachability"] == "likely_reachable"

    assert diagnostics["input_count"] == 2
    assert diagnostics["saved_count"] == 1
    assert diagnostics["filtered_count"] == 1
    assert diagnostics["filtered_reasons"]["missing_or_invalid_file_path"] == 1
