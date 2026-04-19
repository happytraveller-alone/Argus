import ast
import io
import tokenize
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOTS = ("app", "scripts", "tests", "alembic")
RETIRED_MODULES = (
    (
        "security",
        PROJECT_ROOT / "app/core/security.py",
        "app.core.security",
        "app.core",
        "security",
    ),
    (
        "encryption",
        PROJECT_ROOT / "app/core/encryption.py",
        "app.core.encryption",
        "app.core",
        "encryption",
    ),
)


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


def _iter_import_statements(path: Path):
    reader = io.StringIO(path.read_text(encoding="utf-8")).readline
    tokens = tokenize.generate_tokens(reader)
    statement_tokens = []
    statement_start_line = None
    at_statement_start = True
    bracket_depth = 0

    def build_statement(tokens):
        return tokenize.untokenize((item.type, item.string) for item in tokens)

    for token in tokens:
        token_type = token.type
        token_string = token.string

        if not statement_tokens:
            if token_type in {
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NL,
                tokenize.NEWLINE,
            }:
                at_statement_start = True
                continue
            if token_type == tokenize.COMMENT:
                continue
            if token_type == tokenize.OP and token_string == ";":
                at_statement_start = True
                continue
            if (
                at_statement_start
                and token_type == tokenize.NAME
                and token_string in {"import", "from"}
            ):
                statement_tokens = [token]
                statement_start_line = token.start[0]
                at_statement_start = False
                continue
            at_statement_start = False
            continue

        statement_tokens.append(token)
        if token_type == tokenize.OP and token_string in "([{":
            bracket_depth += 1
        elif token_type == tokenize.OP and token_string in ")]}":
            bracket_depth = max(0, bracket_depth - 1)

        if token_type == tokenize.OP and token_string == ";" and bracket_depth == 0:
            yield build_statement(statement_tokens[:-1]), statement_start_line
            statement_tokens = []
            statement_start_line = None
            at_statement_start = True
            continue

        if token_type == tokenize.NEWLINE and bracket_depth == 0:
            yield build_statement(statement_tokens), statement_start_line
            statement_tokens = []
            statement_start_line = None
            at_statement_start = True
            continue

        if token_type == tokenize.ENDMARKER and statement_tokens:
            yield build_statement(statement_tokens), statement_start_line


def _collect_direct_import_offenders(
    retired_module: str,
    parent_package: str,
    symbol: str,
) -> list[str]:
    offenders: list[str] = []

    for root_name in PYTHON_ROOTS:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for statement, start_line in _iter_import_statements(path):
                module = ast.parse(statement)
                for node in module.body:
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == retired_module:
                                offenders.append(
                                    f"{path}:{start_line}: {statement.strip()}"
                                )
                    if isinstance(node, ast.ImportFrom):
                        resolved_module = _resolve_import_from_module(path, node)
                        if resolved_module == retired_module:
                            offenders.append(f"{path}:{start_line}: {statement.strip()}")
                            continue
                        if resolved_module == parent_package:
                            for alias in node.names:
                                if alias.name == symbol:
                                    offenders.append(
                                        f"{path}:{start_line}: {statement.strip()}"
                                    )
                                    break

    return offenders


def test_retired_core_security_and_encryption_modules_stay_deleted():
    existing = [label for label, path, *_ in RETIRED_MODULES if path.exists()]
    assert not existing, (
        "retired core security/encryption modules should stay deleted:\n"
        + "\n".join(existing)
    )


def test_retired_core_security_and_encryption_modules_have_no_live_python_importers():
    offenders = []
    for _, _, module_name, parent_package, symbol in RETIRED_MODULES:
        offenders.extend(_collect_direct_import_offenders(module_name, parent_package, symbol))

    assert not offenders, (
        "retired core security/encryption modules should have no live Python importers:\n"
        + "\n".join(offenders)
    )
