from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_AGENT_PACKAGE_SHELLS = (
    ("bootstrap", "app/services/agent/bootstrap/__init__.py"),
    ("core", "app/services/agent/core/__init__.py"),
    ("flow", "app/services/agent/flow/__init__.py"),
    ("frameworks", "app/services/agent/knowledge/frameworks/__init__.py"),
    ("logic", "app/services/agent/logic/__init__.py"),
    ("vulnerabilities", "app/services/agent/knowledge/vulnerabilities/__init__.py"),
    ("memory", "app/services/agent/memory/__init__.py"),
    ("prompts", "app/services/agent/prompts/__init__.py"),
    ("streaming", "app/services/agent/streaming/__init__.py"),
    ("tool_runtime", "app/services/agent/tool_runtime/__init__.py"),
    ("tools", "app/services/agent/tools/__init__.py"),
    ("tools_runtime", "app/services/agent/tools/runtime/__init__.py"),
    ("utils", "app/services/agent/utils/__init__.py"),
)
RETIRED_AGENT_WORKFLOW_CLUSTER_FILES = (
    ("engine", "app/services/agent/workflow/engine.py"),
    ("models", "app/services/agent/workflow/models.py"),
    ("parallel_executor", "app/services/agent/workflow/parallel_executor.py"),
    ("memory_monitor", "app/services/agent/workflow/memory_monitor.py"),
    ("workflow_orchestrator", "app/services/agent/workflow/workflow_orchestrator.py"),
)
RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_FILES = (
    ("probe_specs", "app/services/agent/tool_runtime/probe_specs.py"),
    ("protocol_verify", "app/services/agent/tool_runtime/protocol_verify.py"),
    ("virtual_tools", "app/services/agent/tool_runtime/virtual_tools.py"),
)
RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_FILES = (
    ("circuit_breaker", "app/services/agent/core/circuit_breaker.py"),
    ("fallback", "app/services/agent/core/fallback.py"),
    ("graph_controller", "app/services/agent/core/graph_controller.py"),
    ("persistence", "app/services/agent/core/persistence.py"),
    ("rate_limiter", "app/services/agent/core/rate_limiter.py"),
    ("retry", "app/services/agent/core/retry.py"),
    ("validation", "app/services/agent/core/validation.py"),
)


def test_legacy_api_router_module_has_been_retired():
    api_router_path = PROJECT_ROOT / "app/api/v1/api.py"
    assert not api_router_path.exists()


def test_legacy_api_package_init_modules_have_been_retired():
    api_init_path = PROJECT_ROOT / "app/api/__init__.py"
    api_v1_init_path = PROJECT_ROOT / "app/api/v1/__init__.py"
    endpoints_init_path = PROJECT_ROOT / "app/api/v1/endpoints/__init__.py"
    assert not api_init_path.exists()
    assert not api_v1_init_path.exists()
    assert not endpoints_init_path.exists()


def test_legacy_config_endpoint_module_has_been_retired():
    config_path = PROJECT_ROOT / "app/api/v1/endpoints/config.py"
    assert not config_path.exists()


def test_legacy_api_deps_module_has_been_retired():
    deps_path = PROJECT_ROOT / "app/api/deps.py"
    assert not deps_path.exists()


def test_legacy_static_tasks_facade_module_has_been_retired():
    static_tasks_path = PROJECT_ROOT / "app/api/v1/endpoints/static_tasks.py"
    assert not static_tasks_path.exists()


def test_legacy_static_scan_runtime_endpoint_module_has_been_retired():
    runtime_helpers_path = PROJECT_ROOT / "app/api/v1/endpoints" / "_".join(
        ["static", "tasks", "shared.py"]
    )
    assert not runtime_helpers_path.exists()


def test_legacy_agent_tasks_facade_module_has_been_retired():
    facade_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks.py"
    assert not facade_path.exists()


def test_legacy_agent_package_convenience_module_has_been_retired():
    package_init_path = PROJECT_ROOT / "app/services/agent/__init__.py"
    assert not package_init_path.exists()


@pytest.mark.parametrize(
    ("shell_name", "relative_path"),
    RETIRED_AGENT_PACKAGE_SHELLS,
    ids=[shell_name for shell_name, _ in RETIRED_AGENT_PACKAGE_SHELLS],
)
def test_legacy_agent_subpackage_shell_has_been_retired(shell_name: str, relative_path: str):
    retired_shell_path = PROJECT_ROOT / relative_path
    assert not retired_shell_path.exists(), f"retired agent {shell_name} package shell should stay deleted"


@pytest.mark.parametrize(
    ("module_name", "relative_path"),
    RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_FILES,
    ids=[module_name for module_name, _ in RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_FILES],
)
def test_legacy_tool_runtime_orphan_cluster_module_has_been_retired(
    module_name: str,
    relative_path: str,
):
    retired_module_path = PROJECT_ROOT / relative_path
    assert not retired_module_path.exists(), (
        f"retired tool_runtime orphan cluster module should stay deleted: {module_name}"
    )


@pytest.mark.parametrize(
    ("module_name", "relative_path"),
    RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_FILES,
    ids=[module_name for module_name, _ in RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_FILES],
)
def test_legacy_agent_core_orphan_support_cluster_module_has_been_retired(
    module_name: str,
    relative_path: str,
):
    retired_module_path = PROJECT_ROOT / relative_path
    assert not retired_module_path.exists(), (
        f"retired agent core orphan support cluster module should stay deleted: {module_name}"
    )


def test_legacy_init_db_module_has_been_retired():
    init_db_path = PROJECT_ROOT / "app/db/init_db.py"
    assert not init_db_path.exists()


def test_legacy_db_session_module_has_been_retired():
    session_path = PROJECT_ROOT / "app/db/session.py"
    assert not session_path.exists()


def test_legacy_db_base_module_has_been_retired():
    base_path = PROJECT_ROOT / "app/db/base.py"
    assert not base_path.exists()


def test_legacy_scan_path_db_helper_module_has_been_retired():
    retired_helper_path = PROJECT_ROOT / "app/db" / "_".join(["static", "finding_paths.py"])
    assert not retired_helper_path.exists()


def test_legacy_agent_tasks_execution_module_has_been_retired():
    execution_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_execution.py"
    assert not execution_path.exists()


def test_legacy_agent_tasks_runtime_module_has_been_retired():
    runtime_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_runtime.py"
    assert not runtime_path.exists()


def test_legacy_agent_tasks_access_module_has_been_retired():
    access_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_access.py"
    assert not access_path.exists()


def test_legacy_agent_tasks_tool_runtime_module_has_been_retired():
    runtime_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_tool_runtime.py"
    assert not runtime_path.exists()


def test_legacy_agent_tasks_bootstrap_module_has_been_retired():
    bootstrap_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_bootstrap.py"
    assert not bootstrap_path.exists()


def test_legacy_agent_tasks_contracts_module_has_been_retired():
    contracts_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_contracts.py"
    assert not contracts_path.exists()


def test_legacy_agent_tasks_findings_module_has_been_retired():
    findings_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_findings.py"
    assert not findings_path.exists()


def test_legacy_rule_flows_schema_module_has_been_retired():
    rule_flows_path = PROJECT_ROOT / "app/api/v1/schemas/rule_flows.py"
    schemas_init_path = PROJECT_ROOT / "app/api/v1/schemas/__init__.py"
    assert not rule_flows_path.exists()
    assert not schemas_init_path.exists()


def test_legacy_project_metrics_service_module_has_been_retired():
    metrics_path = PROJECT_ROOT / "app/services/project_metrics.py"
    assert not metrics_path.exists()


def test_legacy_zip_cache_manager_has_been_retired():
    cache_path = PROJECT_ROOT / "app/services/zip_cache_manager.py"
    assert not cache_path.exists()


def test_legacy_search_service_has_been_retired():
    search_service_path = PROJECT_ROOT / "app/services/search_service.py"
    assert not search_service_path.exists()


def test_legacy_report_generator_service_has_been_retired():
    report_generator_path = PROJECT_ROOT / "app/services/report_generator.py"
    assert not report_generator_path.exists()


def test_legacy_runner_preflight_service_has_been_retired():
    runner_preflight_path = PROJECT_ROOT / "app/services/runner_preflight.py"
    assert not runner_preflight_path.exists()


def test_legacy_opengrep_confidence_service_has_been_retired():
    confidence_path = PROJECT_ROOT / "app/services/opengrep_confidence.py"
    assert not confidence_path.exists()


def test_legacy_init_templates_service_has_been_retired():
    init_templates_path = PROJECT_ROOT / "app/services/init_templates.py"
    assert not init_templates_path.exists()


def test_legacy_seed_archive_service_has_been_retired():
    seed_archive_path = PROJECT_ROOT / "app/services/seed_archive.py"
    assert not seed_archive_path.exists()


def test_legacy_zip_storage_service_has_been_retired():
    zip_storage_path = PROJECT_ROOT / "app/services/zip_storage.py"
    assert not zip_storage_path.exists()


def test_legacy_upload_compression_factory_has_been_retired():
    compression_factory_path = PROJECT_ROOT / "app/services/upload/compression_factory.py"
    assert not compression_factory_path.exists()


def test_legacy_upload_compression_handlers_have_been_retired():
    compression_handlers_path = PROJECT_ROOT / "app/services/upload/compression_handlers.py"
    assert not compression_handlers_path.exists()


def test_legacy_upload_compression_strategy_has_been_retired():
    compression_strategy_path = PROJECT_ROOT / "app/services/upload/compression_strategy.py"
    assert not compression_strategy_path.exists()


def test_legacy_upload_language_detection_has_been_retired():
    language_detection_path = PROJECT_ROOT / "app/services/upload/language_detection.py"
    assert not language_detection_path.exists()


def test_legacy_upload_project_stats_has_been_retired():
    project_stats_path = PROJECT_ROOT / "app/services/upload/project_stats.py"
    assert not project_stats_path.exists()


def test_legacy_upload_manager_has_been_retired():
    upload_manager_path = PROJECT_ROOT / "app/services/upload/upload_manager.py"
    assert not upload_manager_path.exists()


def test_legacy_scanner_service_has_been_retired():
    scanner_path = PROJECT_ROOT / "app/services/scanner.py"
    assert not scanner_path.exists()


def test_legacy_gitleaks_rules_seed_service_has_been_retired():
    gitleaks_seed_path = PROJECT_ROOT / "app/services/gitleaks_rules_seed.py"
    assert not gitleaks_seed_path.exists()


def test_legacy_project_test_service_has_been_retired():
    project_test_service_path = PROJECT_ROOT / "app/services/project_test_service.py"
    assert not project_test_service_path.exists()


def test_legacy_flow_parser_runtime_service_has_been_retired():
    flow_parser_runtime_path = PROJECT_ROOT / "app/services/flow_parser_runtime.py"
    assert not flow_parser_runtime_path.exists()


def test_legacy_skill_test_runner_service_has_been_retired():
    skill_test_runner_path = PROJECT_ROOT / "app/services/agent/skill_test_runner.py"
    assert not skill_test_runner_path.exists()


def test_legacy_skill_test_agent_module_has_been_retired():
    skill_test_agent_path = PROJECT_ROOT / "app/services/agent/agents/skill_test.py"
    assert not skill_test_agent_path.exists()


def test_legacy_agent_skills_package_shell_has_been_retired():
    skills_package_init_path = PROJECT_ROOT / "app/services/agent/skills/__init__.py"
    assert not skills_package_init_path.exists()


def test_legacy_agent_knowledge_package_shell_has_been_retired():
    knowledge_package_init_path = PROJECT_ROOT / "app/services/agent/knowledge/__init__.py"
    assert not knowledge_package_init_path.exists()


def test_legacy_agent_knowledge_tools_module_has_been_retired():
    knowledge_tools_path = PROJECT_ROOT / "app/services/agent/knowledge/tools.py"
    assert not knowledge_tools_path.exists()


def test_legacy_tree_sitter_parser_service_has_been_retired():
    parser_path = PROJECT_ROOT / "app/services/parser.py"
    assert not parser_path.exists()


def test_legacy_sandbox_runner_client_service_has_been_retired():
    sandbox_runner_client_path = PROJECT_ROOT / "app/services/sandbox_runner_client.py"
    assert not sandbox_runner_client_path.exists()


def test_legacy_backend_venv_service_has_been_retired():
    backend_venv_path = PROJECT_ROOT / "app/services/backend_venv.py"
    assert not backend_venv_path.exists()


def test_legacy_user_config_service_has_been_retired():
    user_config_service_path = PROJECT_ROOT / "app/services/user_config_service.py"
    assert not user_config_service_path.exists()


def test_legacy_json_safe_service_has_been_retired():
    json_safe_path = PROJECT_ROOT / "app/services/json_safe.py"
    assert not json_safe_path.exists()


def test_legacy_flow_parser_runner_service_has_been_retired():
    flow_parser_runner_path = PROJECT_ROOT / "app/services/flow_parser_runner.py"
    assert not flow_parser_runner_path.exists()


def test_legacy_scanner_runner_service_has_been_retired():
    scanner_runner_path = PROJECT_ROOT / "app/services/scanner_runner.py"
    assert not scanner_runner_path.exists()


def test_legacy_static_scan_runtime_service_shell_has_been_retired():
    runtime_service_path = PROJECT_ROOT / "app/services/static_scan_runtime.py"
    assert not runtime_service_path.exists()


def test_legacy_runtime_tool_docs_scripts_have_been_retired():
    generate_script_path = PROJECT_ROOT / "scripts/generate_runtime_tool_docs.py"
    validate_script_path = PROJECT_ROOT / "scripts/validate_runtime_tool_docs.py"
    assert not generate_script_path.exists()
    assert not validate_script_path.exists()


def test_legacy_prompt_skills_helper_module_has_been_retired():
    prompt_skills_path = PROJECT_ROOT / "app/services/agent/skills/prompt_skills.py"
    assert not prompt_skills_path.exists()


def test_legacy_agent_telemetry_modules_have_been_retired():
    telemetry_init_path = PROJECT_ROOT / "app/services/agent/telemetry/__init__.py"
    telemetry_tracer_path = PROJECT_ROOT / "app/services/agent/telemetry/tracer.py"
    assert not telemetry_init_path.exists()
    assert not telemetry_tracer_path.exists()


def test_legacy_agent_workflow_package_init_has_been_retired():
    workflow_init_path = PROJECT_ROOT / "app/services/agent/workflow/__init__.py"
    assert not workflow_init_path.exists()


@pytest.mark.parametrize(
    ("module_name", "relative_path"),
    RETIRED_AGENT_WORKFLOW_CLUSTER_FILES,
    ids=[module_name for module_name, _ in RETIRED_AGENT_WORKFLOW_CLUSTER_FILES],
)
def test_legacy_agent_workflow_cluster_modules_have_been_retired(
    module_name: str, relative_path: str
):
    retired_module_path = PROJECT_ROOT / relative_path
    assert not retired_module_path.exists(), (
        f"retired agent workflow module {module_name} should stay deleted"
    )


def test_legacy_skill_resource_catalog_helper_has_been_retired():
    resource_catalog_path = PROJECT_ROOT / "app/services/agent/skills/resource_catalog.py"
    assert not resource_catalog_path.exists()


def test_legacy_business_logic_scan_modules_have_been_retired():
    tool_path = PROJECT_ROOT / "app/services/agent/tools/business_logic_scan_tool.py"
    agent_path = PROJECT_ROOT / "app/services/agent/agents/business_logic_scan.py"

    assert not tool_path.exists()
    assert not agent_path.exists()
