import ast
import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FLOW_RUNTIME_SETTING_TARGETS = (
    PROJECT_ROOT / "app/services/agent/core/flow/pipeline.py",
    PROJECT_ROOT / "app/services/agent/core/flow/lightweight/callgraph_code2flow.py",
    PROJECT_ROOT / "app/services/agent/core/flow/lightweight/flow_parser_runtime.py",
    PROJECT_ROOT / "app/services/agent/core/flow/lightweight/function_locator.py",
)


def _collect_core_config_import_offenders() -> list[str]:
    offenders: list[str] = []
    for path in FLOW_RUNTIME_SETTING_TARGETS:
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


def test_flow_lightweight_modules_stop_importing_app_core_config():
    offenders = _collect_core_config_import_offenders()
    assert not offenders, (
        "flow/lightweight runtime modules should stop importing app.core.config:\n"
        + "\n".join(offenders)
    )


def test_runtime_settings_parses_function_locator_languages_env(monkeypatch):
    monkeypatch.setenv("FUNCTION_LOCATOR_LANGUAGES", '["python","typescript","python"]')

    module = importlib.import_module("app.services.agent.runtime_settings")
    instance = module.RuntimeSettings()

    assert instance.FUNCTION_LOCATOR_LANGUAGES == ["python", "typescript"]


def test_runtime_settings_uses_repo_backend_env_file_path():
    module = importlib.import_module("app.services.agent.runtime_settings")
    expected = PROJECT_ROOT.parent / "backend" / "docker" / "env" / "backend" / ".env"

    assert module.BACKEND_ENV_FILE == expected


def test_runtime_settings_falls_back_to_env_file_values(monkeypatch):
    module = importlib.import_module("app.services.agent.runtime_settings")
    monkeypatch.delenv("FLOW_PARSER_RUNNER_IMAGE", raising=False)
    monkeypatch.setattr(
        module,
        "_ENV_FILE_VALUES",
        {"FLOW_PARSER_RUNNER_IMAGE": "example.com/custom/flow-parser:latest"},
    )

    instance = module.RuntimeSettings()

    assert instance.FLOW_PARSER_RUNNER_IMAGE == "example.com/custom/flow-parser:latest"
