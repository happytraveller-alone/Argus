from pathlib import Path

import pytest

from app.services.agent.task_findings import (
    _build_core_audit_exclude_patterns,
    _filter_bootstrap_findings,
)
import app.models.opengrep  # noqa: F401


def test_scope_filter_bridge_preserves_fnmatch_question_mark_and_char_class_support():
    patterns = _build_core_audit_exclude_patterns(["src/file?.py", "file[ab].py"])

    filtered = _filter_bootstrap_findings(
        [
            {"id": "drop-question", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/file1.py"},
            {"id": "drop-basename-class", "severity": "ERROR", "confidence": "HIGH", "file_path": "nested/filea.py"},
            {"id": "keep", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/file10.py"},
        ],
        exclude_patterns=patterns,
    )

    assert {item["id"] for item in filtered} == {"keep"}


def test_filter_bootstrap_findings_ignores_non_core_scope_paths():
    candidates = [
        {
            "id": "ok-src",
            "severity": "ERROR",
            "confidence": "HIGH",
            "file_path": "src/api.py",
        },
        {
            "id": "drop-tests",
            "severity": "ERROR",
            "confidence": "HIGH",
            "file_path": "tests/test_api.py",
        },
        {
            "id": "drop-hidden",
            "severity": "ERROR",
            "confidence": "HIGH",
            "file_path": ".github/workflows/pipeline.py",
        },
        {
            "id": "drop-config-yaml",
            "severity": "ERROR",
            "confidence": "HIGH",
            "file_path": "config/app.yaml",
        },
        {
            "id": "drop-settings-py",
            "severity": "ERROR",
            "confidence": "HIGH",
            "file_path": "app/settings.py",
        },
    ]

    filtered = _filter_bootstrap_findings(
        candidates,
        exclude_patterns=_build_core_audit_exclude_patterns([]),
    )

    assert {item["id"] for item in filtered} == {"ok-src"}


