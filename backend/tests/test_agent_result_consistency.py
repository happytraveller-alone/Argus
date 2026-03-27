from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import _save_findings
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_save_findings_requires_verification_result_and_keeps_verified_payload(tmp_path):
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
                "authenticity": "confirmed",
                "reachability": "reachable",
                "evidence": "verified by controlled request replay",
            },
        },
        {
            "title": "invalid finding without file",
            "severity": "medium",
            "vulnerability_type": "xss",
            "description": "missing location",
            "verification_result": {
                "authenticity": "likely",
                "reachability": "likely_reachable",
                "evidence": "missing file path should still be filtered",
            },
        },
        {
            "title": "missing verification payload",
            "severity": "high",
            "vulnerability_type": "command_injection",
            "file_path": "src/service.py",
            "line_start": 1,
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
    assert saved_finding.verification_result["authenticity"] == "confirmed"
    assert saved_finding.verification_result["reachability"] == "reachable"
    assert saved_finding.verification_result["evidence"] == "verified by controlled request replay"
    reachability_target = saved_finding.verification_result.get("reachability_target")
    assert isinstance(reachability_target, dict)
    assert isinstance(reachability_target.get("start_line"), int)
    assert isinstance(reachability_target.get("end_line"), int)
    assert saved_finding.verification_result.get("function_trigger_flow")
    assert any(
        "handle" in step
        for step in saved_finding.verification_result.get("function_trigger_flow", [])
    )
    assert saved_finding.references == [{"cwe": "CWE-89"}]

    assert diagnostics["input_count"] == 3
    assert diagnostics["saved_count"] == 1
    assert diagnostics["filtered_count"] == 2
    assert diagnostics["filtered_reasons"]["missing_or_invalid_file_path"] == 1
    assert diagnostics["filtered_reasons"]["missing_verification_result"] == 1


@pytest.mark.asyncio
async def test_save_findings_filters_pseudo_c_attribute_function_name(tmp_path):
    source_file = tmp_path / "src" / "demo.c"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "static __attribute__((unused)) int parse_node(int input) {",
                "    return input + 1;",
                "}",
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
            "title": "C parsing issue",
            "severity": "high",
            "vulnerability_type": "memory_corruption",
            "file_path": "src/demo.c",
            "line_start": 2,
            "description": "suspicious pointer behavior",
            "confidence": 0.8,
            "verification_result": {
                "authenticity": "confirmed",
                "reachability": "reachable",
                "evidence": "verified by static control-flow checks",
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-consistency-c-1",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.function_name == "parse_node"
    assert saved_finding.function_name != "__attribute__"
    reachability_target = saved_finding.verification_result.get("reachability_target") or {}
    assert reachability_target.get("function") == "parse_node"


@pytest.mark.asyncio
async def test_save_findings_does_not_autofill_fix_code_for_verification_stage(tmp_path):
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

    findings = [
        {
            "title": "Verification finding",
            "severity": "high",
            "vulnerability_type": "sql_injection",
            "file_path": "src/service.py",
            "line_start": 2,
            "description": "query string concatenation",
            "confidence": 0.9,
            "verification_stage_completed": True,
            "verification_result": {
                "authenticity": "confirmed",
                "reachability": "reachable",
                "evidence": "verified by controlled request replay",
                "verification_stage_completed": True,
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-consistency-2",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.suggestion
    assert saved_finding.fix_code is None
