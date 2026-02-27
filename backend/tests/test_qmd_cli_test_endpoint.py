from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import verify_qmd_cli_runtime


@pytest.mark.asyncio
async def test_qmd_cli_runtime_returns_success(monkeypatch):
    monkeypatch.setattr(config_module.settings, "QMD_CLI_COMMAND", "npx -y @tobilu/qmd")

    def _fake_run_qmd_cli_check(*, name, command, timeout_seconds, cwd=None):
        del timeout_seconds, cwd
        return {
            "name": name,
            "success": True,
            "command": command,
            "exit_code": 0,
            "duration_ms": 5,
            "stdout": "ok",
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(config_module, "_run_qmd_cli_check", _fake_run_qmd_cli_check)

    response = await verify_qmd_cli_runtime(_current_user=SimpleNamespace(id="user-1"))

    assert response.success is True
    assert response.command_base == ["npx", "-y", "@tobilu/qmd"]
    assert [item.name for item in response.checks] == ["help", "status", "collection_list"]
    assert all(item.success is True for item in response.checks)


@pytest.mark.asyncio
async def test_qmd_cli_runtime_reports_partial_failure(monkeypatch):
    monkeypatch.setattr(config_module.settings, "QMD_CLI_COMMAND", "npx -y @tobilu/qmd")

    def _fake_run_qmd_cli_check(*, name, command, timeout_seconds, cwd=None):
        del command, timeout_seconds, cwd
        if name == "status":
            return {
                "name": name,
                "success": False,
                "command": ["npx", "-y", "@tobilu/qmd", "status"],
                "exit_code": 1,
                "duration_ms": 8,
                "stdout": "",
                "stderr": "status failed",
                "error": "execution_failed",
            }
        return {
            "name": name,
            "success": True,
            "command": ["npx", "-y", "@tobilu/qmd", name],
            "exit_code": 0,
            "duration_ms": 5,
            "stdout": "ok",
            "stderr": "",
            "error": None,
        }

    monkeypatch.setattr(config_module, "_run_qmd_cli_check", _fake_run_qmd_cli_check)

    response = await verify_qmd_cli_runtime(_current_user=SimpleNamespace(id="user-1"))

    assert response.success is False
    failures = [item for item in response.checks if not item.success]
    assert len(failures) == 1
    assert failures[0].name == "status"
