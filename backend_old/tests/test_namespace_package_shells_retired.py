from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_package_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_app_root_package_shell_stays_deleted():
    app_root_init = PROJECT_ROOT / "app/__init__.py"
    assert not app_root_init.exists(), (
        "retired app root package shell should stay deleted"
    )


def test_app_root_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders("app", None, None)
    filtered = [
        offender
        for offender in offenders
        if ": import app" in offender or ": from app import" in offender
    ]
    assert not filtered, (
        "retired app root package shell should have no direct live Python importers:\n"
        + "\n".join(filtered)
    )


def test_schema_snapshots_package_shell_stays_deleted():
    snapshots_init = PROJECT_ROOT / "app/db/schema_snapshots/__init__.py"
    assert not snapshots_init.exists(), (
        "retired app.db.schema_snapshots package shell should stay deleted"
    )


def test_schema_snapshots_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.db.schema_snapshots",
        "app.db",
        "schema_snapshots",
    )
    assert not offenders, (
        "retired app.db.schema_snapshots package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_flow_lightweight_package_shell_stays_deleted():
    lightweight_init = PROJECT_ROOT / "app/services/agent/core/flow/lightweight/__init__.py"
    assert not lightweight_init.exists(), (
        "retired app.services.agent.core.flow.lightweight package shell should stay deleted"
    )


def test_flow_lightweight_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.services.agent.core.flow.lightweight",
        "app.services.agent.core.flow",
        "lightweight",
    )
    assert not offenders, (
        "retired app.services.agent.core.flow.lightweight package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_llm_adapters_package_shell_stays_deleted():
    adapters_init = PROJECT_ROOT / "app/services/llm/adapters/__init__.py"
    assert not adapters_init.exists(), (
        "retired app.services.llm.adapters package shell should stay deleted"
    )


def test_llm_adapters_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.services.llm.adapters",
        "app.services.llm",
        "adapters",
    )
    assert not offenders, (
        "retired app.services.llm.adapters package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )
