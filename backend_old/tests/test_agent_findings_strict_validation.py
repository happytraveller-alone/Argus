from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent.task_findings import _save_findings
import app.models.opengrep  # noqa: F401


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_save_findings_strict_validation_filters_invalid_and_keeps_enriched(tmp_path):
    source_file = tmp_path / "app.py"
    source_file.write_text(
        "\n".join(
            [
                "x = 1",
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
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
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
            "title": "global scope finding should be filtered",
            "file_path": "app.py",
            "line_start": 1,
            "line_end": 1,
            "description": "not inside any function",
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
            "verification_result": {},
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
    assert saved_finding.line_start == 4
    assert saved_finding.line_end == 4
    assert "dangerous_call(user_input)" in saved_finding.code_snippet
    assert saved_finding.code_context
    assert saved_finding.verification_result["authenticity"] == "likely"
    assert saved_finding.verification_result["reachability"] == "likely_reachable"


@pytest.mark.asyncio
async def test_save_findings_filters_ignored_scope_paths(tmp_path):
    ignored_file = tmp_path / ".github" / "workflows" / "pipeline.py"
    ignored_file.parent.mkdir(parents=True, exist_ok=True)
    ignored_file.write_text("def hidden():\n    return 1\n", encoding="utf-8")

    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    diagnostics = {}
    findings = [
        {
            "title": "ignored scope finding",
            "file_path": ".github/workflows/pipeline.py",
            "line_start": 1,
            "line_end": 1,
            "description": "should be filtered by ignored scope path",
            "verdict": "likely",
            "reachability": "likely_reachable",
            "verification_result": {},
        },
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-ignored-scope",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics=diagnostics,
    )

    assert saved_count == 0
    db.add.assert_not_called()
    db.commit.assert_awaited_once()
    assert diagnostics["saved_count"] == 0
    assert diagnostics["filtered_count"] == 1
    assert diagnostics["filtered_reasons"]["ignored_scope_path"] == 1


@pytest.mark.asyncio
async def test_save_findings_keeps_false_positive_payload_with_minimal_fields(tmp_path):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    diagnostics = {}
    findings = [
        {
            "title": "false positive should persist",
            "file_path": "missing/demo.ts",
            "line_start": None,
            "line_end": None,
            "description": "cannot reproduce",
            "code_snippet": None,
            "verdict": "false_positive",
            "reachability": "unreachable",
            "verification_details": "flow shows unreachable because this is only a sample config",
            "verification_todo_id": "todo-1",
            "verification_fingerprint": "fp-1",
            "verification_result": {
                "verification_todo_id": "todo-1",
                "verification_fingerprint": "fp-1",
            },
        },
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-fp-discard",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics=diagnostics,
    )

    assert saved_count == 1
    db.add.assert_called_once()
    assert diagnostics["saved_count"] == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == "false_positive"
    assert saved_finding.verdict == "false_positive"
    assert saved_finding.verification_evidence.startswith("flow shows unreachable")
    assert saved_finding.file_path == "missing/demo.ts"
    assert saved_finding.line_start is None
    assert saved_finding.code_context is None
    assert saved_finding.finding_metadata["verification_todo_id"] == "todo-1"
    assert saved_finding.finding_metadata["verification_fingerprint"] == "fp-1"
