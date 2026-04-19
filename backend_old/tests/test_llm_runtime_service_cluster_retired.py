from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODULES = (
    (
        "base_adapter",
        PROJECT_ROOT / "app/services/llm/base_adapter.py",
        "app.services.llm.base_adapter",
        "app.services.llm",
        "base_adapter",
    ),
    (
        "factory",
        PROJECT_ROOT / "app/services/llm/factory.py",
        "app.services.llm.factory",
        "app.services.llm",
        "factory",
    ),
    (
        "prompt_cache",
        PROJECT_ROOT / "app/services/llm/prompt_cache.py",
        "app.services.llm.prompt_cache",
        "app.services.llm",
        "prompt_cache",
    ),
    (
        "service",
        PROJECT_ROOT / "app/services/llm/service.py",
        "app.services.llm.service",
        "app.services.llm",
        "service",
    ),
    (
        "types",
        PROJECT_ROOT / "app/services/llm/types.py",
        "app.services.llm.types",
        "app.services.llm",
        "types",
    ),
    (
        "baidu_adapter",
        PROJECT_ROOT / "app/services/llm/adapters/baidu_adapter.py",
        "app.services.llm.adapters.baidu_adapter",
        "app.services.llm.adapters",
        "baidu_adapter",
    ),
    (
        "doubao_adapter",
        PROJECT_ROOT / "app/services/llm/adapters/doubao_adapter.py",
        "app.services.llm.adapters.doubao_adapter",
        "app.services.llm.adapters",
        "doubao_adapter",
    ),
    (
        "litellm_adapter",
        PROJECT_ROOT / "app/services/llm/adapters/litellm_adapter.py",
        "app.services.llm.adapters.litellm_adapter",
        "app.services.llm.adapters",
        "litellm_adapter",
    ),
    (
        "minimax_adapter",
        PROJECT_ROOT / "app/services/llm/adapters/minimax_adapter.py",
        "app.services.llm.adapters.minimax_adapter",
        "app.services.llm.adapters",
        "minimax_adapter",
    ),
)


def test_retired_llm_service_cluster_modules_stay_deleted():
    existing = [label for label, path, *_ in RETIRED_MODULES if path.exists()]
    assert not existing, (
        "retired llm service/adapters modules should stay deleted:\n"
        + "\n".join(existing)
    )


def test_retired_llm_service_cluster_modules_have_no_live_python_importers():
    offenders = []
    for _, _, module_name, parent_package, symbol in RETIRED_MODULES:
        offenders.extend(
            _collect_direct_module_import_offenders(module_name, parent_package, symbol)
        )

    assert not offenders, (
        "retired llm service/adapters modules should have no live Python importers:\n"
        + "\n".join(offenders)
    )
