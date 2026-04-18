import ast
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_HELPER_IMPORTS = (
    "ensure_scan_workspace",
    "ensure_scan_project_dir",
    "ensure_scan_output_dir",
    "ensure_scan_logs_dir",
    "ensure_scan_meta_dir",
    "cleanup_scan_workspace",
    "copy_project_tree_to_scan_dir",
)
RETIRED_AGENT_PACKAGE_SHELL_IMPORT_GUARDS = (
    ("bootstrap", "app.services.agent.bootstrap", "app.services.agent", "bootstrap"),
    ("core", "app.services.agent.core", "app.services.agent", "core"),
    ("flow", "app.services.agent.flow", "app.services.agent", "flow"),
    (
        "frameworks",
        "app.services.agent.knowledge.frameworks",
        "app.services.agent.knowledge",
        "frameworks",
    ),
    ("logic", "app.services.agent.logic", "app.services.agent", "logic"),
    (
        "vulnerabilities",
        "app.services.agent.knowledge.vulnerabilities",
        "app.services.agent.knowledge",
        "vulnerabilities",
    ),
    ("memory", "app.services.agent.memory", "app.services.agent", "memory"),
    ("prompts", "app.services.agent.prompts", "app.services.agent", "prompts"),
    ("streaming", "app.services.agent.streaming", "app.services.agent", "streaming"),
    (
        "tool_runtime",
        "app.services.agent.tool_runtime",
        "app.services.agent",
        "tool_runtime",
    ),
    ("tools", "app.services.agent.tools", "app.services.agent", "tools"),
    (
        "tools_runtime",
        "app.services.agent.tools.runtime",
        "app.services.agent.tools",
        "runtime",
    ),
    ("utils", "app.services.agent.utils", "app.services.agent", "utils"),
)
RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_IMPORT_GUARDS = (
    (
        "probe_specs",
        "app.services.agent.tool_runtime.probe_specs",
        "app.services.agent.tool_runtime",
        "probe_specs",
    ),
    (
        "protocol_verify",
        "app.services.agent.tool_runtime.protocol_verify",
        "app.services.agent.tool_runtime",
        "protocol_verify",
    ),
    (
        "virtual_tools",
        "app.services.agent.tool_runtime.virtual_tools",
        "app.services.agent.tool_runtime",
        "virtual_tools",
    ),
)
RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_IMPORT_GUARDS = (
    (
        "circuit_breaker",
        "app.services.agent.core.circuit_breaker",
        "app.services.agent.core",
        "circuit_breaker",
    ),
    (
        "fallback",
        "app.services.agent.core.fallback",
        "app.services.agent.core",
        "fallback",
    ),
    (
        "graph_controller",
        "app.services.agent.core.graph_controller",
        "app.services.agent.core",
        "graph_controller",
    ),
    (
        "persistence",
        "app.services.agent.core.persistence",
        "app.services.agent.core",
        "persistence",
    ),
    (
        "rate_limiter",
        "app.services.agent.core.rate_limiter",
        "app.services.agent.core",
        "rate_limiter",
    ),
    (
        "retry",
        "app.services.agent.core.retry",
        "app.services.agent.core",
        "retry",
    ),
    (
        "validation",
        "app.services.agent.core.validation",
        "app.services.agent.core",
        "validation",
    ),
)


def _collect_direct_package_import_offenders(
    retired_package: str,
    parent_package: str,
    package_name: str,
) -> list[str]:
    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == retired_package:
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == retired_package:
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == parent_package:
                        for alias in node.names:
                            if alias.name == package_name:
                                offenders.append(
                                    f"{path}: from {parent_package} import {package_name}"
                                )

    return offenders


def _collect_direct_module_import_offenders(
    retired_module: str,
    parent_package: str | None = None,
    module_name: str | None = None,
) -> list[str]:
    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == retired_module:
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    resolved_module = _resolve_import_from_module(path, node)
                    if resolved_module == retired_module:
                        offenders.append(
                            f"{path}: from {'.' * node.level}{node.module or ''} import ..."
                        )
                        continue
                    if resolved_module == parent_package and module_name:
                        for alias in node.names:
                            if alias.name == module_name:
                                offenders.append(
                                    f"{path}: from {'.' * node.level}{node.module or ''} import {module_name}"
                                )

    return offenders


def _module_name_for_path(path: Path) -> str:
    relative_path = path.relative_to(PROJECT_ROOT)
    parts = list(relative_path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = path.stem
    return ".".join(parts)


def _resolve_import_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    current_module = _module_name_for_path(path)
    current_package_parts = current_module.split(".")
    if path.name != "__init__.py":
        current_package_parts = current_package_parts[:-1]

    ascents = max(node.level - 1, 0)
    if ascents > len(current_package_parts):
        return node.module

    base_parts = current_package_parts[: len(current_package_parts) - ascents]
    if node.module:
        return ".".join([*base_parts, node.module])
    return ".".join(base_parts)


def test_no_live_python_module_imports_skill_test_runner():
    retired_module = PROJECT_ROOT / "app/services/agent/skill_test_runner.py"
    assert not retired_module.exists(), "retired skill_test_runner helper should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.skill_test_runner":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.skill_test_runner":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent":
                        for alias in node.names:
                            if alias.name == "skill_test_runner":
                                offenders.append(
                                    f"{path}: from app.services.agent import skill_test_runner"
                                )

    assert not offenders, (
        "retired skill_test_runner helper should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_skill_test_agent_module():
    retired_module = PROJECT_ROOT / "app/services/agent/agents/skill_test.py"
    assert not retired_module.exists(), "retired agent skill_test module should stay deleted"

    offenders = _collect_direct_module_import_offenders(
        retired_module="app.services.agent.agents.skill_test",
        parent_package="app.services.agent.agents",
        module_name="skill_test",
    )

    assert not offenders, (
        "retired agent skill_test module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_bootstrap_callers_use_agent_scan_workspace_module():
    caller_paths = [
        PROJECT_ROOT / "app/services/agent/bootstrap/opengrep.py",
        PROJECT_ROOT / "app/services/agent/bootstrap/phpstan.py",
    ]

    for path in caller_paths:
        content = path.read_text(encoding="utf-8")
        module = ast.parse(content, filename=str(path))
        import_from_nodes = [node for node in ast.walk(module) if isinstance(node, ast.ImportFrom)]

        required_nodes = [
            node
            for node in import_from_nodes
            if node.module == "app.services.agent.scan_workspace"
        ]
        assert required_nodes, f"{path.name} should import workspace helpers from agent.scan_workspace"

        forbidden_names = {
            alias.name
            for node in import_from_nodes
            if node.module == "app.services.static_scan_runtime"
            for alias in node.names
        }
        leaked_helpers = sorted(forbidden_names.intersection(WORKSPACE_HELPER_IMPORTS))
        assert not leaked_helpers, (
            f"{path.name} still imports workspace helpers from static_scan_runtime: "
            f"{', '.join(leaked_helpers)}"
        )


def test_no_live_python_module_imports_static_scan_runtime():
    retired_module = PROJECT_ROOT / "app/services/static_scan_runtime.py"
    assert not retired_module.exists(), "retired static_scan_runtime service shell should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.static_scan_runtime":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.static_scan_runtime":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services":
                        for alias in node.names:
                            if alias.name == "static_scan_runtime":
                                offenders.append(f"{path}: from app.services import static_scan_runtime")

    assert not offenders, (
        "retired static_scan_runtime service shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_db_session():
    retired_module = PROJECT_ROOT / "app/db/session.py"
    assert not retired_module.exists(), "retired db.session module should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.db.session":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.db.session":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.db":
                        for alias in node.names:
                            if alias.name == "session":
                                offenders.append(f"{path}: from app.db import session")

    assert not offenders, (
        "retired db.session module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_db_base():
    retired_module = PROJECT_ROOT / "app/db/base.py"
    assert not retired_module.exists(), "retired db.base module should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.db.base":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.db.base":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.db":
                        for alias in node.names:
                            if alias.name == "base":
                                offenders.append(f"{path}: from app.db import base")

    assert not offenders, (
        "retired db.base module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_prompt_skills_helper():
    retired_module = PROJECT_ROOT / "app/services/agent/skills/prompt_skills.py"
    assert not retired_module.exists(), "retired prompt_skills helper should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.skills.prompt_skills":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.skills.prompt_skills":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent.skills":
                        for alias in node.names:
                            if alias.name == "prompt_skills":
                                offenders.append(
                                    f"{path}: from app.services.agent.skills import prompt_skills"
                                )

    assert not offenders, (
        "retired prompt_skills helper should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_skill_resource_catalog_helper():
    retired_module = PROJECT_ROOT / "app/services/agent/skills/resource_catalog.py"
    assert not retired_module.exists(), "retired resource_catalog helper should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.skills.resource_catalog":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.skills.resource_catalog":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent.skills":
                        for alias in node.names:
                            if alias.name == "resource_catalog":
                                offenders.append(
                                    f"{path}: from app.services.agent.skills import resource_catalog"
                                )

    assert not offenders, (
        "retired resource_catalog helper should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_agent_skills_package_shell():
    retired_module = PROJECT_ROOT / "app/services/agent/skills/__init__.py"
    assert not retired_module.exists(), "retired agent skills package shell should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.skills":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.skills":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent":
                        for alias in node.names:
                            if alias.name == "skills":
                                offenders.append(f"{path}: from app.services.agent import skills")

    assert not offenders, (
        "retired agent skills package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_agent_knowledge_package_shell():
    retired_module = PROJECT_ROOT / "app/services/agent/knowledge/__init__.py"
    assert not retired_module.exists(), "retired agent knowledge package shell should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.knowledge":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.knowledge":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent":
                        for alias in node.names:
                            if alias.name == "knowledge":
                                offenders.append(
                                    f"{path}: from app.services.agent import knowledge"
                                )
                    if node.level and node.module == "knowledge":
                        offenders.append(
                            f"{path}: from {'.' * node.level}{node.module} import ..."
                        )

    assert not offenders, (
        "retired agent knowledge package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_agent_knowledge_tools_module():
    retired_module = PROJECT_ROOT / "app/services/agent/knowledge/tools.py"
    assert not retired_module.exists(), "retired agent knowledge.tools module should stay deleted"

    offenders = _collect_direct_module_import_offenders(
        retired_module="app.services.agent.knowledge.tools",
        parent_package="app.services.agent.knowledge",
        module_name="tools",
    )

    assert not offenders, (
        "retired agent knowledge.tools module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    ("shell_name", "retired_package", "parent_package", "package_name"),
    RETIRED_AGENT_PACKAGE_SHELL_IMPORT_GUARDS,
    ids=[shell_name for shell_name, *_ in RETIRED_AGENT_PACKAGE_SHELL_IMPORT_GUARDS],
)
def test_no_live_python_module_imports_retired_agent_subpackage_shell(
    shell_name: str,
    retired_package: str,
    parent_package: str,
    package_name: str,
):
    retired_module = PROJECT_ROOT / retired_package.replace(".", "/") / "__init__.py"
    assert not retired_module.exists(), f"retired agent {shell_name} package shell should stay deleted"

    offenders = _collect_direct_package_import_offenders(
        retired_package=retired_package,
        parent_package=parent_package,
        package_name=package_name,
    )

    assert not offenders, (
        f"retired agent {shell_name} package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_tools_runtime_package_shell_via_relative_or_absolute_imports():
    retired_module = PROJECT_ROOT / "app/services/agent/tools/runtime/__init__.py"
    assert not retired_module.exists(), "retired agent tools.runtime package shell should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "alembic",
    ]
    retired_package = "app.services.agent.tools.runtime"
    parent_package = "app.services.agent.tools"
    offenders: list[str] = []

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == retired_package:
                            offenders.append(f"{path}: import {alias.name}")
                if not isinstance(node, ast.ImportFrom):
                    continue

                resolved_module = _resolve_import_from_module(path, node)
                if resolved_module == retired_package:
                    offenders.append(
                        f"{path}: from {'.' * node.level}{node.module or ''} import ..."
                    )
                    continue

                if resolved_module == parent_package:
                    for alias in node.names:
                        if alias.name == "runtime":
                            offenders.append(
                                f"{path}: from {'.' * node.level}{node.module or ''} import runtime"
                            )

    assert not offenders, (
        "retired agent tools.runtime package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_agent_knowledge_callers_import_loader_directly():
    caller_paths = [
        PROJECT_ROOT / "app/services/agent/agents/base.py",
        PROJECT_ROOT / "app/services/agent/tools/agent_tools.py",
    ]

    for path in caller_paths:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        import_from_nodes = [node for node in ast.walk(module) if isinstance(node, ast.ImportFrom)]

        direct_loader_imports = [
            node
            for node in import_from_nodes
            if node.level == 2
            and node.module == "knowledge.loader"
            and any(alias.name == "knowledge_loader" for alias in node.names)
        ]
        assert direct_loader_imports, (
            f"{path.name} should import knowledge_loader from ..knowledge.loader"
        )

        package_root_imports = [
            node
            for node in import_from_nodes
            if node.level == 2
            and node.module == "knowledge"
            and any(alias.name == "knowledge_loader" for alias in node.names)
        ]
        assert not package_root_imports, (
            f"{path.name} should not import knowledge_loader from ..knowledge"
        )


def test_no_live_python_module_imports_agent_workflow_package():
    retired_module = PROJECT_ROOT / "app/services/agent/workflow/__init__.py"
    assert not retired_module.exists(), "retired workflow package convenience module should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
    ]
    offenders: list[str] = []

    for root in python_roots:
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent.workflow":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module == "app.services.agent.workflow":
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent":
                        for alias in node.names:
                            if alias.name == "workflow":
                                offenders.append(
                                    f"{path}: from app.services.agent import workflow"
                                )

    assert not offenders, (
        "retired workflow package convenience module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_retired_agent_workflow_cluster_modules():
    retired_modules = [
        PROJECT_ROOT / "app/services/agent/workflow/engine.py",
        PROJECT_ROOT / "app/services/agent/workflow/models.py",
        PROJECT_ROOT / "app/services/agent/workflow/parallel_executor.py",
        PROJECT_ROOT / "app/services/agent/workflow/memory_monitor.py",
        PROJECT_ROOT / "app/services/agent/workflow/workflow_orchestrator.py",
    ]
    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []

    for retired_module in retired_modules:
        assert not retired_module.exists(), f"retired workflow module should stay deleted: {retired_module}"

    retired_import_roots = (
        "app.services.agent.workflow.engine",
        "app.services.agent.workflow.models",
        "app.services.agent.workflow.parallel_executor",
        "app.services.agent.workflow.memory_monitor",
        "app.services.agent.workflow.workflow_orchestrator",
    )

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in retired_import_roots:
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module in retired_import_roots:
                        offenders.append(f"{path}: from {node.module} import ...")

    assert not offenders, (
        "retired workflow cluster modules should have no live Python direct importers:\n"
        + "\n".join(offenders)
    )


def test_agent_package_convenience_module_has_been_retired():
    agent_init_path = PROJECT_ROOT / "app/services/agent/__init__.py"
    assert not agent_init_path.exists(), "retired agent package convenience module should stay deleted"


def test_no_live_python_module_imports_agent_package_convenience_module():
    retired_module = PROJECT_ROOT / "app/services/agent/__init__.py"
    assert not retired_module.exists(), "retired agent package convenience module should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "app.services.agent":
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom) and node.module == "app.services.agent":
                    offenders.append(f"{path}: from {node.module} import ...")

    assert not offenders, (
        "retired agent package convenience module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_retired_agent_telemetry():
    retired_module = PROJECT_ROOT / "app/services/agent/telemetry/tracer.py"
    assert not retired_module.exists(), "retired agent telemetry tracer should stay deleted"

    python_roots = [
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "alembic",
    ]
    offenders: list[str] = []
    retired_symbols = {"telemetry", "Tracer", "get_global_tracer", "set_global_tracer"}

    for root in python_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in {
                            "app.services.agent.telemetry",
                            "app.services.agent.telemetry.tracer",
                        }:
                            offenders.append(f"{path}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module in {
                        "app.services.agent.telemetry",
                        "app.services.agent.telemetry.tracer",
                    }:
                        offenders.append(f"{path}: from {node.module} import ...")
                    if node.module == "app.services.agent":
                        for alias in node.names:
                            if alias.name in retired_symbols:
                                offenders.append(
                                    f"{path}: from app.services.agent import {alias.name}"
                                )

    assert not offenders, (
        "retired agent telemetry helpers should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_business_logic_scan_tool():
    retired_module = PROJECT_ROOT / "app/services/agent/tools/business_logic_scan_tool.py"
    assert not retired_module.exists(), "retired business_logic_scan tool should stay deleted"

    offenders = _collect_direct_module_import_offenders(
        retired_module="app.services.agent.tools.business_logic_scan_tool",
        parent_package="app.services.agent.tools",
        module_name="business_logic_scan_tool",
    )

    assert not offenders, (
        "retired business_logic_scan tool should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_no_live_python_module_imports_business_logic_scan_agent_module():
    retired_module = PROJECT_ROOT / "app/services/agent/agents/business_logic_scan.py"
    assert not retired_module.exists(), "retired business_logic_scan agent should stay deleted"

    offenders = _collect_direct_module_import_offenders(
        retired_module="app.services.agent.agents.business_logic_scan",
        parent_package="app.services.agent.agents",
        module_name="business_logic_scan",
    )

    assert not offenders, (
        "retired business_logic_scan agent module should have no live Python importers:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    ("module_name", "retired_module_name", "parent_package", "import_name"),
    RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_IMPORT_GUARDS,
    ids=[module_name for module_name, *_ in RETIRED_TOOL_RUNTIME_ORPHAN_CLUSTER_IMPORT_GUARDS],
)
def test_no_live_python_module_imports_retired_tool_runtime_orphan_cluster_modules(
    module_name: str,
    retired_module_name: str,
    parent_package: str,
    import_name: str,
):
    retired_module = PROJECT_ROOT / retired_module_name.replace(".", "/")
    retired_module = retired_module.with_suffix(".py")
    assert not retired_module.exists(), (
        f"retired tool_runtime orphan cluster module should stay deleted: {module_name}"
    )

    offenders = _collect_direct_module_import_offenders(
        retired_module=retired_module_name,
        parent_package=parent_package,
        module_name=import_name,
    )

    assert not offenders, (
        f"retired tool_runtime orphan cluster module should have no live Python importers: "
        f"{module_name}\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    ("module_name", "retired_module_name", "parent_package", "import_name"),
    RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_IMPORT_GUARDS,
    ids=[module_name for module_name, *_ in RETIRED_AGENT_CORE_ORPHAN_SUPPORT_CLUSTER_IMPORT_GUARDS],
)
def test_no_live_python_module_imports_retired_agent_core_orphan_support_cluster_modules(
    module_name: str,
    retired_module_name: str,
    parent_package: str,
    import_name: str,
):
    retired_module = PROJECT_ROOT / retired_module_name.replace(".", "/")
    retired_module = retired_module.with_suffix(".py")
    assert not retired_module.exists(), (
        f"retired agent core orphan support cluster module should stay deleted: {module_name}"
    )

    offenders = _collect_direct_module_import_offenders(
        retired_module=retired_module_name,
        parent_package=parent_package,
        module_name=import_name,
    )

    assert not offenders, (
        "retired agent core orphan support cluster module should have no live Python "
        f"importers: {module_name}\n" + "\n".join(offenders)
    )


def test_agents_package_no_longer_reexports_business_logic_scan_agent():
    agents_package_path = PROJECT_ROOT / "app/services/agent/agents/__init__.py"
    if not agents_package_path.exists():
        return
    module = ast.parse(agents_package_path.read_text(encoding="utf-8"), filename=str(agents_package_path))

    offending_imports: list[str] = []
    exported_symbols: list[str] = []

    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            resolved_module = _resolve_import_from_module(agents_package_path, node)
            if resolved_module == "app.services.agent.agents.business_logic_scan":
                offending_imports.append(
                    f"from {'.' * node.level}{node.module or ''} import "
                    + ", ".join(alias.name for alias in node.names)
                )

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        if isinstance(value, list):
            exported_symbols.extend(str(item) for item in value)

    assert not offending_imports, (
        "agents package should not import the retired business_logic_scan module:\n"
        + "\n".join(offending_imports)
    )
    assert "BusinessLogicScanAgent" not in exported_symbols
