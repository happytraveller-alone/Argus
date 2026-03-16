"""Gitleaks 静态扫描后端单元测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import static_tasks_gitleaks
from app.models.gitleaks import GitleaksFinding, GitleaksScanTask


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    """用于 _execute_gitleaks_scan 的最小会话桩。"""

    def __init__(self, task: GitleaksScanTask):
        self.task = task
        self.findings = []
        self.commit_calls = 0
        self.rollback_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is GitleaksScanTask:
            return _ScalarOneOrNoneResult(self.task)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, GitleaksFinding):
            self.findings.append(obj)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


def test_normalize_gitleaks_runtime_config_defaults_to_unredacted_and_parses_strings():
    assert static_tasks_gitleaks._normalize_gitleaks_runtime_config({}) == {
        "reportFormat": "json",
        "redact": False,
        "customConfigToml": "",
    }
    assert static_tasks_gitleaks._normalize_gitleaks_runtime_config({"redact": True})["redact"] is True
    assert static_tasks_gitleaks._normalize_gitleaks_runtime_config({"redact": False})["redact"] is False
    assert static_tasks_gitleaks._normalize_gitleaks_runtime_config({"redact": "false"})["redact"] is False
    assert static_tasks_gitleaks._normalize_gitleaks_runtime_config({"redact": "TRUE"})["redact"] is True


def test_build_gitleaks_command_only_adds_redact_when_explicitly_enabled():
    base_kwargs = {
        "full_target_path": "/tmp/project",
        "report_file": "/tmp/report.json",
        "report_format": "json",
        "no_git": True,
        "config_file": None,
    }

    default_cmd = static_tasks_gitleaks._build_gitleaks_command(redact=False, **base_kwargs)
    assert "--redact" not in default_cmd
    assert "--no-git" in default_cmd

    redacted_cmd = static_tasks_gitleaks._build_gitleaks_command(redact=True, **base_kwargs)
    assert "--redact" in redacted_cmd


@pytest.mark.asyncio
async def test_execute_gitleaks_scan_keeps_match_content_and_masks_secret(monkeypatch):
    task = GitleaksScanTask(
        id="gitleaks-task-1",
        project_id="project-1",
        name="gitleaks",
        status="pending",
        target_path=".",
        no_git="true",
    )
    fake_session = _FakeAsyncSession(task)
    monkeypatch.setattr(static_tasks_gitleaks, "async_session_factory", lambda: fake_session)
    monkeypatch.setattr(static_tasks_gitleaks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_gitleaks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "_build_effective_gitleaks_config_toml",
        AsyncMock(return_value=None),
    )

    def _fake_run_subprocess_with_tracking(scan_type, task_id, cmd, timeout):
        assert scan_type == "gitleaks"
        assert task_id == "gitleaks-task-1"
        assert timeout == 600
        assert "--redact" not in cmd
        report_path = cmd[cmd.index("--report-path") + 1]
        payload = [
            {
                "RuleID": "generic-api-key",
                "Description": "possible api key",
                "File": "config/.env.production",
                "StartLine": 8,
                "EndLine": 8,
                "Secret": "ghp_example_secret",
                "Match": "ghp_example_secret",
                "Fingerprint": "gl:1",
            }
        ]
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        static_tasks_gitleaks,
        "_run_subprocess_with_tracking",
        _fake_run_subprocess_with_tracking,
    )

    class _FakeLoop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    monkeypatch.setattr(static_tasks_gitleaks.asyncio, "get_event_loop", lambda: _FakeLoop())

    await static_tasks_gitleaks._execute_gitleaks_scan(
        task_id="gitleaks-task-1",
        project_root="/tmp",
        target_path=".",
        no_git=True,
        runtime_config={},
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.files_scanned == 1
    assert len(fake_session.findings) == 1
    assert fake_session.findings[0].match == "ghp_example_secret"
    assert fake_session.findings[0].secret == "ghp_**********cret"
