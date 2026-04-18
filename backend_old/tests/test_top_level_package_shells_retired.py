from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_package_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_core_package_shell_stays_deleted():
    core_package_init = PROJECT_ROOT / "app/core/__init__.py"
    assert not core_package_init.exists(), (
        "retired app.core package shell should stay deleted"
    )


def test_core_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders("app.core", "app", "core")
    assert not offenders, (
        "retired app.core package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_models_package_shell_stays_deleted():
    models_package_init = PROJECT_ROOT / "app/models/__init__.py"
    assert not models_package_init.exists(), (
        "retired app.models package shell should stay deleted"
    )


def test_models_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders("app.models", "app", "models")
    assert not offenders, (
        "retired app.models package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_alembic_env_imports_model_modules_directly():
    alembic_env = PROJECT_ROOT / "alembic/env.py"
    source = alembic_env.read_text(encoding="utf-8")

    assert "from app.models import *" not in source
    assert "import app.models.agent_task" in source
    assert "import app.models.user_config" in source
