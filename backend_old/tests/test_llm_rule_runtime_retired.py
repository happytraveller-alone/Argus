from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
    _collect_direct_package_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODULES = (
    ("rule", PROJECT_ROOT / "app/services/rule.py", "app.services.rule", "app.services", "rule"),
    (
        "llm_rule.cache_manager",
        PROJECT_ROOT / "app/services/llm_rule/cache_manager.py",
        "app.services.llm_rule.cache_manager",
        "app.services.llm_rule",
        "cache_manager",
    ),
    (
        "llm_rule.config",
        PROJECT_ROOT / "app/services/llm_rule/config.py",
        "app.services.llm_rule.config",
        "app.services.llm_rule",
        "config",
    ),
    (
        "llm_rule.git_manager",
        PROJECT_ROOT / "app/services/llm_rule/git_manager.py",
        "app.services.llm_rule.git_manager",
        "app.services.llm_rule",
        "git_manager",
    ),
    (
        "llm_rule.llm_client",
        PROJECT_ROOT / "app/services/llm_rule/llm_client.py",
        "app.services.llm_rule.llm_client",
        "app.services.llm_rule",
        "llm_client",
    ),
    (
        "llm_rule.patch_processor",
        PROJECT_ROOT / "app/services/llm_rule/patch_processor.py",
        "app.services.llm_rule.patch_processor",
        "app.services.llm_rule",
        "patch_processor",
    ),
    (
        "llm_rule.repo_cache_manager",
        PROJECT_ROOT / "app/services/llm_rule/repo_cache_manager.py",
        "app.services.llm_rule.repo_cache_manager",
        "app.services.llm_rule",
        "repo_cache_manager",
    ),
    (
        "llm_rule.rule_manager",
        PROJECT_ROOT / "app/services/llm_rule/rule_manager.py",
        "app.services.llm_rule.rule_manager",
        "app.services.llm_rule",
        "rule_manager",
    ),
    (
        "llm_rule.rule_validator",
        PROJECT_ROOT / "app/services/llm_rule/rule_validator.py",
        "app.services.llm_rule.rule_validator",
        "app.services.llm_rule",
        "rule_validator",
    ),
)


def test_llm_rule_package_shell_stays_deleted():
    retired_package = PROJECT_ROOT / "app/services/llm_rule"
    remaining_python_files = sorted(retired_package.rglob("*.py")) if retired_package.exists() else []
    assert not remaining_python_files, (
        "retired app.services.llm_rule package should not retain Python modules:\n"
        + "\n".join(str(path) for path in remaining_python_files)
    )


def test_llm_rule_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.services.llm_rule",
        "app.services",
        "llm_rule",
    )
    assert not offenders, (
        "retired app.services.llm_rule package should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_retired_rule_runtime_modules_stay_deleted():
    missing = [label for label, path, *_ in RETIRED_MODULES if path.exists()]
    assert not missing, "retired rule runtime modules should stay deleted:\n" + "\n".join(missing)


def test_retired_rule_runtime_modules_have_no_live_python_importers():
    offenders = []
    for _, _, module_name, parent_package, symbol in RETIRED_MODULES:
        offenders.extend(
            _collect_direct_module_import_offenders(module_name, parent_package, symbol)
        )

    assert not offenders, (
        "retired rule runtime modules should have no live Python importers:\n"
        + "\n".join(offenders)
    )
