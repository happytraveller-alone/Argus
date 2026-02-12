from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _save_findings
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_save_findings_strict_validation_filters_invalid_and_keeps_enriched(tmp_path):
    source_file = tmp_path / "app.py"
    source_file.write_text(
        "\n".join(
            [
                "def run(user_input):",
                "    prefix = 'ok'",
                "    dangerous_call(user_input)",
                "    return prefix",
                "",
                "def dangerous_call(value):",
                "    return value",
            ]
        ),
        encoding="utf-8",
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": "missing path",
            "description": "no file path",
            "verdict": "confirmed",
            "reachability": "reachable",
        },
        {
            "title": "invalid path",
            "file_path": "not_found.py",
            "description": "file does not exist",
            "verdict": "confirmed",
            "reachability": "reachable",
            "line_start": 2,
        },
        {
            "title": "cannot infer line",
            "file_path": "app.py",
            "description": "snippet not found",
            "code_snippet": "def definitely_not_exists(): pass",
            "verdict": "likely",
            "reachability": "likely_reachable",
        },
        {
            "title": "valid inferred finding",
            "file_path": "app.py",
            "description": "dangerous call is reachable",
            "code_snippet": "dangerous_call(user_input)",
            "verdict": "likely",
            "reachability": "likely_reachable",
            "verification_details": "matched dangerous call in source",
        },
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
    assert saved_finding.file_path == "app.py"
    assert saved_finding.line_start == 3
    assert saved_finding.line_end == 3
    assert "dangerous_call(user_input)" in saved_finding.code_snippet
    assert saved_finding.code_context
    assert saved_finding.verification_result["authenticity"] == "likely"
    assert saved_finding.verification_result["reachability"] == "likely_reachable"
