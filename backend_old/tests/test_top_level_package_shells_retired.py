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


def test_alembic_tree_stays_deleted():
    assert not (PROJECT_ROOT / "alembic").exists(), (
        "retired backend_old/alembic tree should stay deleted"
    )


def test_baseline_schema_snapshot_stays_deleted():
    snapshot_file = PROJECT_ROOT / "app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py"
    assert not snapshot_file.exists(), (
        "retired Alembic baseline snapshot should stay deleted"
    )
