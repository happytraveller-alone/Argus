from pathlib import Path

import pytest

from app.services.agent.task_findings import (
    _build_core_audit_exclude_patterns,
    _filter_bootstrap_findings,
)
from app.services.agent.tools.smart_scan_tool import SmartScanTool
import app.models.opengrep  # noqa: F401


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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

@pytest.mark.asyncio
async def test_smart_scan_collect_files_ignores_hidden_test_and_config_scope(tmp_path):
    _write_file(tmp_path / "src" / "controller.py", "def x():\n    return 1\n")
    _write_file(tmp_path / "tests" / "test_controller.py", "def test_x():\n    pass\n")
    _write_file(tmp_path / ".github" / "scanner.py", "def hidden():\n    return 0\n")
    _write_file(tmp_path / ".vscode" / "ext.ts", "router.get('/x', () => {})\n")
    _write_file(tmp_path / "app" / "settings.py", "DEBUG=True\n")

    tool = SmartScanTool(
        project_root=str(tmp_path),
        exclude_patterns=_build_core_audit_exclude_patterns([]),
    )
    files = await tool._collect_files(target=".", max_files=100, quick_mode=False)

    assert "src/controller.py" in files
    assert "tests/test_controller.py" not in files
    assert ".github/scanner.py" not in files
    assert ".vscode/ext.ts" not in files
    assert "app/settings.py" not in files
