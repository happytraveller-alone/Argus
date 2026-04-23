import ast
import importlib.util
import sys
import types
from pathlib import Path

from app.services.agent.agents.base import BaseAgent
from app.services.agent.runtime_settings import settings
from app.services.agent.tools.sandbox_runner_client import SandboxRunnerClient
from app.services.agent.tools.sandbox_tool import SandboxConfig, SandboxManager


BACKEND_OLD_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_OLD_ROOT.parent
REMAINING_RUNTIME_SETTING_TARGETS = (
    BACKEND_OLD_ROOT / "app/services/agent/agents/base.py",
    BACKEND_OLD_ROOT / "app/services/agent/tools/sandbox_tool.py",
    BACKEND_OLD_ROOT / "app/services/agent/tools/sandbox_runner_client.py",
    REPO_ROOT / "scripts/release-templates/runner_preflight.py",
)


def _collect_core_config_import_offenders() -> list[str]:
    offenders: list[str] = []
    for path in REMAINING_RUNTIME_SETTING_TARGETS:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.core.config":
                        offenders.append(f"{path}: import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module == "app.core.config":
                    offenders.append(f"{path}: from {node.module} import ...")
                if node.module == "app.core":
                    for alias in node.names:
                        if alias.name == "config":
                            offenders.append(f"{path}: from app.core import config")
    return offenders


def _load_runner_preflight_module(monkeypatch):
    module_path = REPO_ROOT / "scripts/release-templates/runner_preflight.py"
    fake_docker = types.SimpleNamespace(errors=types.SimpleNamespace(DockerException=Exception, ImageNotFound=Exception))
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    spec = importlib.util.spec_from_file_location("runner_preflight_module", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _DummyAgent:
    llm_service = object()


def test_remaining_runtime_modules_stop_importing_app_core_config():
    offenders = _collect_core_config_import_offenders()
    assert not offenders, (
        "remaining runtime modules should stop importing app.core.config:\n"
        + "\n".join(offenders)
    )


def test_base_timeout_config_uses_runtime_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM_FIRST_TOKEN_TIMEOUT", 11)
    monkeypatch.setattr(settings, "LLM_STREAM_TIMEOUT", 22)
    monkeypatch.setattr(settings, "AGENT_TIMEOUT_SECONDS", 33)
    monkeypatch.setattr(settings, "SUB_AGENT_TIMEOUT_SECONDS", 44)
    monkeypatch.setattr(settings, "TOOL_TIMEOUT_SECONDS", 55)

    assert BaseAgent._get_timeout_config(_DummyAgent()) == {
        "llm_first_token_timeout": 11,
        "llm_stream_timeout": 22,
        "agent_timeout": 33,
        "sub_agent_timeout": 44,
        "tool_timeout": 55,
    }


def test_sandbox_config_and_client_use_runtime_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SANDBOX_IMAGE", "example.com/custom/sandbox:latest")
    monkeypatch.setattr(settings, "SANDBOX_RUNNER_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_RUNNER_IMAGE", "example.com/custom/sandbox-runner:latest")
    monkeypatch.setattr(settings, "SANDBOX_TIMEOUT", 99)
    monkeypatch.setattr(settings, "SANDBOX_MEMORY_LIMIT", "768m")
    monkeypatch.setattr(settings, "SANDBOX_CPU_LIMIT", 2.5)
    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(tmp_path / "scan-root"))

    config = SandboxConfig()
    manager = SandboxManager(config=SandboxConfig(image=""))
    client = SandboxRunnerClient()

    assert config.image == "example.com/custom/sandbox:latest"
    assert config.timeout == 99
    assert config.memory_limit == "768m"
    assert config.cpu_limit == 2.5
    assert manager._use_new_runner is False
    assert client.workspace_root == tmp_path / "scan-root" / "sandbox-runner"
    assert client._get_image_candidates()[0] == "example.com/custom/sandbox-runner:latest"


def test_runner_preflight_uses_runtime_settings(monkeypatch):
    module = _load_runner_preflight_module(monkeypatch)

    monkeypatch.setattr(settings, "RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 91)
    monkeypatch.setattr(settings, "SCANNER_OPENGREP_IMAGE", "example.com/opengrep:latest")
    monkeypatch.setattr(settings, "FLOW_PARSER_RUNNER_IMAGE", "example.com/flow-parser:latest")
    monkeypatch.setattr(settings, "SANDBOX_RUNNER_IMAGE", "example.com/sandbox-runner:latest")

    specs = module.get_configured_runner_preflight_specs()

    assert all(spec.timeout_seconds == 91 for spec in specs)
    assert [spec.image for spec in specs] == [
        "example.com/opengrep:latest",
        "example.com/flow-parser:latest",
        "example.com/sandbox-runner:latest",
    ]
