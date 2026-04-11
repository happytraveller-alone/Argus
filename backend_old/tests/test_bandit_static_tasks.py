"""Bandit 静态扫描后端单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import static_tasks
from app.models.bandit import BanditScanTask, BanditFinding


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    """用于 _execute_bandit_scan 的最小会话桩。"""

    def __init__(self, task: BanditScanTask):
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
        if entity is BanditScanTask:
            return _ScalarOneOrNoneResult(self.task)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, BanditFinding):
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


@pytest.mark.asyncio
async def test_parse_bandit_output_payload_supports_dict_and_list():
    payload_dict = {"results": [{"test_id": "B101"}, {"test_id": "B602"}]}
    payload_list = [{"test_id": "B101"}]

    parsed_from_dict = static_tasks._parse_bandit_output_payload(payload_dict)
    parsed_from_list = static_tasks._parse_bandit_output_payload(payload_list)

    assert len(parsed_from_dict) == 2
    assert parsed_from_dict[0]["test_id"] == "B101"
    assert len(parsed_from_list) == 1

    with pytest.raises(ValueError):
        static_tasks._parse_bandit_output_payload("invalid")


@pytest.mark.asyncio
async def test_update_bandit_finding_status_validation_and_success():
    finding = SimpleNamespace(id="finding-1", status="open")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    with pytest.raises(HTTPException) as exc_info:
        await static_tasks.update_bandit_finding_status(
            finding_id="finding-1",
            status="bad_status",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as fixed_exc_info:
        await static_tasks.update_bandit_finding_status(
            finding_id="finding-1",
            status="fixed",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
    assert fixed_exc_info.value.status_code == 400

    result = await static_tasks.update_bandit_finding_status(
        finding_id="finding-1",
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert result["status"] == "verified"
    assert finding.status == "verified"


@pytest.mark.asyncio
async def test_get_bandit_finding_returns_resolved_location_payload():
    task = SimpleNamespace(id="task-1", project_id="project-1")
    finding = SimpleNamespace(
        id="finding-1",
        scan_task_id="task-1",
        test_id="B602",
        test_name="subprocess_popen_with_shell_equals_true",
        issue_severity="HIGH",
        issue_confidence="HIGH",
        file_path="src/app/main.py",
        line_number=42,
        code_snippet="subprocess.Popen(cmd, shell=True)",
        issue_text="shell=True risk",
        more_info="https://bandit.readthedocs.io/",
        status="open",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(task),
            _ScalarOneOrNoneResult(finding),
        ]
    )

    result = await static_tasks.get_bandit_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.file_path == "src/app/main.py"
    assert result.line_number == 42
    assert result.resolved_file_path == "src/app/main.py"
    assert result.resolved_line_start == 42


@pytest.mark.asyncio
async def test_execute_bandit_scan_transitions_to_completed(monkeypatch, tmp_path):
    task = BanditScanTask(
        id="bandit-task-1",
        project_id="project-1",
        name="bandit",
        status="pending",
        target_path=".",
        severity_level="medium",
        confidence_level="medium",
    )
    load_session = _FakeAsyncSession(task)
    persist_session = _FakeAsyncSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    workspace_dir = SimpleNamespace()
    monkeypatch.setattr(static_tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks._bandit,
        "settings",
        SimpleNamespace(SCANNER_BANDIT_IMAGE="vulhunter/bandit-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: tmp_path / "scans" / "bandit" / task.id,
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "bandit" / task.id / "project",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "bandit" / task.id / "output",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "bandit" / task.id / "logs",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "bandit" / task.id / "meta",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._bandit,
        "_resolve_bandit_scan_rule_ids",
        AsyncMock(return_value=["B602", "B101"]),
    )

    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        report_path = tmp_path / "scans" / "bandit" / task.id / "output" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "results": [
                {
                    "test_id": "B602",
                    "test_name": "subprocess_popen_with_shell_equals_true",
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                    "filename": "/scan/project/app/main.py",
                    "line_number": 42,
                    "code": "subprocess.Popen(cmd, shell=True)",
                    "issue_text": "subprocess call with shell=True identified",
                    "more_info": "https://bandit.readthedocs.io/",
                }
            ]
        }
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="bandit-container-1",
            exit_code=1,
            stdout_path=str(tmp_path / "scans" / "bandit" / task.id / "logs" / "stdout.log"),
            stderr_path=str(tmp_path / "scans" / "bandit" / task.id / "logs" / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(static_tasks._bandit, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks._execute_bandit_scan(
        task_id="bandit-task-1",
        project_root=str(tmp_path),
        target_path=".",
        severity_level="medium",
        confidence_level="medium",
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.high_count == 1
    assert task.medium_count == 0
    assert task.low_count == 0
    assert task.files_scanned == 1
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].file_path == "app/main.py"
    assert seen["spec"].image == "vulhunter/bandit-runner:test"
    assert seen["spec"].command[0] == "bandit"
    assert seen["spec"].command[seen["spec"].command.index("-o") + 1] == "/scan/output/report.json"
    assert "-t" in seen["spec"].command
    assert seen["spec"].command[seen["spec"].command.index("-t") + 1] == "B602,B101"
