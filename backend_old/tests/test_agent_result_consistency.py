from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent.task_findings import _save_findings
from app.models.agent_task import FindingStatus
import app.models.opengrep  # noqa: F401


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


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
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
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
    assert saved_finding.status == FindingStatus.NEEDS_REVIEW
    assert saved_finding.is_verified is False
    assert saved_finding.verified_at is None
    assert saved_finding.verdict == "confirmed"
    assert saved_finding.verification_result["authenticity"] == "confirmed"
    assert saved_finding.verification_result["status"] == FindingStatus.NEEDS_REVIEW
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
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
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
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
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
    assert saved_finding.status == FindingStatus.NEEDS_REVIEW
    assert saved_finding.is_verified is False
    assert saved_finding.verification_result["status"] == FindingStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_save_findings_normalizes_legacy_uncertain_status_to_likely_and_keeps_rich_fields(tmp_path):
    source_file = tmp_path / "src" / "draw.c"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "void ClonePolygonEdgesTLS(void) {",
                "    edge = clone_edge(src);",
                "    destroy_edge(edge);",
                "}",
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
            "title": "draw.c中的ClonePolygonEdgesTLS潜在双重释放",
            "severity": "high",
            "vulnerability_type": "memory_corruption",
            "file_path": "src/draw.c",
            "line_start": 2,
            "line_end": 3,
            "function_name": "ClonePolygonEdgesTLS",
            "description": "复制后的指针在异常路径可能重复释放。",
            "status": "uncertain",
            "confidence": 0.74,
            "source": "图像绘制参数",
            "sink": "destroy_edge(edge)",
            "dataflow_path": ["ParseCommand", "ClonePolygonEdgesTLS", "destroy_edge"],
            "cvss_score": 7.8,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H",
            "suggestion": "复制后转移所有权并增加释放保护。",
            "poc_code": "int main(void) { return 0; }",
            "verification_result": {
                "authenticity": "likely",
                "status": "uncertain",
                "reachability": "likely_reachable",
                "evidence": "fuzz harness observed repeated free attempts",
                "verification_evidence": "fuzz harness observed repeated free attempts",
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-rich-save",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == "likely"
    assert saved_finding.verification_result["status"] == "likely"
    assert saved_finding.source == "图像绘制参数"
    assert saved_finding.sink == "destroy_edge(edge)"
    assert isinstance(saved_finding.dataflow_path, list)
    assert "ClonePolygonEdgesTLS" in " ".join(saved_finding.dataflow_path)
    assert saved_finding.cvss_score == 7.8
    assert saved_finding.cvss_vector == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H"
    assert saved_finding.suggestion == "复制后转移所有权并增加释放保护。"
    assert saved_finding.has_poc is True
    assert saved_finding.poc_code == "int main(void) { return 0; }"


@pytest.mark.asyncio
async def test_save_findings_corrects_declared_function_range_with_snippet_anchor(tmp_path):
    source_file = tmp_path / "src" / "service.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def helper(value):",
                "    return value + 1",
                "",
                "def target_handler(user_input):",
                "    prefix = 'safe'",
                "    cmd = user_input.strip()",
                "    return prefix + cmd",
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
            "title": "target handler command injection",
            "severity": "high",
            "vulnerability_type": "command_injection",
            "file_path": "src/service.py",
            "line_start": 2,
            "line_end": 2,
            "code_snippet": "cmd = user_input.strip()",
            "function_start_line": 1,
            "function_end_line": 2,
            "verification_result": {
                "authenticity": "confirmed",
                "reachability": "reachable",
                "verification_evidence": "manual review confirms untrusted input reaches command execution",
                "context_start_line": 900,
                "context_end_line": 920,
                "reachability_target": {
                    "function": "target_handler",
                    "start_line": 1,
                    "end_line": 2,
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-function-range-correction",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.line_start == 4
    assert saved_finding.line_end == 4
    reachability_target = saved_finding.verification_result.get("reachability_target") or {}
    assert reachability_target.get("function") == "target_handler"
    assert reachability_target.get("start_line") == 4
    assert reachability_target.get("end_line") == 7
    function_range_validation = (
        saved_finding.verification_result.get("function_range_validation") or {}
    )
    assert function_range_validation.get("declared_start_line") == 1
    assert function_range_validation.get("declared_end_line") == 2
    assert function_range_validation.get("resolved_start_line") == 4
    assert function_range_validation.get("resolved_end_line") == 7
    assert function_range_validation.get("anchor_from_snippet") is True
    assert function_range_validation.get("correction_applied") is True
    assert function_range_validation.get("hit_line_outside_function") is True
    assert function_range_validation.get("hit_line_correction_applied") is True
    assert function_range_validation.get("original_line_start") == 2
    assert function_range_validation.get("corrected_line_start") == 4
    assert (
        function_range_validation.get("hit_line_correction_reason")
        == "outside_function_range_align_to_function_start"
    )
    assert saved_finding.verification_result.get("context_start_line") == 1
    assert saved_finding.verification_result.get("context_end_line") == 7
    assert "def target_handler(user_input):" in (saved_finding.code_context or "")


@pytest.mark.asyncio
async def test_save_findings_validates_function_range_for_false_positive_when_file_resolvable(
    tmp_path,
):
    source_file = tmp_path / "src" / "validator.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def alpha(data):",
                "    return data",
                "",
                "def beta(payload):",
                "    text = payload.strip()",
                "    return text",
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
            "title": "false positive sample",
            "severity": "medium",
            "vulnerability_type": "xss",
            "file_path": "src/validator.py",
            "line_start": 1,
            "line_end": 1,
            "code_snippet": "text = payload.strip()",
            "verification_result": {
                "authenticity": "false_positive",
                "status": "false_positive",
                "verification_evidence": "manual verification shows payload is sanitized before output",
                "context_start_line": 900,
                "context_end_line": 920,
                "reachability_target": {
                    "function": "beta",
                    "start_line": 1,
                    "end_line": 1,
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-fp-function-range-validation",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == FindingStatus.FALSE_POSITIVE
    assert saved_finding.line_start == 4
    assert saved_finding.line_end == 4
    reachability_target = saved_finding.verification_result.get("reachability_target") or {}
    assert reachability_target.get("function") == "beta"
    assert reachability_target.get("start_line") == 4
    assert reachability_target.get("end_line") == 6
    function_range_validation = (
        saved_finding.verification_result.get("function_range_validation") or {}
    )
    assert function_range_validation.get("hit_line_outside_function") is True
    assert function_range_validation.get("hit_line_correction_applied") is True
    assert saved_finding.verification_result.get("context_start_line") == 1
    assert saved_finding.verification_result.get("context_end_line") == 6
    assert "def beta(payload):" in (saved_finding.code_context or "")


@pytest.mark.asyncio
async def test_save_findings_keeps_hit_line_when_it_is_inside_function_range(tmp_path):
    source_file = tmp_path / "src" / "inside_case.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def guard(flag):",
                "    if flag:",
                "        return 1",
                "    return 0",
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
            "title": "inside range case",
            "severity": "medium",
            "vulnerability_type": "business_logic",
            "file_path": "src/inside_case.py",
            "line_start": 2,
            "line_end": 2,
            "verification_result": {
                "authenticity": "likely",
                "reachability": "likely_reachable",
                "verification_evidence": "path condition can be controlled by attacker input flow",
                "context_start_line": 900,
                "context_end_line": 920,
                "reachability_target": {
                    "function": "guard",
                    "start_line": 1,
                    "end_line": 4,
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-hit-line-inside",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.line_start == 2
    assert saved_finding.line_end == 2
    function_range_validation = (
        saved_finding.verification_result.get("function_range_validation") or {}
    )
    assert function_range_validation.get("hit_line_outside_function") is False
    assert function_range_validation.get("hit_line_correction_applied") is False
    assert function_range_validation.get("corrected_line_start") == 2
    assert function_range_validation.get("corrected_line_end") == 2
    assert saved_finding.verification_result.get("context_start_line") == 1
    assert saved_finding.verification_result.get("context_end_line") == 4
    assert "def guard(flag):" in (saved_finding.code_context or "")


@pytest.mark.asyncio
async def test_save_findings_skips_hit_line_correction_when_function_range_missing(tmp_path):
    source_file = tmp_path / "src" / "missing_range.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def f(payload):",
                "    return payload",
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
            "title": "missing range case",
            "severity": "low",
            "vulnerability_type": "idor",
            "file_path": "src/missing_range.py",
            "line_start": 1,
            "line_end": 1,
            "verification_result": {
                "authenticity": "likely",
                "reachability": "unknown",
                "verification_evidence": "insufficient context but finding should still be persisted",
                "reachability_target": {
                    "function": "f",
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-hit-line-missing-range",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.line_start == 1
    assert saved_finding.line_end == 1
    function_range_validation = (
        saved_finding.verification_result.get("function_range_validation") or {}
    )
    assert (
        function_range_validation.get("hit_line_correction_skipped_reason")
        == "missing_function_range"
    )
    assert function_range_validation.get("hit_line_correction_applied") is False
    assert saved_finding.verification_result.get("context_start_line") == 1
    assert saved_finding.verification_result.get("context_end_line") == 2


@pytest.mark.asyncio
async def test_save_findings_aligns_missing_hit_line_to_function_start(tmp_path):
    source_file = tmp_path / "src" / "missing_hit.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def check(payload):",
                "    value = payload.strip()",
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
            "title": "missing hit line case",
            "severity": "low",
            "vulnerability_type": "xss",
            "file_path": "src/missing_hit.py",
            "line_start": None,
            "line_end": None,
            "verification_result": {
                "authenticity": "false_positive",
                "status": "false_positive",
                "verification_evidence": "line not provided by upstream payload",
                "reachability_target": {
                    "function": "check",
                    "start_line": 1,
                    "end_line": 3,
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-missing-hit-line",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.line_start == 1
    assert saved_finding.line_end == 1
    function_range_validation = (
        saved_finding.verification_result.get("function_range_validation") or {}
    )
    assert function_range_validation.get("hit_line_correction_applied") is True
    assert (
        function_range_validation.get("hit_line_correction_reason")
        == "missing_hit_line_align_to_function_start"
    )
    assert (
        function_range_validation.get("hit_line_correction_engine")
        == "align_helper_v1"
    )
    assert (
        function_range_validation.get("hit_line_correction_from_unified_helper")
        is True
    )
    assert function_range_validation.get("corrected_line_start") == 1
    assert function_range_validation.get("corrected_line_end") == 1


@pytest.mark.asyncio
async def test_save_findings_clears_stale_context_lines_when_file_unavailable_for_false_positive(
    tmp_path,
):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    findings = [
        {
            "title": "fp without local file",
            "severity": "low",
            "vulnerability_type": "xss",
            "file_path": "src/not_exists.py",
            "line_start": 10,
            "line_end": 10,
            "verification_result": {
                "authenticity": "false_positive",
                "status": "false_positive",
                "verification_evidence": "no runtime risk",
                "context_start_line": 900,
                "context_end_line": 920,
                "reachability_target": {
                    "function": "missing",
                },
            },
        }
    ]

    saved_count = await _save_findings(
        db,
        task_id="task-fp-missing-source-context",
        findings=findings,
        project_root=str(tmp_path),
        save_diagnostics={},
    )

    assert saved_count == 1
    saved_finding = db.add.call_args.args[0]
    assert saved_finding.status == FindingStatus.FALSE_POSITIVE
    assert saved_finding.verification_result.get("context_start_line") is None
    assert saved_finding.verification_result.get("context_end_line") is None
