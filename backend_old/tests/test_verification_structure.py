"""Regression tests for the nested verification_result structure."""

import pytest


def check_finding_structure(finding):
    """Validate that a finding matches the SaveFindings verification contract."""

    issues = []

    verification_result_payload_input = finding.get("verification_result")
    if not isinstance(verification_result_payload_input, dict):
        issues.append("missing_verification_result: finding.get('verification_result') is not dict")
        return issues

    authenticity_raw = (
        finding.get("authenticity")
        or finding.get("verdict")
        or verification_result_payload_input.get("authenticity")
        or verification_result_payload_input.get("verdict")
    )
    reachability_raw = (
        finding.get("reachability")
        or verification_result_payload_input.get("reachability")
    )
    evidence_raw = (
        finding.get("verification_details")
        or finding.get("verification_evidence")
        or verification_result_payload_input.get("verification_details")
        or verification_result_payload_input.get("verification_evidence")
        or verification_result_payload_input.get("evidence")
    )

    if not authenticity_raw:
        issues.append("missing_authenticity: no verdict found")
    if not reachability_raw:
        issues.append("missing_reachability: no reachability found")
    if not evidence_raw:
        issues.append("missing_evidence: no verification_evidence found")

    if issues:
        return issues

    authenticity = str(authenticity_raw).strip().lower()
    if authenticity not in {"confirmed", "likely", "false_positive"}:
        issues.append(f"invalid_verdict: {authenticity} not in valid values")

    reachability = str(reachability_raw).strip().lower()
    if reachability not in {"reachable", "likely_reachable", "unreachable"}:
        issues.append(f"invalid_reachability: {reachability} not in valid values")

    return issues


OLD_FORMAT_FINDING = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "verdict": "confirmed",
    "confidence": 0.92,
    "reachability": "reachable",
    "verification_evidence": "通过fuzzing验证",
    "cwe_id": "CWE-1333",
}

NEW_FORMAT_FINDING = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "verification_result": {
        "verdict": "confirmed",
        "confidence": 0.92,
        "reachability": "reachable",
        "verification_evidence": "通过fuzzing验证",
    },
    "suggestion": "使用regex库替代re.search",
}

HYBRID_FORMAT_FINDING = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "verdict": "confirmed",
    "confidence": 0.92,
    "reachability": "reachable",
    "verification_evidence": "通过fuzzing验证",
    "verification_result": {
        "verdict": "confirmed",
        "confidence": 0.92,
        "reachability": "reachable",
        "verification_evidence": "通过fuzzing验证",
    },
    "suggestion": "使用regex库替代re.search",
}

MISSING_VERIFICATION_RESULT = {
    "file_path": "server/app.py",
    "line_start": 36,
    "line_end": 36,
    "title": "ReDoS漏洞",
    "cwe_id": "CWE-1333",
    "suggestion": "修复建议",
}


@pytest.mark.parametrize(
    ("finding", "expected_issue"),
    [
        (OLD_FORMAT_FINDING, "missing_verification_result: finding.get('verification_result') is not dict"),
        (MISSING_VERIFICATION_RESULT, "missing_verification_result: finding.get('verification_result') is not dict"),
    ],
)
def test_verification_structure_rejects_findings_without_nested_verification_result(
    finding,
    expected_issue,
):
    issues = check_finding_structure(finding)

    assert issues == [expected_issue]


@pytest.mark.parametrize("finding", [NEW_FORMAT_FINDING, HYBRID_FORMAT_FINDING])
def test_verification_structure_accepts_nested_verification_result_formats(finding):
    issues = check_finding_structure(finding)

    assert issues == []
