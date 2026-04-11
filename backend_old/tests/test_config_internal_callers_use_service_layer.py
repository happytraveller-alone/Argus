from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_internal_callers_no_longer_import_config_endpoint():
    caller_paths = [
        PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_execution.py",
        PROJECT_ROOT / "app/api/v1/endpoints/static_tasks_shared.py",
        PROJECT_ROOT / "app/api/v1/endpoints/agent_test.py",
        PROJECT_ROOT / "app/api/v1/endpoints/static_tasks_opengrep_rules.py",
        PROJECT_ROOT / "app/services/agent/skill_test_runner.py",
    ]

    forbidden = "from app.api.v1.endpoints.config import _load_effective_user_config"
    required = "from app.services.user_config_service import load_effective_user_config"

    for path in caller_paths:
        content = path.read_text(encoding="utf-8")
        if path.name == "skill_test_runner.py":
            assert (
                "from app.api.v1.endpoints.config import (\n    _normalize_extracted_project_root,\n)"
                not in content
            ), "skill_test_runner.py still depends on config endpoint"
            assert (
                "from app.services.project_test_service import normalize_extracted_project_root"
                in content
            ), "skill_test_runner.py should depend on project_test_service"
            continue

        assert forbidden not in content, f"{path.name} still depends on config endpoint"
        assert required in content, f"{path.name} should depend on user_config_service"


def test_config_endpoint_no_longer_owns_llm_provider_helper_impl():
    config_path = PROJECT_ROOT / "app/api/v1/endpoints/config.py"
    content = config_path.read_text(encoding="utf-8")

    forbidden_defs = [
        "def _build_llm_provider_catalog(",
        "def _resolve_llm_runtime_provider(",
        "def _extract_model_names_from_payload(",
        "def _extract_model_metadata_from_payload(",
        "async def _fetch_models_openai_compatible(",
        "async def _fetch_models_anthropic(",
        "async def _fetch_models_azure_openai(",
    ]
    for snippet in forbidden_defs:
        assert snippet not in content, f"config.py still owns helper: {snippet}"

    assert (
        "from app.services import llm_provider_service" in content
    ), "config.py should depend on llm_provider_service"
