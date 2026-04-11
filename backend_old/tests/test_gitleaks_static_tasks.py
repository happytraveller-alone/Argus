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

    async def close(self):
        return None


class _SessionFactory:
    def __init__(self, *sessions):
        self._sessions = list(sessions)
        self.calls = 0

    def __call__(self):
        session = self._sessions[min(self.calls, len(self._sessions) - 1)]
        self.calls += 1
        return session


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
async def test_execute_gitleaks_scan_keeps_match_content_and_masks_secret(monkeypatch, tmp_path):
    task = GitleaksScanTask(
        id="gitleaks-task-1",
        project_id="project-1",
        name="gitleaks",
        status="pending",
        target_path=".",
        no_git="true",
    )
    load_session = _FakeAsyncSession(task)
    persist_session = _FakeAsyncSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    monkeypatch.setattr(static_tasks_gitleaks, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_gitleaks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_gitleaks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "settings",
        SimpleNamespace(SCANNER_GITLEAKS_IMAGE="vulhunter/gitleaks-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: tmp_path / "scans" / "gitleaks" / task.id,
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "gitleaks" / task.id / "project",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "gitleaks" / task.id / "output",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "gitleaks" / task.id / "logs",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "gitleaks" / task.id / "meta",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks_gitleaks,
        "_build_effective_gitleaks_config_toml",
        AsyncMock(return_value=None),
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        assert "--redact" not in spec.command
        report_path = tmp_path / "scans" / "gitleaks" / task.id / "output" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
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
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="gitleaks-container-1",
            exit_code=0,
            stdout_path=str(tmp_path / "scans" / "gitleaks" / task.id / "logs" / "stdout.log"),
            stderr_path=str(tmp_path / "scans" / "gitleaks" / task.id / "logs" / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(static_tasks_gitleaks, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks_gitleaks._execute_gitleaks_scan(
        task_id="gitleaks-task-1",
        project_root=str(tmp_path),
        target_path=".",
        no_git=True,
        runtime_config={},
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.files_scanned == 1
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].match == "ghp_example_secret"
    assert persist_session.findings[0].secret == "ghp_**********cret"
    assert seen["spec"].image == "vulhunter/gitleaks-runner:test"
    assert seen["spec"].command[0] == "gitleaks"
    assert seen["spec"].command[seen["spec"].command.index("--report-path") + 1] == "/scan/output/report.json"
