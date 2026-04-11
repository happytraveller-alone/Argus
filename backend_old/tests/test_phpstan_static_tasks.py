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


def test_parse_phpstan_output_payload_supports_empty_noise_and_json():
    parsed_empty = static_tasks._parse_phpstan_output_payload("")
    parsed_noise = static_tasks._parse_phpstan_output_payload("NOTICE...\n{\"files\":{}}")
    parsed_bracket_noise = static_tasks._parse_phpstan_output_payload(
        "[warning] bootstrap log\n{\"files\":{},\"totals\":{}}"
    )
    parsed_json = static_tasks._parse_phpstan_output_payload("{\"files\":{},\"totals\":{}}")

    assert parsed_empty == {}
    assert isinstance(parsed_noise, dict)
    assert isinstance(parsed_bracket_noise, dict)
    assert isinstance(parsed_json, dict)

    with pytest.raises(ValueError):
        static_tasks._parse_phpstan_output_payload("{invalid")


def test_filter_phpstan_security_messages_keeps_security_findings_only():
    messages = [
        {
            "message": "User input reaches eval() and may cause code execution.",
            "line": 10,
            "identifier": "security.eval",
        },
        {
            "message": "Call to undefined method Foo::bar().",
            "line": 20,
            "identifier": "method.notFound",
        },
        {
            "message": "Potential XSS injection sink.",
            "line": 30,
            "identifier": "framework.security",
        },
        None,
        "bad",
    ]
    result = static_tasks._filter_phpstan_security_messages(messages)

    assert len(result["kept"]) == 2
    assert len(result["dropped"]) == 3


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

    with pytest.raises(HTTPException) as fixed_exc_info:
        await static_tasks.update_phpstan_finding_status(
            finding_id="finding-1",
            status="fixed",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
    assert fixed_exc_info.value.status_code == 400

    result = await static_tasks.update_phpstan_finding_status(
        finding_id="finding-1",
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert result["status"] == "verified"
    assert finding.status == "verified"


@pytest.mark.asyncio
async def test_get_phpstan_finding_returns_normalized_resolved_location(monkeypatch):
    task = SimpleNamespace(id="task-1", project_id="project-1")
    finding = SimpleNamespace(
        id="finding-1",
        scan_task_id="task-1",
        file_path="/workspace/demo/src/Service.php",
        line=21,
        message="User input may reach eval().",
        identifier="security.eval",
        tip=None,
        status="open",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(task),
            _ScalarOneOrNoneResult(finding),
        ]
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "_get_project_root",
        AsyncMock(return_value="/workspace/demo"),
    )

    result = await static_tasks.get_phpstan_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.file_path == "/workspace/demo/src/Service.php"
    assert result.line == 21
    assert result.resolved_file_path == "src/Service.php"
    assert result.resolved_line_start == 21


@pytest.mark.asyncio
async def test_execute_phpstan_scan_transitions_to_completed(monkeypatch, tmp_path):
    task = PhpstanScanTask(
        id="phpstan-task-1",
        project_id="project-1",
        name="phpstan",
        status="pending",
        target_path=".",
        level=5,
    )
    load_session = _FakeAsyncSession(task)
    persist_session = _FakeAsyncSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    monkeypatch.setattr(static_tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks._phpstan,
        "settings",
        SimpleNamespace(SCANNER_PHPSTAN_IMAGE="vulhunter/phpstan-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id,
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "project",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "output",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "logs",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "meta",
        raising=False,
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        payload = {
            "totals": {"errors": 0, "file_errors": 2},
            "files": {
                "/workspace/app/A.php": {
                    "errors": 1,
                    "messages": [
                        {
                            "message": "Untrusted data may reach eval() causing code execution.",
                            "line": 21,
                            "identifier": "security.eval",
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
        report_path = tmp_path / "scans" / "phpstan" / task.id / "output" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="phpstan-container-1",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(static_tasks._phpstan, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks._execute_phpstan_scan(
        task_id="phpstan-task-1",
        project_root=str(tmp_path),
        target_path=".",
        level=6,
    )

    assert task.status == "completed"
    assert task.level == 6
    assert task.total_findings == 1
    assert task.files_scanned == 2
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 1
    assert seen["spec"].image == "vulhunter/phpstan-runner:test"
    assert seen["spec"].command[:3] == ["php", "/opt/phpstan/phpstan", "analyse"]
    assert seen["spec"].capture_stdout_path == "output/report.json"


@pytest.mark.asyncio
async def test_execute_phpstan_scan_completes_when_all_findings_filtered(monkeypatch, tmp_path):
    task = PhpstanScanTask(
        id="phpstan-task-2",
        project_id="project-1",
        name="phpstan",
        status="pending",
        target_path=".",
        level=5,
    )
    load_session = _FakeAsyncSession(task)
    persist_session = _FakeAsyncSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    monkeypatch.setattr(static_tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks._phpstan,
        "settings",
        SimpleNamespace(SCANNER_PHPSTAN_IMAGE="vulhunter/phpstan-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id,
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "project",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "output",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "logs",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._phpstan,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "phpstan" / task.id / "meta",
        raising=False,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        payload = {
            "totals": {"errors": 0, "file_errors": 1},
            "files": {
                "/workspace/app/C.php": {
                    "errors": 1,
                    "messages": [
                        {
                            "message": "Property $id does not exist.",
                            "line": 6,
                            "identifier": "property.notFound",
                        }
                    ],
                },
            },
        }
        report_path = tmp_path / "scans" / "phpstan" / task.id / "output" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="phpstan-container-2",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(static_tasks._phpstan, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks._execute_phpstan_scan(
        task_id="phpstan-task-2",
        project_root=str(tmp_path),
        target_path=".",
        level=5,
    )

    assert task.status == "completed"
    assert task.total_findings == 0
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 0
