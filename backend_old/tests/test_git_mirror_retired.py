from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_git_mirror_module_stays_deleted():
    mirror_path = PROJECT_ROOT / "app/services/git_mirror.py"
    assert not mirror_path.exists(), (
        "retired app.services.git_mirror module should stay deleted"
    )


def test_git_mirror_module_has_no_live_python_importers():
    offenders = _collect_direct_module_import_offenders(
        "app.services.git_mirror",
        "app.services",
        "git_mirror",
    )
    assert not offenders, (
        "retired app.services.git_mirror module should have no live Python importers:\n"
        + "\n".join(offenders)
    )
