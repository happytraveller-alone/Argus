import tempfile
import zipfile
from pathlib import Path
import os

import pytest
from dotenv import load_dotenv

from app.services.agent.tools.business_logic_scan_tool import BusinessLogicScanTool
from app.services.agent.tools.base import ToolResult
from app.services.llm.service import LLMService
from app.services.agent.tools import (
    FileReadTool,
    FileSearchTool,
    ListFilesTool,
    ExtractFunctionTool,
)


class _DummyReadFileTool:
    description = "dummy read file"

    async def execute(self, **kwargs):
        return ToolResult(success=True, data=f"read:{kwargs.get('file_path', 'unknown')}")


def _prepare_javaseclab_target_and_llm() -> tuple[Path, Path, LLMService]:
    backend_root = Path(__file__).resolve().parents[1]
    env_path = backend_root / ".env"
    zip_path = backend_root / "tests" / "resources" / "JavaSecLab-1.4.zip"

    assert env_path.exists(), f".env 文件不存在: {env_path}"
    assert zip_path.exists(), f"ZIP 文件不存在: {zip_path}"

    load_dotenv(dotenv_path=env_path, override=False)
    llm_service = LLMService()
    return backend_root, zip_path, llm_service


@pytest.mark.asyncio
async def test_business_logic_scan_with_javaseclab_zip_and_env_llm(monkeypatch):
    _, zip_path, llm_service = _prepare_javaseclab_target_and_llm()
    assert llm_service.config is not None
    assert llm_service.config.provider is not None
    assert llm_service.config.model

    called = {"run": False, "target": None}

    async def _fake_run(self, input_data):
        called["run"] = True
        called["target"] = input_data.get("target")
        return type(
            "_Result",
            (),
            {
                "success": True,
                "error": None,
                "iterations": 3,
                "tool_calls": 4,
                "tokens_used": 100,
                "data": {
                    "report": "ok",
                    "findings": [],
                    "phase_1_entries": 0,
                    "phase_3_sensitive_ops": [],
                    "phase_4_taint_paths": [],
                    "total_findings": 0,
                    "by_severity": {},
                },
                "to_dict": lambda _self: {"success": True},
            },
        )()

    monkeypatch.setattr(
        "app.services.agent.agents.business_logic_scan.BusinessLogicScanAgent.run",
        _fake_run,
    )

    with tempfile.TemporaryDirectory(prefix="javasec_", suffix="_scan") as temp_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        extracted_root = Path(temp_dir)
        children = [item for item in extracted_root.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            target_dir = str(children[0])
        else:
            target_dir = str(extracted_root)

        tool = BusinessLogicScanTool(
            project_root=target_dir,
            llm_service=llm_service,
            tools_registry={
                "read_file": _DummyReadFileTool(),
                "business_logic_scan": object(),
            },
            event_emitter=None,
        )

        result = await tool.execute(target=target_dir, framework_hint="java", quick_mode=True, max_iterations=5)

    assert called["run"] is True
    assert called["target"] == target_dir
    assert result.success is True
    assert result.metadata["sub_agent"] == "BusinessLogicScanAgent"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_business_logic_scan_real_llm_end_to_end():
    """真 LLM 端到端测试（可选执行）。

    启用方式：
    RUN_LIVE_LLM_E2E=1 /home/yl/PHDlife/DeepAudit/backend/.venv/bin/python -m pytest tests/test_refactored_business_logic_scan.py -k real_llm_end_to_end -q -s
    """
    if os.getenv("RUN_LIVE_LLM_E2E") != "1":
        pytest.skip("未启用真 LLM 端到端测试。设置 RUN_LIVE_LLM_E2E=1 后执行。")

    _, zip_path, llm_service = _prepare_javaseclab_target_and_llm()
    config = llm_service.config
    if config.provider.value != "ollama" and not str(config.api_key or "").strip():
        pytest.skip("当前 .env 未提供可用 API Key，跳过真 LLM 端到端测试。")

    with tempfile.TemporaryDirectory(prefix="javasec_live_", suffix="_scan") as temp_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        extracted_root = Path(temp_dir)
        children = [item for item in extracted_root.iterdir()]
        target_dir = str(children[0]) if len(children) == 1 and children[0].is_dir() else str(extracted_root)

        analysis_tools = {
            "read_file": FileReadTool(target_dir),
            "search_code": FileSearchTool(target_dir),
            "list_files": ListFilesTool(target_dir),
            "extract_function": ExtractFunctionTool(target_dir),
        }

        tool = BusinessLogicScanTool(
            project_root=target_dir,
            llm_service=llm_service,
            tools_registry=analysis_tools,
            event_emitter=None,
        )

        result = await tool.execute(
            target=target_dir,
            framework_hint="java",
            quick_mode=True,
            max_iterations=8,
        )

    assert result.success is True
    assert isinstance(result.data, str)
    assert isinstance(result.metadata.get("findings"), list)
    assert result.metadata.get("sub_agent") == "BusinessLogicScanAgent"


@pytest.mark.asyncio
async def test_business_logic_scan_tool_requires_bound_tools():
    tool = BusinessLogicScanTool(project_root=".", llm_service=None, tools_registry={})
    result = await tool.execute(target=".")

    assert result.success is False
    assert "tools_registry" in (result.error or "")
