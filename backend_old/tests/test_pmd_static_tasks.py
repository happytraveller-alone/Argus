"""PMD 静态扫描后端单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import static_tasks
from app.models.pmd_scan import PmdFinding, PmdScanTask


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, task: PmdScanTask):
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
        if entity is PmdScanTask:
            return _ScalarOneOrNoneResult(self.task)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, PmdFinding):
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
async def test_update_pmd_finding_status_validation_and_success():
    finding = SimpleNamespace(id="finding-1", status="open")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    with pytest.raises(HTTPException) as exc_info:
        await static_tasks.update_pmd_finding_status(
            finding_id="finding-1",
            status="bad_status",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
    assert exc_info.value.status_code == 400

    result = await static_tasks.update_pmd_finding_status(
        finding_id="finding-1",
        status="verified",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert result["status"] == "verified"
    assert finding.status == "verified"


@pytest.mark.asyncio
async def test_get_pmd_finding_returns_resolved_location_payload():
    task = SimpleNamespace(id="task-1", project_id="project-1")
    finding = SimpleNamespace(
        id="finding-1",
        scan_task_id="task-1",
        file_path="src/main/java/App.java",
        begin_line=21,
        end_line=21,
        rule="HardCodedCryptoKey",
        ruleset="Security",
        priority=2,
        message="Hard coded key detected.",
        status="open",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneOrNoneResult(task),
            _ScalarOneOrNoneResult(finding),
        ]
    )

    result = await static_tasks.get_pmd_finding(
        task_id="task-1",
        finding_id="finding-1",
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.file_path == "src/main/java/App.java"
    assert result.begin_line == 21
    assert result.resolved_file_path == "src/main/java/App.java"
    assert result.resolved_line_start == 21


@pytest.mark.asyncio
async def test_execute_pmd_scan_transitions_to_completed(monkeypatch, tmp_path):
    task = PmdScanTask(
        id="pmd-task-1",
        project_id="project-1",
        name="pmd",
        status="pending",
        target_path=".",
        ruleset="security",
    )
    load_session = _FakeAsyncSession(task)
    persist_session = _FakeAsyncSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    monkeypatch.setattr(static_tasks, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        static_tasks._pmd,
        "settings",
        SimpleNamespace(SCANNER_PMD_IMAGE="vulhunter/pmd-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._pmd,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: tmp_path / "scans" / "pmd" / task.id,
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._pmd,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "pmd" / task.id / "project",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._pmd,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "pmd" / task.id / "output",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._pmd,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "pmd" / task.id / "logs",
        raising=False,
    )
    monkeypatch.setattr(
        static_tasks._pmd,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: tmp_path / "scans" / "pmd" / task.id / "meta",
        raising=False,
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        report_path = tmp_path / "scans" / "pmd" / task.id / "output" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "files": [
                {
                    "filename": "/scan/project/src/main/java/App.java",
                    "violations": [
                        {
                            "beginline": 21,
                            "endline": 21,
                            "rule": "HardCodedCryptoKey",
                            "ruleset": "Security",
                            "priority": 2,
                            "message": "Hard coded key detected.",
                        }
                    ],
                }
            ]
        }
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="pmd-container-1",
            exit_code=4,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(static_tasks._pmd, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks._execute_pmd_scan(
        task_id="pmd-task-1",
        project_root=str(tmp_path),
        target_path=".",
        ruleset="security",
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.files_scanned == 1
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].priority == 2
    assert seen["spec"].image == "vulhunter/pmd-runner:test"
    assert seen["spec"].command[:2] == ["pmd", "check"]
