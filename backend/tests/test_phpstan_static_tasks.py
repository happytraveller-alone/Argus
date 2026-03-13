"""PHPStan 静态扫描后端单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import static_tasks
from app.models.phpstan import PhpstanScanTask, PhpstanFinding


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    """用于 _execute_phpstan_scan 的最小会话桩。"""

    def __init__(self, task: PhpstanScanTask):
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
        if entity is PhpstanScanTask:
            return _ScalarOneOrNoneResult(self.task)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, PhpstanFinding):
            self.findings.append(obj)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


def test_parse_phpstan_output_payload_supports_empty_noise_and_json():
    parsed_empty = static_tasks._parse_phpstan_output_payload("")
    parsed_noise = static_tasks._parse_phpstan_output_payload("NOTICE...\n{\"files\":{}}")
    parsed_json = static_tasks._parse_phpstan_output_payload("{\"files\":{},\"totals\":{}}")

    assert parsed_empty == {}
    assert isinstance(parsed_noise, dict)
    assert isinstance(parsed_json, dict)

    with pytest.raises(ValueError):
        static_tasks._parse_phpstan_output_payload("{invalid")


@pytest.mark.asyncio
async def test_update_phpstan_finding_status_validation_and_success():
    finding = SimpleNamespace(id="finding-1", status="open")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    with pytest.raises(HTTPException) as exc_info:
        await static_tasks.update_phpstan_finding_status(
            finding_id="finding-1",
            status="bad_status",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
    assert exc_info.value.status_code == 400

    result = await static_tasks.update_phpstan_finding_status(
        finding_id="finding-1",
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert result["status"] == "verified"
    assert finding.status == "verified"


@pytest.mark.asyncio
async def test_execute_phpstan_scan_transitions_to_completed(monkeypatch):
    task = PhpstanScanTask(
        id="phpstan-task-1",
        project_id="project-1",
        name="phpstan",
        status="pending",
        target_path=".",
        level=5,
    )
    fake_session = _FakeAsyncSession(task)
    monkeypatch.setattr(static_tasks, "async_session_factory", lambda: fake_session)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)

    def _fake_run_subprocess_with_tracking(scan_type, task_id, cmd, timeout):
        assert scan_type == "phpstan"
        assert task_id == "phpstan-task-1"
        assert timeout == 600
        payload = {
            "totals": {"errors": 0, "file_errors": 2},
            "files": {
                "/workspace/app/A.php": {
                    "errors": 1,
                    "messages": [
                        {
                            "message": "Call to undefined method Foo::bar().",
                            "line": 21,
                            "identifier": "method.notFound",
                            "tip": "Did you mean baz()?",
                        }
                    ],
                },
                "/workspace/app/B.php": {
                    "errors": 1,
                    "messages": [
                        {
                            "message": "Property $id does not exist.",
                            "line": 7,
                            "identifier": "property.notFound",
                        }
                    ],
                },
            },
        }
        return SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(
        static_tasks,
        "_run_subprocess_with_tracking",
        _fake_run_subprocess_with_tracking,
    )

    class _FakeLoop:
        async def run_in_executor(self, _executor, fn):
            return fn()

    monkeypatch.setattr(static_tasks.asyncio, "get_event_loop", lambda: _FakeLoop())

    await static_tasks._execute_phpstan_scan(
        task_id="phpstan-task-1",
        project_root="/tmp",
        target_path=".",
        level=6,
    )

    assert task.status == "completed"
    assert task.level == 6
    assert task.total_findings == 2
    assert task.files_scanned == 2
    assert len(fake_session.findings) == 2
