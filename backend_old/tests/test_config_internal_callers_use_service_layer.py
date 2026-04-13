from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_internal_callers_no_longer_import_config_endpoint():
    caller_paths = [
        PROJECT_ROOT / "app/services/static_scan_runtime.py",
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
                "def normalize_extracted_project_root(base_path: str) -> str:" in content
            ), "skill_test_runner.py should host normalize_extracted_project_root locally"
            continue

        assert forbidden not in content, f"{path.name} still depends on config endpoint"
        assert required in content, f"{path.name} should depend on user_config_service"


def test_static_scan_runtime_no_longer_imports_db_session_module():
    path = PROJECT_ROOT / "app/services/static_scan_runtime.py"
    content = path.read_text(encoding="utf-8")

    assert "from app.db.session import" not in content
    assert "async_session_factory" not in content
    assert "get_db" not in content
