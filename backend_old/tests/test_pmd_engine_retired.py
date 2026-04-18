from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_PMD_MODULES = (
    (
        "model_rules",
        PROJECT_ROOT / "app/models/pmd.py",
        "app.models.pmd",
    ),
    (
        "model_scan",
        PROJECT_ROOT / "app/models/pmd_scan.py",
        "app.models.pmd_scan",
    ),
    (
        "ruleset_helper",
        PROJECT_ROOT / "app/services/pmd_rulesets.py",
        "app.services.pmd_rulesets",
    ),
)


def test_pmd_modules_stay_deleted():
    existing = [str(path) for _, path, _ in RETIRED_PMD_MODULES if path.exists()]
    assert not existing, (
        "pmd should be fully retired in opengrep-only mode:\n" + "\n".join(existing)
    )


def test_pmd_modules_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_PMD_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired pmd module {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )


def test_pmd_tool_surface_is_removed_from_external_tool_entrypoints():
    external_tools_text = (
        PROJECT_ROOT / "app/services/agent/tools/external_tools.py"
    ).read_text(encoding="utf-8")
    manual_smoke_text = (
        PROJECT_ROOT / "tests/test_external_tools_manual.py"
    ).read_text(encoding="utf-8")

    assert "PMDTool" not in external_tools_text
    assert "PMD_RULESET_ALIASES" not in external_tools_text
    assert "_normalize_pmd_target_path" not in external_tools_text
    assert "test_pmd(" not in manual_smoke_text
    assert '"pmd"' not in manual_smoke_text
