from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "backend" / "alembic" / "versions"


def _read_revision_fields(path: Path) -> tuple[str, list[str]]:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = None
    down_revisions: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue

        targets: list[ast.expr]
        value: ast.expr
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            targets = list(node.targets)
            value = node.value

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "revision":
                revision = ast.literal_eval(value)
            if target.id == "down_revision":
                raw_value = ast.literal_eval(value)
                if raw_value is None:
                    down_revisions = []
                elif isinstance(raw_value, str):
                    down_revisions = [raw_value]
                else:
                    down_revisions = list(raw_value)

    assert isinstance(revision, str), f"missing revision in {path}"
    return revision, down_revisions


def test_alembic_history_has_single_linear_head() -> None:
    revisions: dict[str, list[str]] = {}
    referenced_revisions: set[str] = set()
    child_count_by_revision: dict[str, int] = {}

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        revision, down_revisions = _read_revision_fields(path)
        revisions[revision] = down_revisions
        referenced_revisions.update(down_revisions)
        assert len(down_revisions) <= 1, f"merge revision is not allowed: {path.name}"
        for parent_revision in down_revisions:
            child_count_by_revision[parent_revision] = (
                child_count_by_revision.get(parent_revision, 0) + 1
            )

    heads = sorted(set(revisions) - referenced_revisions)

    assert len(heads) == 1, f"expected exactly one alembic head, found {heads}"
    branchpoints = sorted(
        revision
        for revision, child_count in child_count_by_revision.items()
        if child_count > 1
    )
    assert not branchpoints, f"branchpoint revisions are not allowed: {branchpoints}"
