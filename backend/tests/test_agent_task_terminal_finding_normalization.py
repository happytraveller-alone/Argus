from types import SimpleNamespace
import sys
import types

if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.errors = types.SimpleNamespace(
        DockerException=Exception,
        NotFound=Exception,
    )
    docker_stub.from_env = lambda: None
    sys.modules["docker"] = docker_stub

from app.api.v1.endpoints import agent_tasks_execution as execution_module
from app.models.agent_task import FindingStatus


def _make_finding(
    *,
    status: str,
    is_verified: bool,
    verdict: str,
    authenticity: str,
):
    return SimpleNamespace(
        status=status,
        is_verified=is_verified,
        verified_at="2026-04-09T08:00:00Z" if is_verified else None,
        verification_result={
            "status": status,
            "verdict": verdict,
            "authenticity": authenticity,
            "verification_stage_completed": True,
        },
    )


def test_normalize_terminal_findings_resets_all_automatic_states_to_needs_review():
    findings = [
        _make_finding(
            status=FindingStatus.VERIFIED,
            is_verified=True,
            verdict="confirmed",
            authenticity="confirmed",
        ),
        _make_finding(
            status=FindingStatus.LIKELY,
            is_verified=False,
            verdict="likely",
            authenticity="likely",
        ),
        _make_finding(
            status=FindingStatus.UNCERTAIN,
            is_verified=False,
            verdict="uncertain",
            authenticity="uncertain",
        ),
        _make_finding(
            status=FindingStatus.FALSE_POSITIVE,
            is_verified=False,
            verdict="false_positive",
            authenticity="false_positive",
        ),
        _make_finding(
            status=FindingStatus.NEEDS_REVIEW,
            is_verified=False,
            verdict="blocked",
            authenticity="blocked",
        ),
    ]

    normalized = execution_module._normalize_terminal_agent_findings(findings)

    assert normalized == findings
    for item in findings:
        assert item.status == FindingStatus.NEEDS_REVIEW
        assert item.is_verified is False
        assert item.verified_at is None
        assert item.verification_result["status"] == FindingStatus.NEEDS_REVIEW
        assert item.verification_result["verification_stage_completed"] is True

    assert findings[0].verification_result["verdict"] == "confirmed"
    assert findings[1].verification_result["verdict"] == "likely"
    assert findings[2].verification_result["verdict"] == "uncertain"
    assert findings[3].verification_result["verdict"] == "false_positive"
    assert findings[4].verification_result["verdict"] == "blocked"
