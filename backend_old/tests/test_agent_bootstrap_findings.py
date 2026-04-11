from types import SimpleNamespace

from app.services.agent.bootstrap_findings import (
    _build_bootstrap_confidence_map_from_rules,
    _dedupe_bootstrap_findings,
    _normalize_bootstrap_finding_from_gitleaks_payload,
    _normalize_bootstrap_finding_from_opengrep_payload,
    _parse_bootstrap_gitleaks_output,
    _parse_bootstrap_opengrep_output,
)


def test_parse_bootstrap_opengrep_output_accepts_results_wrapper():
    output = _parse_bootstrap_opengrep_output('{"results":[{"check_id":"rule-1"}]}')

    assert output == [{"check_id": "rule-1"}]


def test_build_bootstrap_confidence_map_uses_rule_id_and_name():
    mapping = _build_bootstrap_confidence_map_from_rules(
        [
            SimpleNamespace(id="rules.sql.injection", name="sql.injection", confidence="high"),
            SimpleNamespace(id="plain-id", name=None, confidence="medium"),
        ]
    )

    assert mapping["rules.sql.injection"] == "HIGH"
    assert mapping["injection"] == "HIGH"
    assert mapping["sql.injection"] == "HIGH"
    assert mapping["plain-id"] == "MEDIUM"


def test_normalize_bootstrap_finding_from_opengrep_payload_uses_confidence_map_fallback():
    finding = _normalize_bootstrap_finding_from_opengrep_payload(
        {
            "check_id": "rules.sql.injection",
            "path": "src/api.py",
            "start": {"line": 8},
            "end": {"line": 9},
            "extra": {"message": "danger", "severity": "error", "lines": "exec()"},
        },
        {"rules.sql.injection": "HIGH"},
        0,
    )

    assert finding["id"] == "rules.sql.injection"
    assert finding["file_path"] == "src/api.py"
    assert finding["line_start"] == 8
    assert finding["line_end"] == 9
    assert finding["severity"] == "ERROR"
    assert finding["confidence"] == "HIGH"


def test_normalize_bootstrap_finding_from_gitleaks_payload_normalizes_relative_path():
    finding = _normalize_bootstrap_finding_from_gitleaks_payload(
        {
            "RuleID": "generic-api-key",
            "Description": "secret candidate",
            "File": "/scan/project/src/secret.py",
            "StartLine": 3,
            "EndLine": 4,
            "Match": "token=abc",
        },
        2,
    )

    assert finding["id"] == "gitleaks-2"
    assert finding["file_path"] == "src/secret.py"
    assert finding["line_start"] == 3
    assert finding["line_end"] == 4
    assert finding["confidence"] == "HIGH"


def test_parse_bootstrap_gitleaks_output_accepts_findings_wrapper():
    output = _parse_bootstrap_gitleaks_output('{"findings":[{"RuleID":"x"}]}')

    assert output == [{"RuleID": "x"}]


def test_dedupe_bootstrap_findings_collapses_same_location_type_and_source():
    deduped = _dedupe_bootstrap_findings(
        [
            {
                "file_path": "src/a.py",
                "line_start": 5,
                "vulnerability_type": "sql",
                "source": "opengrep_bootstrap",
            },
            {
                "file_path": "src/a.py",
                "line_start": 5,
                "vulnerability_type": "sql",
                "source": "opengrep_bootstrap",
            },
            {
                "file_path": "src/a.py",
                "line_start": 5,
                "vulnerability_type": "sql",
                "source": "gitleaks_bootstrap",
            },
        ]
    )

    assert len(deduped) == 2
