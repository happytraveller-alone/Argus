from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_package_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_db_package_shell_stays_deleted():
    db_package_init = PROJECT_ROOT / "app/db/__init__.py"
    assert not db_package_init.exists(), (
        "retired app.db package shell should stay deleted after Rust-owned asset paths took over"
    )


def test_db_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders("app.db", "app", "db")
    assert not offenders, (
        "retired app.db package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )
