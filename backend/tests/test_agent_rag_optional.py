from types import SimpleNamespace
from pathlib import Path

import pytest

from app.api.v1.endpoints.agent_tasks import _initialize_tools
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_initialize_tools_rag_disabled_skips_rag_tools(tmp_path: Path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")

    tools = await _initialize_tools(
        project_root=str(tmp_path),
        llm_service=object(),
        user_config=None,
        sandbox_manager=SimpleNamespace(),
        rag_enabled=False,
        verification_level="analysis_with_poc_plan",
        exclude_patterns=[],
        target_files=None,
        project_id="p1",
        event_emitter=None,
        task_id=None,
    )

    assert isinstance(tools, dict)
    assert "analysis" in tools and "recon" in tools and "verification" in tools

    assert "rag_query" not in tools["recon"]
    assert "rag_query" not in tools["analysis"]
    assert "security_search" not in tools["analysis"]
    assert "function_context" not in tools["analysis"]


@pytest.mark.asyncio
async def test_initialize_tools_rag_enabled_but_init_fails_degrades(monkeypatch, tmp_path: Path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")

    class _BoomEmbeddingService:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.services.rag.EmbeddingService", _BoomEmbeddingService)

    tools = await _initialize_tools(
        project_root=str(tmp_path),
        llm_service=object(),
        user_config=None,
        sandbox_manager=SimpleNamespace(),
        rag_enabled=True,
        verification_level="analysis_with_poc_plan",
        exclude_patterns=[],
        target_files=None,
        project_id="p1",
        event_emitter=None,
        task_id=None,
    )

    assert isinstance(tools, dict)
    assert "analysis" in tools and "recon" in tools and "verification" in tools

    # Init失败应降级：不注册 rag 工具
    assert "rag_query" not in tools["recon"]
    assert "rag_query" not in tools["analysis"]
    assert "security_search" not in tools["analysis"]
    assert "function_context" not in tools["analysis"]

