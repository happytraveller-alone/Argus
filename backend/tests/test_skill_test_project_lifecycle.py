import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.project import Project
from app.services.agent import skill_test_runner as runner_module
from app.services.agent.agents.base import AgentResult


class _RecorderEmitter:
    def __init__(self):
        self.events: list[dict] = []

    async def emit_event(self, event_type: str, message: str, metadata=None):
        self.events.append(
            {
                "type": event_type,
                "message": message,
                "metadata": metadata or {},
            }
        )

    async def emit(self, event_data):
        self.events.append(
            {
                "type": getattr(event_data, "event_type", "info"),
                "message": getattr(event_data, "message", ""),
                "metadata": getattr(event_data, "metadata", {}) or {},
            }
        )


def _make_libplist_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
        zip_ref.writestr("libplist-2.7.0/src/main.c", "int main() {\n  return 0;\n}\n")


@pytest.mark.asyncio
async def test_skill_test_runner_extracts_nested_project_and_cleans_temp_dir(monkeypatch, tmp_path: Path):
    archive_path = tmp_path / "libplist.zip"
    _make_libplist_zip(archive_path)

    project = Project(
        id="project-1",
        owner_id="user-1",
        name="libplist",
        source_type="zip",
        is_active=True,
    )
    emitter = _RecorderEmitter()
    captured_project_root: dict[str, str] = {}

    async def _fake_resolve_verify_project(**kwargs):
        return project, str(archive_path), False

    def _fake_build_tools(skill_id: str, project_root: str, llm_service):
        captured_project_root["value"] = project_root
        return {"get_code_window": object()}

    class _FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, input_data):
            return AgentResult(success=True, data={"final_text": "读取完成"})

    monkeypatch.setattr(runner_module, "_resolve_verify_project", _fake_resolve_verify_project)
    monkeypatch.setattr(runner_module, "build_skill_test_tools", _fake_build_tools)
    monkeypatch.setattr(runner_module, "SkillTestAgent", _FakeAgent)

    runner = runner_module.SkillTestRunner(
        skill_id="get_code_window",
        prompt="读取入口函数",
        max_iterations=3,
        llm_service=object(),
        db=AsyncMock(),
        current_user=SimpleNamespace(id="user-1"),
        event_emitter=emitter,
    )

    result = await runner.run()

    assert captured_project_root["value"].endswith("libplist-2.7.0")
    assert result["project_name"] == "libplist"
    assert result["cleanup"]["success"] is True
    assert not Path(result["cleanup"]["temp_dir"]).exists()
    assert any(event["type"] == "project_prepare" for event in emitter.events)
    assert any(event["type"] == "project_cleanup" for event in emitter.events)


@pytest.mark.asyncio
async def test_skill_test_runner_cleans_temp_dir_when_agent_fails(monkeypatch, tmp_path: Path):
    archive_path = tmp_path / "libplist.zip"
    _make_libplist_zip(archive_path)

    project = Project(
        id="project-1",
        owner_id="user-1",
        name="libplist",
        source_type="zip",
        is_active=True,
    )
    emitter = _RecorderEmitter()

    async def _fake_resolve_verify_project(**kwargs):
        return project, str(archive_path), False

    class _FailingAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, input_data):
            raise RuntimeError("boom")

    monkeypatch.setattr(runner_module, "_resolve_verify_project", _fake_resolve_verify_project)
    monkeypatch.setattr(
        runner_module,
        "build_skill_test_tools",
        lambda skill_id, project_root, llm_service: {"get_code_window": object()},
    )
    monkeypatch.setattr(runner_module, "SkillTestAgent", _FailingAgent)

    runner = runner_module.SkillTestRunner(
        skill_id="get_code_window",
        prompt="读取入口函数",
        max_iterations=3,
        llm_service=object(),
        db=AsyncMock(),
        current_user=SimpleNamespace(id="user-1"),
        event_emitter=emitter,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await runner.run()

    cleanup_event = next(event for event in emitter.events if event["type"] == "project_cleanup")
    assert cleanup_event["metadata"]["cleanup_success"] is True
    assert not Path(cleanup_event["metadata"]["temp_dir"]).exists()
