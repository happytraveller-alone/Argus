from __future__ import annotations

import ast
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load_revision_metadata() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = None
        down_revision = None
        for node in module.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_id = node.target.id
                value = node.value
            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                target_id = node.targets[0].id
                value = node.value
            else:
                continue

            if target_id == "revision":
                revision = ast.literal_eval(value)
            if target_id == "down_revision":
                down_revision = ast.literal_eval(value)
        if revision is None:
            continue
        rows.append(
            {
                "path": path,
                "revision": revision,
                "down_revision": down_revision,
            }
        )
    return rows


def test_alembic_revisions_are_unique_and_single_head():
    rows = _load_revision_metadata()
    revisions = [str(row["revision"]) for row in rows]

    assert len(revisions) == len(set(revisions))

    parents: set[str] = set()
    for row in rows:
        down_revision = row["down_revision"]
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            parents.update(str(item) for item in down_revision)
        else:
            parents.add(str(down_revision))

    heads = [revision for revision in revisions if revision not in parents]
    assert heads == ["e1f2a3b4c5d6"]


def test_pmd_migration_follows_prompt_skills_migration():
    rows = _load_revision_metadata()
    pmd_row = next(row for row in rows if row["revision"] == "da4e5f6a7b8c")
    assert pmd_row["down_revision"] == "d4e5f6a7b8c9"


def test_pmd_scan_tables_migration_follows_pmd_rule_configs():
    rows = _load_revision_metadata()
    pmd_scan_row = next(row for row in rows if row["revision"] == "e1f2a3b4c5d6")
    assert pmd_scan_row["down_revision"] == "da4e5f6a7b8c"
