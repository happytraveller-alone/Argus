import os
import tempfile
import zipfile
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.services.agent.tools import (
    ExtractFunctionTool,
    FileReadTool,
    FileSearchTool,
    ListFilesTool,
)
from app.services.agent.tools.base import ToolResult
from app.services.agent.tools.business_logic_scan_tool import BusinessLogicScanTool
from app.services.llm.service import LLMService
from app.services.llm.types import DEFAULT_BASE_URLS, LLMProvider


class _DummyReadFileTool:
    description = "dummy read file"

    async def execute(self, **kwargs):
        return ToolResult(success=True, data=f"read:{kwargs.get('file_path', 'unknown')}")


def _build_javaseclab_like_zip(tmp_path: Path) -> Path:
    zip_path = tmp_path / "JavaSecLab-1.4.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
        zip_ref.writestr(
            "JavaSecLab-1.4/src/main/java/com/example/DemoController.java",
            "package com.example; public class DemoController { public String ping() { return \"pong\"; } }\n",
        )
        zip_ref.writestr(
            "JavaSecLab-1.4/README.md",
            "# JavaSecLab sample\n",
        )
    return zip_path


def _prepare_javaseclab_target_and_llm(tmp_path: Path) -> tuple[Path, Path, LLMService]:
    backend_root = Path(__file__).resolve().parents[1]
    env_path = backend_root / ".env"
    zip_path = _build_javaseclab_like_zip(tmp_path)

    assert env_path.exists(), f".env 文件不存在: {env_path}"

    load_dotenv(dotenv_path=env_path, override=False)
    provider = (os.getenv("LLM_PROVIDER", "openai") or "openai").strip().lower()
    model = (os.getenv("LLM_MODEL", "") or "").strip()
    base_url = (os.getenv("LLM_BASE_URL", "") or "").strip()
    api_key = (os.getenv("LLM_API_KEY", "") or "").strip()

    provider_key_map = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "claude": "CLAUDE_API_KEY",
        "anthropic": "CLAUDE_API_KEY",
        "qwen": "QWEN_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "baidu": "BAIDU_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "doubao": "DOUBAO_API_KEY",
    }
    if not api_key and provider in provider_key_map:
        api_key = (os.getenv(provider_key_map[provider], "") or "").strip()

    if not base_url:
        try:
            runtime_provider = LLMProvider.CLAUDE if provider == "anthropic" else LLMProvider(provider)
            base_url = DEFAULT_BASE_URLS.get(runtime_provider, "") or ""
        except Exception:
            base_url = ""

    if not model:
        model = "gpt-5" if provider != "ollama" else "llama3.3"

    llm_service = LLMService(
        user_config={
            "llmConfig": {
                "llmProvider": provider,
                "llmApiKey": api_key,
                "llmModel": model,
                "llmBaseUrl": base_url,
            }
        }
    )
    return backend_root, zip_path, llm_service


@pytest.mark.asyncio
async def test_business_logic_scan_with_javaseclab_zip_and_env_llm(monkeypatch, tmp_path: Path):
    _, zip_path, llm_service = _prepare_javaseclab_target_and_llm(tmp_path)
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
        children = list(extracted_root.iterdir())
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
async def test_business_logic_scan_real_llm_end_to_end(tmp_path: Path):
    """真 LLM 端到端测试（可选执行）。

    启用方式：
    RUN_LIVE_LLM_E2E=1 /home/yl/PHDlife/VulHunter/backend/.venv/bin/python -m pytest tests/test_refactored_business_logic_scan.py -k real_llm_end_to_end -q -s
    """
    if os.getenv("RUN_LIVE_LLM_E2E") != "1":
        pytest.skip("未启用真 LLM 端到端测试。设置 RUN_LIVE_LLM_E2E=1 后执行。")

    _, zip_path, llm_service = _prepare_javaseclab_target_and_llm(tmp_path)
    config = llm_service.config
    if config.provider.value != "ollama" and not str(config.api_key or "").strip():
        pytest.skip("当前 .env 未提供可用 API Key，跳过真 LLM 端到端测试。")

    with tempfile.TemporaryDirectory(prefix="javasec_live_", suffix="_scan") as temp_dir:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        extracted_root = Path(temp_dir)
        children = list(extracted_root.iterdir())
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
