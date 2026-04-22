import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_PUSH_FINDING_PAYLOAD_MODULE = (
    "push_finding_payload",
    PROJECT_ROOT / "app/services/agent/push_finding_payload.py",
    "app.services.agent.push_finding_payload",
)


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


def _resolve_import_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    module = node.module or ""
    if node.level == 0:
        return module or None

    relative_path = path.relative_to(PROJECT_ROOT)
    package_parts = list(relative_path.with_suffix("").parts)
    if package_parts[-1] == "__init__":
        package_parts.pop()
    else:
        package_parts.pop()

    if node.level > len(package_parts):
        return module or None

    base_parts = package_parts[: len(package_parts) - node.level + 1]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def test_push_finding_payload_module_stays_deleted():
    _, path, _ = RETIRED_PUSH_FINDING_PAYLOAD_MODULE
    assert not path.exists(), "push_finding_payload helper should stay deleted"


def test_push_finding_payload_module_has_no_live_python_importers():
    module_name, _, dotted_module = RETIRED_PUSH_FINDING_PAYLOAD_MODULE
    offenders = _collect_direct_module_import_offenders(
        dotted_module,
        ".".join(dotted_module.split(".")[:-1]),
        dotted_module.rsplit(".", 1)[-1],
    )
    assert not offenders, (
        f"retired push_finding_payload module {module_name} should have no live Python importers:\n"
        + "\n".join(offenders)
    )
