from pathlib import Path

import pytest

from app.api.v1.endpoints.agent_tasks import (
    _build_core_audit_exclude_patterns,
    _collect_project_info,
    _discover_entry_points_deterministic,
    _filter_bootstrap_findings,
)
from app.services.agent.tools.smart_scan_tool import SmartScanTool
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def test_discover_entry_points_deterministic_ignores_hidden_test_and_config_paths(tmp_path):
    _write_file(
        tmp_path / "src" / "main.py",
        '@app.get("/alive")\ndef alive():\n    return "ok"\n',
    )
    _write_file(
        tmp_path / "tests" / "test_api.py",
        '@app.get("/from-test")\ndef from_test():\n    return "bad"\n',
    )
    _write_file(
        tmp_path / ".github" / "scanner.py",
        '@app.get("/from-hidden")\ndef from_hidden():\n    return "bad"\n',
    )
    _write_file(
        tmp_path / "app" / "settings.py",
        '@app.get("/from-settings")\ndef from_settings():\n    return "bad"\n',
    )
    _write_file(
        tmp_path / ".vscode" / "ext.ts",
        "router.get('/from-vscode', () => {})\n",
    )

    result = _discover_entry_points_deterministic(str(tmp_path))
    files = {item["file"] for item in result["entry_points"]}

    assert "src/main.py" in files
    assert "tests/test_api.py" not in files
    assert ".github/scanner.py" not in files
    assert "app/settings.py" not in files
    assert ".vscode/ext.ts" not in files


@pytest.mark.asyncio
async def test_collect_project_info_ignores_hidden_test_and_config_scope(tmp_path):
    _write_file(tmp_path / "src" / "main.py", "def main():\n    return 1\n")
    _write_file(tmp_path / "src" / "util.py", "def util():\n    return 2\n")
    _write_file(tmp_path / "tests" / "test_main.py", "def test_main():\n    pass\n")
    _write_file(tmp_path / ".vscode" / "tasks.json", "{}\n")
    _write_file(tmp_path / ".github" / "workflows" / "ci.yml", "name: ci\n")
    _write_file(tmp_path / "app" / "settings.py", "DEBUG=True\n")
    _write_file(tmp_path / "config" / "app.yml", "port: 8080\n")

    info = await _collect_project_info(str(tmp_path), "demo")

    assert info["file_count"] == 2
    assert "Python" in info["languages"]
    assert "src" in info["structure"]["directories"]
    assert "tests" not in info["structure"]["directories"]
    assert ".github" not in info["structure"]["directories"]
    assert ".vscode" not in info["structure"]["directories"]
    assert "app/settings.py" not in info["structure"]["files"]


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
