from app.services.agent.bootstrap_seeds import (
    MAX_SEED_FINDINGS,
    _merge_seed_and_agent_findings,
    _normalize_seed_from_opengrep,
)


def test_normalize_seed_from_opengrep_maps_and_dedupes_candidates():
    seeds = _normalize_seed_from_opengrep(
        [
            {
                "id": "a",
                "file_path": "src/api.py",
                "line_start": "8",
                "line_end": "9",
                "severity": "ERROR",
                "confidence": "HIGH",
                "vulnerability_type": "sql_injection",
                "description": "danger",
                "code_snippet": "execute(sql)",
            },
            {
                "id": "dup",
                "file_path": "src/api.py",
                "line_start": 8,
                "severity": "WARNING",
                "confidence": "LOW",
                "vulnerability_type": "sql_injection",
            },
        ]
    )

    assert len(seeds) == 1
    first = seeds[0]
    assert first["file_path"] == "src/api.py"
    assert first["line_start"] == 8
    assert first["line_end"] == 9
    assert first["severity"] == "high"
    assert first["confidence"] == 0.8
    assert first["bootstrap_severity"] == "ERROR"
    assert first["bootstrap_confidence"] == "HIGH"


def test_normalize_seed_from_opengrep_truncates_to_max_seed_findings():
    seeds = _normalize_seed_from_opengrep(
        [
            {
                "id": str(index),
                "file_path": f"src/{index}.py",
                "line_start": 1,
                "severity": "INFO",
                "confidence": 0.1,
                "vulnerability_type": f"type-{index}",
            }
            for index in range(MAX_SEED_FINDINGS + 5)
        ]
    )

    assert len(seeds) == MAX_SEED_FINDINGS


def test_merge_seed_and_agent_findings_prefers_agent_payload_for_matching_key():
    merged = _merge_seed_and_agent_findings(
        [
            {
                "file_path": "src/api.py",
                "line_start": 12,
                "vulnerability_type": "sql_injection",
                "title": "seed-title",
                "confidence": 0.8,
            }
        ],
        [
            {
                "file_path": "src/api.py",
                "line_start": "12",
                "vulnerability_type": "sql_injection",
                "title": "agent-title",
                "severity": "critical",
            }
        ],
    )

    assert len(merged) == 1
    assert merged[0]["title"] == "agent-title"
    assert merged[0]["confidence"] == 0.8
    assert merged[0]["severity"] == "critical"
