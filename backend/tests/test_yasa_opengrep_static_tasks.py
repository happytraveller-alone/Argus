import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import static_tasks_opengrep
from app.api.v1.endpoints import static_tasks_yasa
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.yasa import YasaFinding, YasaScanTask


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeYasaSession:
    def __init__(self, task: YasaScanTask):
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
        if entity is YasaScanTask:
            return _ScalarOneOrNoneResult(self.task)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, YasaFinding):
            self.findings.append(obj)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def close(self):
        return None


class _FakeOpengrepSession:
    def __init__(self, task: OpengrepScanTask, *, rules=None):
        self.task = task
        self.rules = list(rules or [])
        self.findings = []
        self.commit_calls = 0
        self.rollback_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is OpengrepScanTask:
            return _ScalarOneOrNoneResult(self.task)
        if entity is OpengrepRule:
            return _ScalarsResult(self.rules)
        return _ScalarOneOrNoneResult(None)

    def add(self, obj):
        if isinstance(obj, OpengrepFinding):
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


class _FakeLoop:
    async def run_in_executor(self, _executor, fn):
        return fn()


@pytest.mark.asyncio
async def test_execute_yasa_scan_uses_short_lived_sessions_and_persists_findings(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-1",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    captured = {}

    def _fake_build_yasa_scan_command(**kwargs):
        captured.update(kwargs)
        return ["yasa", kwargs["source_path"]]

    monkeypatch.setattr(static_tasks_yasa, "build_yasa_scan_command", _fake_build_yasa_scan_command)
    monkeypatch.setattr(static_tasks_yasa.settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:test")
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: tmp_path / "workspace", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: tmp_path / "workspace" / "project", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: tmp_path / "workspace" / "output", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: tmp_path / "workspace" / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: tmp_path / "workspace" / "meta", raising=False)

    async def _fake_run_scanner_container(spec, **kwargs):
        assert spec.scanner_type == "yasa"
        assert spec.image == "vulhunter/yasa-runner:test"
        assert spec.timeout_seconds == 90
        report_path = tmp_path / "workspace" / spec.artifact_paths[0]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            """
            {
              "runs": [
                {
                  "results": [
                    {
                      "ruleId": "demo.rule",
                      "message": {"text": "demo finding"},
                      "level": "warning",
                      "locations": [
                        {
                          "physicalLocation": {
                            "artifactLocation": {"uri": "%s"},
                            "region": {"startLine": 7, "endLine": 7}
                          }
                        }
                      ]
                    }
                  ],
                  "tool": {"driver": {"rules": [{"id": "demo.rule", "name": "Demo Rule"}]}}
                }
              ]
            }
            """
            % str(tmp_path / "src" / "main.ts"),
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="container-1",
            exit_code=0,
            stdout_path=str(tmp_path / "workspace" / "logs" / "stdout.log"),
            stderr_path=str(tmp_path / "workspace" / "logs" / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(static_tasks_yasa, "run_scanner_container", _fake_run_scanner_container, raising=False)

    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "main.ts").write_text("console.log('ok');", encoding="utf-8")

    await static_tasks_yasa._execute_yasa_scan(
        task_id="yasa-task-1",
        project_root=str(tmp_path),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.files_scanned == 1
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].file_path.endswith("main.ts")


@pytest.mark.asyncio
async def test_execute_yasa_scan_uses_scanner_runner_and_shared_workspace(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-runner-1",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    output_dir = tmp_path / "scans" / "yasa" / task.id / "output"
    logs_dir = tmp_path / "scans" / "yasa" / task.id / "logs"
    project_dir = tmp_path / "scans" / "yasa" / task.id / "project"
    project_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "main.ts").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa.settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:test")
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: project_dir.parent, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: logs_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: project_dir.parent / "meta", raising=False)

    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        report_path = project_dir.parent / spec.artifact_paths[0]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            """
            {
              "runs": [
                {
                  "results": [
                    {
                      "ruleId": "demo.rule",
                      "message": {"text": "runner finding"},
                      "level": "warning",
                      "locations": [
                        {
                          "physicalLocation": {
                            "artifactLocation": {"uri": "src/main.ts"},
                            "region": {"startLine": 5, "endLine": 5}
                          }
                        }
                      ]
                    }
                  ]
                }
              ]
            }
            """,
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="container-yasa-1",
            exit_code=0,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(static_tasks_yasa, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert seen["spec"].image == "vulhunter/yasa-runner:test"
    assert seen["spec"].timeout_seconds == 90
    assert task.status == "completed"
    assert task.total_findings == 1
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].message == "runner finding"


@pytest.mark.asyncio
async def test_execute_yasa_scan_marks_failed_when_runner_fails_without_local_fallback(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-runner-fail",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    output_dir = tmp_path / "scans" / "yasa" / task.id / "output"
    project_dir = tmp_path / "scans" / "yasa" / task.id / "project"
    project_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "main.ts").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: project_dir.parent, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: tmp_path / "scans" / "yasa" / task.id / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: project_dir.parent / "meta", raising=False)

    async def _fake_run_scanner_container(_spec, **_kwargs):
        return SimpleNamespace(
            success=False,
            container_id="container-yasa-fail",
            exit_code=127,
            stdout_path=None,
            stderr_path=None,
            error="runner image missing",
        )

    monkeypatch.setattr(static_tasks_yasa, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "failed"
    assert "runner image missing" in str(task.error_message)


@pytest.mark.asyncio
async def test_execute_yasa_scan_skips_timed_out_file_and_continues(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-timeout-partial",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    workspace_dir = tmp_path / "scans" / "yasa" / task.id
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "slow.ts").write_text("const slow = 1;\n", encoding="utf-8")
    (repo_root / "src" / "fast.ts").write_text("const fast = 1;\n", encoding="utf-8")
    (repo_root / "src" / "ignored.py").write_text("print('x')\n", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)

    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: workspace_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: workspace_dir / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: workspace_dir / "meta", raising=False)

    seen_sources = []

    async def _fake_run_scanner_container(spec, **_kwargs):
        source_index = spec.command.index("--sourcePath") + 1
        source_path = spec.command[source_index]
        seen_sources.append(source_path)
        if source_path.endswith("slow.ts"):
            return SimpleNamespace(
                success=False,
                container_id="container-yasa-timeout",
                exit_code=1,
                stdout_path=None,
                stderr_path=None,
                error="scanner timed out after 90s",
            )

        report_path = workspace_dir / spec.artifact_paths[0]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            """
            {
              "runs": [
                {
                  "results": [
                    {
                      "ruleId": "demo.rule",
                      "message": {"text": "partial finding"},
                      "level": "warning",
                      "locations": [
                        {
                          "physicalLocation": {
                            "artifactLocation": {"uri": "src/fast.ts"},
                            "region": {"startLine": 3, "endLine": 3}
                          }
                        }
                      ]
                    }
                  ]
                }
              ]
            }
            """,
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="container-yasa-fast",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(static_tasks_yasa, "run_scanner_container", _fake_run_scanner_container, raising=False)

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.files_scanned == 1
    diagnostics = json.loads(task.diagnostics_summary or "{}")
    scan_stats = diagnostics.get("scan_stats") or {}
    assert scan_stats.get("files_total") == 2
    assert scan_stats.get("files_timed_out") == 1
    assert "src/slow.ts" in (scan_stats.get("skipped_files_sample") or [])
    assert all(not source.endswith("ignored.py") for source in seen_sources)


@pytest.mark.asyncio
async def test_execute_yasa_scan_all_timed_out_files_still_mark_completed(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-timeout-all",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    workspace_dir = tmp_path / "scans" / "yasa" / task.id
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "a.ts").write_text("const a = 1;\n", encoding="utf-8")
    (repo_root / "src" / "b.ts").write_text("const b = 1;\n", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: workspace_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: workspace_dir / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: workspace_dir / "meta", raising=False)
    async def _fake_run_scanner_container(*_args, **_kwargs):
        return SimpleNamespace(
            success=False,
            container_id="container-yasa-timeout",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="read timed out",
        )

    monkeypatch.setattr(
        static_tasks_yasa,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "completed"
    assert task.total_findings == 0
    assert task.files_scanned == 0
    diagnostics = json.loads(task.diagnostics_summary or "{}")
    scan_stats = diagnostics.get("scan_stats") or {}
    assert scan_stats.get("files_total") == 2
    assert scan_stats.get("files_timed_out") == 2


@pytest.mark.asyncio
async def test_execute_yasa_scan_timeout_exception_is_skipped_per_file(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-timeout-exception",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path=".",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    workspace_dir = tmp_path / "scans" / "yasa" / task.id
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "only.ts").write_text("const only = 1;\n", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)

    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: workspace_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: workspace_dir / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: workspace_dir / "meta", raising=False)

    async def _fake_run_scanner_container(*_args, **_kwargs):
        raise RuntimeError("UnixHTTPConnectionPool(host='localhost', port=None): Read timed out.")

    monkeypatch.setattr(
        static_tasks_yasa,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path=".",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "completed"
    assert task.total_findings == 0
    assert task.files_scanned == 0
    diagnostics = json.loads(task.diagnostics_summary or "{}")
    scan_stats = diagnostics.get("scan_stats") or {}
    assert scan_stats.get("files_total") == 1
    assert scan_stats.get("files_timed_out") == 1
    assert "src/only.ts" in (scan_stats.get("skipped_files_sample") or [])


@pytest.mark.asyncio
async def test_execute_yasa_scan_single_target_file_timeout_marks_completed(
    monkeypatch,
    tmp_path,
):
    task = YasaScanTask(
        id="yasa-task-single-file-timeout",
        project_id="project-1",
        name="yasa",
        status="pending",
        target_path="src/slow.ts",
        language="typescript",
    )
    load_session = _FakeYasaSession(task)
    persist_session = _FakeYasaSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    workspace_dir = tmp_path / "scans" / "yasa" / task.id
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "slow.ts").write_text("const slow = 1;\n", encoding="utf-8")
    (repo_root / "src" / "other.ts").write_text("const other = 1;\n", encoding="utf-8")

    monkeypatch.setattr(static_tasks_yasa, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_yasa, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_yasa, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    async def _fake_load_runtime_config(*_args, **_kwargs):
        return {
            "yasa_timeout_seconds": 600,
            "yasa_exec_heartbeat_seconds": 15,
            "yasa_orphan_stale_seconds": 120,
        }

    monkeypatch.setattr(
        static_tasks_yasa,
        "load_global_yasa_runtime_config",
        _fake_load_runtime_config,
        raising=False,
    )
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_workspace", lambda *_args, **_kwargs: workspace_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_logs_dir", lambda *_args, **_kwargs: workspace_dir / "logs", raising=False)
    monkeypatch.setattr(static_tasks_yasa, "ensure_scan_meta_dir", lambda *_args, **_kwargs: workspace_dir / "meta", raising=False)
    async def _fake_run_scanner_container(*_args, **_kwargs):
        return SimpleNamespace(
            success=False,
            container_id="container-yasa-timeout",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="timeout",
        )

    monkeypatch.setattr(
        static_tasks_yasa,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    await static_tasks_yasa._execute_yasa_scan(
        task_id=task.id,
        project_root=str(repo_root),
        target_path="src/slow.ts",
        language="typescript",
        checker_pack_ids=None,
        checker_ids=None,
        rule_config_file=None,
        rule_config_id=None,
    )

    assert task.status == "completed"
    diagnostics = json.loads(task.diagnostics_summary or "{}")
    scan_stats = diagnostics.get("scan_stats") or {}
    assert scan_stats.get("files_total") == 1
    assert scan_stats.get("files_timed_out") == 1
    assert scan_stats.get("skipped_files_sample") == ["src/slow.ts"]


@pytest.mark.asyncio
async def test_execute_opengrep_scan_uses_short_lived_sessions_and_persists_findings(
    monkeypatch,
    tmp_path,
):
    task = OpengrepScanTask(
        id="opengrep-task-1",
        project_id="project-1",
        name="opengrep",
        status="pending",
        target_path=".",
    )
    rule = SimpleNamespace(
        id="rule-1",
        name="demo rule",
        language="python",
        pattern_yaml="rules:\n  - id: demo.rule\n    languages: [python]\n    pattern: insecure_call(...)",
        is_active=True,
    )
    load_session = _FakeOpengrepSession(task, rules=[rule])
    persist_session = _FakeOpengrepSession(task)
    session_factory = _SessionFactory(load_session, persist_session)
    metric_enqueues = []
    workspace_dir = tmp_path / "scans" / "opengrep" / task.id
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"

    monkeypatch.setattr(static_tasks_opengrep, "async_session_factory", session_factory)
    monkeypatch.setattr(static_tasks_opengrep, "_is_scan_task_cancelled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(static_tasks_opengrep, "_clear_scan_task_cancel", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(static_tasks_opengrep, "_ensure_opengrep_xdg_dirs", lambda: None)
    monkeypatch.setattr(static_tasks_opengrep, "_record_scan_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(static_tasks_opengrep, "_detect_project_languages", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(static_tasks_opengrep, "_resolve_opengrep_scan_jobs", lambda: 1)
    monkeypatch.setattr(
        static_tasks_opengrep.project_metrics_refresher,
        "enqueue",
        lambda project_id: metric_enqueues.append(project_id),
    )
    monkeypatch.setattr(
        static_tasks_opengrep,
        "_parse_opengrep_output",
        lambda _stdout: (
            [
                {
                    "path": "/scan/project/src/app.py",
                    "start": {"line": 3},
                    "end": {"line": 3},
                    "extra": {
                        "severity": "ERROR",
                        "message": "dangerous sink",
                        "lines": "dangerous()",
                    },
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(static_tasks_opengrep.settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:test")
    monkeypatch.setattr(static_tasks_opengrep, "ensure_scan_workspace", lambda *_args, **_kwargs: workspace_dir, raising=False)
    monkeypatch.setattr(static_tasks_opengrep, "ensure_scan_project_dir", lambda *_args, **_kwargs: project_dir, raising=False)
    monkeypatch.setattr(static_tasks_opengrep, "ensure_scan_output_dir", lambda *_args, **_kwargs: output_dir, raising=False)
    monkeypatch.setattr(static_tasks_opengrep, "ensure_scan_logs_dir", lambda *_args, **_kwargs: logs_dir, raising=False)
    monkeypatch.setattr(static_tasks_opengrep, "ensure_scan_meta_dir", lambda *_args, **_kwargs: meta_dir, raising=False)

    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="opengrep-container-1",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(static_tasks_opengrep, "run_scanner_container", _fake_run_scanner_container, raising=False)

    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "app.py").write_text("dangerous()\n", encoding="utf-8")

    await static_tasks_opengrep._execute_opengrep_scan(
        task_id="opengrep-task-1",
        project_root=str(tmp_path),
        target_path=".",
        rule_ids=["rule-1"],
    )

    assert task.status == "completed"
    assert task.total_findings == 1
    assert task.error_count == 1
    assert task.files_scanned == 1
    assert task.lines_scanned == 1
    assert session_factory.calls >= 2
    assert len(persist_session.findings) == 1
    assert persist_session.findings[0].file_path == "src/app.py"
    assert metric_enqueues == ["project-1"]
    assert seen["spec"].image == "vulhunter/opengrep-runner:test"
    assert seen["spec"].command[:2] == ["opengrep", "--config"]
    assert "--json" in seen["spec"].command
    assert seen["spec"].command[-1] == "/scan/project"
    assert seen["spec"].command[2].startswith("/scan/meta/")
    assert seen["spec"].capture_stdout_path == "output/report.json"
