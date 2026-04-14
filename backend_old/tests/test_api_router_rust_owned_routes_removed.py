from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

def test_legacy_api_router_module_has_been_retired():
    api_router_path = PROJECT_ROOT / "app/api/v1/api.py"
    assert not api_router_path.exists()


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


def test_legacy_init_db_module_has_been_retired():
    init_db_path = PROJECT_ROOT / "app/db/init_db.py"
    assert not init_db_path.exists()


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
