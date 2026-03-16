"""normalize static finding paths

Revision ID: 7f8e9d0c1b2a
Revises: 6c8d9e0f1a2b
Create Date: 2026-03-14 20:30:00.000000

"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op
from sqlalchemy import text

from app.db.static_finding_paths import (
    collect_zip_relative_paths,
    resolve_legacy_static_finding_path,
)


# revision identifiers, used by Alembic.
revision = "7f8e9d0c1b2a"
down_revision = "6c8d9e0f1a2b"
branch_labels = None
depends_on = None


def _resolve_zip_path(project_id: str, zip_storage_path: Path) -> Path | None:
    direct = zip_storage_path / f"{project_id}.zip"
    if direct.exists():
        return direct

    for candidate in sorted(zip_storage_path.glob(f"{project_id}_*.zip")):
        if candidate.exists():
            return candidate
    return None


def _backfill_table_paths(
    table_name: str,
    scan_task_table: str,
    zip_storage_path: Path,
) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        text(
            f"""
            SELECT f.id, f.file_path, t.project_id
            FROM {table_name} AS f
            JOIN {scan_task_table} AS t ON t.id = f.scan_task_id
            WHERE f.file_path LIKE '/tmp/%'
            """
        )
    ).fetchall()

    known_paths_by_project: dict[str, set[str]] = {}

    for row in rows:
        finding_id = str(row.id)
        file_path = str(row.file_path or "")
        project_id = str(row.project_id or "")
        if not project_id or not file_path:
            continue

        known_paths = known_paths_by_project.get(project_id)
        if known_paths is None:
            zip_path = _resolve_zip_path(project_id, zip_storage_path)
            if not zip_path:
                known_paths_by_project[project_id] = set()
                continue
            known_paths = collect_zip_relative_paths(zip_path)
            known_paths_by_project[project_id] = known_paths

        if not known_paths:
            continue

        resolved = resolve_legacy_static_finding_path(file_path, known_paths)
        if not resolved or resolved == file_path:
            continue

        connection.execute(
            text(f"UPDATE {table_name} SET file_path = :file_path WHERE id = :finding_id"),
            {
                "file_path": resolved,
                "finding_id": finding_id,
            },
        )


def upgrade() -> None:
    zip_storage_path = Path(os.environ.get("ZIP_STORAGE_PATH", "./uploads/zip_files"))
    _backfill_table_paths("bandit_findings", "bandit_scan_tasks", zip_storage_path)
    _backfill_table_paths("opengrep_findings", "opengrep_scan_tasks", zip_storage_path)


def downgrade() -> None:
    pass
