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

    result = await static_tasks.update_bandit_finding_status(
        finding_id="finding-1",
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert result["status"] == "verified"
    assert finding.status == "verified"


@pytest.mark.asyncio
async def test_execute_bandit_scan_transitions_to_completed(monkeypatch):
    task = BanditScanTask(
        id="bandit-task-1",
        project_id="project-1",
        name="bandit",
        status="pending",
        target_path=".",
        severity_level="medium",
        confidence_level="medium",
    )
    fake_session = _FakeAsyncSession(task)
    monkeypatch.setattr(static_tasks, "async_session_factory", lambda: fake_session)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)

    def _fake_run_subprocess_with_tracking(scan_type, task_id, cmd, timeout):
        assert scan_type == "bandit"
        assert task_id == "bandit-task-1"
        assert timeout == 600
        report_path = cmd[cmd.index("-o") + 1]
        payload = {
            "results": [
                {
                    "test_id": "B602",
                    "test_name": "subprocess_popen_with_shell_equals_true",
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                    "filename": "/tmp/app/main.py",
                    "line_number": 42,
                    "code": "subprocess.Popen(cmd, shell=True)",
                    "issue_text": "subprocess call with shell=True identified",
                    "more_info": "https://bandit.readthedocs.io/",
                }
            ]
        }
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload))
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(
        static_tasks,
        "_run_subprocess_with_tracking",
        _fake_run_subprocess_with_tracking,
    )

    class _FakeLoop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    monkeypatch.setattr(static_tasks.asyncio, "get_event_loop", lambda: _FakeLoop())

    await static_tasks._execute_bandit_scan(
        task_id="bandit-task-1",
        project_root="/tmp",
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
    assert len(fake_session.findings) == 1
    assert fake_session.findings[0].file_path == "app/main.py"
