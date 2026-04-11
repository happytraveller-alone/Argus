from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import UniqueConstraint, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models as _all_models  # noqa: F401  # Ensure all models are registered
from app.db.base import Base
from app.db.init_db import DEFAULT_DEMO_EMAIL, _build_default_seed_projects
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.zip_storage import (
    delete_project_zip,
    get_project_zip_meta,
    load_project_zip,
    save_project_zip,
)

logger = logging.getLogger(__name__)

TRANSFER_SCOPE = "project-domain"
TRANSFER_EXPORT_VERSION = "project-export-v1"
TRANSFER_BUNDLE_PREFIX = "deepaudit-project-export-v1"


@dataclass
class ProjectExportBundle:
    path: str
    filename: str
    manifest: dict[str, Any]


@dataclass
class ProjectImportSummary:
    imported_projects: list[dict[str, Any]]
    skipped_projects: list[dict[str, Any]]
    failed_projects: list[dict[str, Any]]
    warnings: list[str]


@dataclass(frozen=True)
class DomainForeignKey:
    child_column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class DomainModelSpec:
    table_name: str
    model: type
    primary_keys: tuple[str, ...]
    foreign_keys: tuple[DomainForeignKey, ...]
    unique_columns: tuple[tuple[str, ...], ...]
    user_fk_columns: tuple[str, ...]


_DOMAIN_SPEC_CACHE: tuple[list[str], dict[str, DomainModelSpec]] | None = None


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _to_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=_json_default,
    ).encode("utf-8")


def _column_names(model: type) -> list[str]:
    return [column.name for column in model.__table__.columns]


def _model_to_dict(instance: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column_name in _column_names(type(instance)):
        value = getattr(instance, column_name)
        if isinstance(value, datetime):
            data[column_name] = value.isoformat()
        else:
            data[column_name] = value
    return data


def _stable_sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
        identifier = str(item.get("id") or "")
        fallback = json.dumps(item, sort_keys=True, default=_json_default, ensure_ascii=False)
        return identifier, fallback

    return sorted(rows, key=_sort_key)


def _parse_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return value


def _coerce_row_for_model(model: type, row: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        if value is None:
            data[column.name] = None
            continue
        python_type = getattr(column.type, "python_type", None)
        if python_type is datetime:
            data[column.name] = _parse_datetime(value)
        else:
            data[column.name] = value
    return data


def _compute_file_sha256(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str:
    try:
        backend_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=backend_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "unknown"
    except Exception:
        pass
    return "unknown"


def _default_seed_descriptors() -> list[dict[str, str]]:
    descriptors: list[dict[str, str]] = []
    for seed in _build_default_seed_projects():
        descriptors.append(
            {
                "name": str(seed.name or "").strip(),
                "archive_name": str(seed.archive_name or "").strip(),
                "owner": str(seed.owner or "").strip(),
                "repo": str(seed.repo or "").strip(),
                "ref": str(seed.ref or "").strip(),
            }
        )
    return descriptors


def _is_seed_project(project: Project, owner: User | None, zip_meta: dict[str, Any] | None) -> bool:
    if not owner or str(owner.email or "").strip().lower() != DEFAULT_DEMO_EMAIL.lower():
        return False

    original_filename = str((zip_meta or {}).get("original_filename") or "").strip()
    project_name = str(project.name or "").strip()
    repository_url = str(project.repository_url or "").strip().lower()

    for seed in _default_seed_descriptors():
        if project_name and project_name == seed["name"]:
            return True
        if original_filename and original_filename == seed["archive_name"]:
            return True
        if repository_url and seed["owner"] and seed["repo"]:
            repo_slug = f"{seed['owner']}/{seed['repo']}".lower()
            if repo_slug in repository_url:
                return True
    return False


def _model_registry_by_table() -> dict[str, type]:
    registry: dict[str, type] = {}
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table = getattr(model, "__table__", None)
        if table is None:
            continue
        registry[table.name] = model
    return registry


def _iter_unique_column_sets(model: type) -> tuple[tuple[str, ...], ...]:
    unique_sets: list[tuple[str, ...]] = []

    for column in model.__table__.columns:
        if getattr(column, "unique", False):
            unique_sets.append((column.name,))

    for constraint in model.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            columns = tuple(column.name for column in constraint.columns)
            if columns:
                unique_sets.append(columns)

    for index in model.__table__.indexes:
        if not getattr(index, "unique", False):
            continue
        columns = tuple(getattr(column, "name", "") for column in index.columns)
        columns = tuple(column for column in columns if column)
        if columns:
            unique_sets.append(columns)

    deduped: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for column_set in unique_sets:
        if column_set in seen:
            continue
        seen.add(column_set)
        deduped.append(column_set)
    return tuple(deduped)


def _user_fk_columns(model: type) -> tuple[str, ...]:
    user_columns: list[str] = []
    for column in model.__table__.columns:
        for foreign_key in column.foreign_keys:
            if foreign_key.column.table.name == "users" and foreign_key.column.name == "id":
                user_columns.append(column.name)
                break
    return tuple(user_columns)


def _discover_project_domain_specs() -> tuple[list[str], dict[str, DomainModelSpec]]:
    model_by_table = _model_registry_by_table()
    root_table = Project.__table__.name
    if root_table not in model_by_table:
        raise RuntimeError("Project model is not registered")

    children_by_parent: dict[str, set[str]] = defaultdict(set)
    explicit_fks_by_child: dict[str, list[DomainForeignKey]] = defaultdict(list)

    for child_table, model in model_by_table.items():
        for foreign_key in model.__table__.foreign_keys:
            parent_table = foreign_key.column.table.name
            if parent_table not in model_by_table:
                continue
            children_by_parent[parent_table].add(child_table)
            explicit_fks_by_child[child_table].append(
                DomainForeignKey(
                    child_column=foreign_key.parent.name,
                    parent_table=parent_table,
                    parent_column=foreign_key.column.name,
                )
            )

    domain_tables: set[str] = {root_table}
    queue: deque[str] = deque([root_table])
    while queue:
        parent = queue.popleft()
        for child in sorted(children_by_parent.get(parent, set())):
            if child in domain_tables:
                continue
            domain_tables.add(child)
            queue.append(child)

    soft_edges: set[tuple[str, str]] = set()
    for table_name in domain_tables:
        model = model_by_table[table_name]
        explicit_fk_columns = {fk.child_column for fk in explicit_fks_by_child.get(table_name, [])}
        table_prefix = table_name.split("_", 1)[0]

        for column in model.__table__.columns:
            if column.name in explicit_fk_columns:
                continue
            if not column.name.endswith("_id"):
                continue

            stem = column.name[:-3]
            candidates = [f"{table_prefix}_{stem}s", f"{stem}s"]
            for candidate in candidates:
                if candidate not in domain_tables or candidate == table_name:
                    continue
                candidate_model = model_by_table[candidate]
                candidate_pk = tuple(col.name for col in candidate_model.__table__.primary_key.columns)
                if "id" not in candidate_pk:
                    continue
                soft_edges.add((candidate, table_name))

    indegree: dict[str, int] = {table: 0 for table in domain_tables}
    edges: dict[str, set[str]] = {table: set() for table in domain_tables}

    for parent, children in children_by_parent.items():
        if parent not in domain_tables:
            continue
        for child in children:
            if child not in domain_tables:
                continue
            if child not in edges[parent]:
                edges[parent].add(child)
                indegree[child] += 1

    for parent, child in soft_edges:
        if child not in edges[parent]:
            edges[parent].add(child)
            indegree[child] += 1

    topo_queue: list[str] = sorted([table for table, degree in indegree.items() if degree == 0])
    table_order: list[str] = []
    while topo_queue:
        current = topo_queue.pop(0)
        table_order.append(current)
        for child in sorted(edges[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                topo_queue.append(child)
                topo_queue.sort()

    if len(table_order) != len(domain_tables):
        remaining = sorted(domain_tables - set(table_order))
        table_order.extend(remaining)

    specs: dict[str, DomainModelSpec] = {}
    for table_name in table_order:
        model = model_by_table[table_name]
        primary_keys = tuple(column.name for column in model.__table__.primary_key.columns)
        foreign_keys = tuple(
            sorted(
                [
                    fk
                    for fk in explicit_fks_by_child.get(table_name, [])
                    if fk.parent_table in domain_tables
                ],
                key=lambda item: (item.parent_table, item.child_column, item.parent_column),
            )
        )
        specs[table_name] = DomainModelSpec(
            table_name=table_name,
            model=model,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            unique_columns=_iter_unique_column_sets(model),
            user_fk_columns=_user_fk_columns(model),
        )

    return table_order, specs


def _project_domain_specs() -> tuple[list[str], dict[str, DomainModelSpec]]:
    global _DOMAIN_SPEC_CACHE
    if _DOMAIN_SPEC_CACHE is None:
        _DOMAIN_SPEC_CACHE = _discover_project_domain_specs()
    return _DOMAIN_SPEC_CACHE


def _referenced_columns(table_order: list[str], specs: dict[str, DomainModelSpec]) -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {table: set() for table in table_order}
    for table_name in table_order:
        for primary_key in specs[table_name].primary_keys:
            columns[table_name].add(primary_key)

    for table_name in table_order:
        for foreign_key in specs[table_name].foreign_keys:
            columns[foreign_key.parent_table].add(foreign_key.parent_column)
    return columns


async def _resolve_export_projects(
    db: AsyncSession,
    current_user: User,
    project_ids: list[str] | None,
) -> tuple[list[Project], list[dict[str, Any]], list[str]]:
    member_result = await db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)
    )
    member_project_ids = [row[0] for row in member_result.all()]

    query = select(Project).options(selectinload(Project.owner))
    query = query.where(
        or_(Project.owner_id == current_user.id, Project.id.in_(member_project_ids or ["__none__"]))
    )
    if project_ids:
        query = query.where(Project.id.in_(project_ids))

    result = await db.execute(query.order_by(Project.created_at.asc(), Project.id.asc()))
    candidates = result.scalars().all()

    exportable: list[Project] = []
    excluded_seed_projects: list[dict[str, Any]] = []
    warnings: list[str] = []

    for project in candidates:
        zip_meta = await get_project_zip_meta(project.id)
        if _is_seed_project(project, getattr(project, "owner", None), zip_meta):
            excluded_seed_projects.append({"id": project.id, "name": project.name})
            continue
        exportable.append(project)

    requested_ids = set(project_ids or [])
    visible_ids = {project.id for project in candidates}
    missing_requested_ids = sorted(requested_ids - visible_ids)
    for missing_id in missing_requested_ids:
        warnings.append(f"project {missing_id} is not visible to current user and was skipped")

    return exportable, excluded_seed_projects, warnings


async def _collect_project_domain_rows(
    db: AsyncSession,
    projects: list[Project],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    table_order, specs = _project_domain_specs()
    datasets: dict[str, list[dict[str, Any]]] = {table: [] for table in table_order}

    if not projects:
        return datasets, table_order

    referenced_columns = _referenced_columns(table_order, specs)
    values_by_table_column: dict[str, dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))

    project_rows = _stable_sort_rows([_model_to_dict(project) for project in projects])
    datasets[Project.__table__.name] = project_rows
    for row in project_rows:
        for column_name in referenced_columns[Project.__table__.name]:
            value = row.get(column_name)
            if value is not None:
                values_by_table_column[Project.__table__.name][column_name].add(value)

    for table_name in table_order:
        if table_name == Project.__table__.name:
            continue

        spec = specs[table_name]
        conditions = []
        for foreign_key in spec.foreign_keys:
            parent_values = values_by_table_column[foreign_key.parent_table].get(
                foreign_key.parent_column,
                set(),
            )
            if not parent_values:
                continue
            conditions.append(getattr(spec.model, foreign_key.child_column).in_(list(parent_values)))

        if not conditions:
            datasets[table_name] = []
            continue

        result = await db.execute(select(spec.model).where(or_(*conditions)))
        rows = _stable_sort_rows([_model_to_dict(instance) for instance in result.scalars().all()])
        datasets[table_name] = rows

        for row in rows:
            for column_name in referenced_columns[table_name]:
                value = row.get(column_name)
                if value is not None:
                    values_by_table_column[table_name][column_name].add(value)

    return datasets, table_order


async def export_projects_bundle(
    db: AsyncSession,
    current_user: User,
    project_ids: list[str] | None = None,
    include_archives: bool = True,
) -> ProjectExportBundle:
    projects, excluded_seed_projects, warnings = await _resolve_export_projects(
        db=db,
        current_user=current_user,
        project_ids=project_ids,
    )
    datasets, table_order = await _collect_project_domain_rows(db=db, projects=projects)

    tmp_dir = tempfile.mkdtemp(prefix="deepaudit-project-export-")
    bundle_filename = f"{TRANSFER_BUNDLE_PREFIX}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    bundle_path = os.path.join(tmp_dir, bundle_filename)

    zip_entries: dict[str, dict[str, Any]] = {}
    for project in projects:
        zip_path = await load_project_zip(project.id)
        zip_meta = await get_project_zip_meta(project.id)
        entry = {
            "project_id": project.id,
            "included": False,
            "exists": bool(zip_path and os.path.exists(zip_path)),
            "original_filename": (zip_meta or {}).get("original_filename"),
            "size": (zip_meta or {}).get("file_size"),
            "sha256": None,
        }
        if include_archives and zip_path and os.path.exists(zip_path):
            entry["included"] = True
            entry["size"] = os.path.getsize(zip_path)
            entry["sha256"] = _compute_file_sha256(zip_path)
        elif project.source_type == "zip":
            warnings.append(f"project {project.id} is missing ZIP archive and was exported without source archive")
        zip_entries[project.id] = entry

    manifest = {
        "export_version": TRANSFER_EXPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_app_version": _git_commit(),
        "scope": TRANSFER_SCOPE,
        "conflict_policy": "skip",
        "project_count": len(projects),
        "table_order": table_order,
        "table_counts": {name: len(datasets[name]) for name in table_order},
        "zip_entries": zip_entries,
        "excluded_seed_projects": excluded_seed_projects,
        "warnings": sorted(set(warnings)),
    }

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", _to_json_bytes(manifest))
        for name in table_order:
            bundle.writestr(f"data/{name}.json", _to_json_bytes(datasets[name]))
        if include_archives:
            for project in projects:
                zip_path = await load_project_zip(project.id)
                zip_meta = await get_project_zip_meta(project.id)
                if zip_path and os.path.exists(zip_path):
                    bundle.write(zip_path, arcname=f"project_zips/{project.id}.zip")
                if zip_meta:
                    bundle.writestr(
                        f"project_zips/{project.id}.meta",
                        _to_json_bytes(zip_meta),
                    )

    return ProjectExportBundle(path=bundle_path, filename=bundle_filename, manifest=manifest)


def cleanup_export_bundle(bundle_path: str) -> None:
    try:
        base_dir = os.path.dirname(bundle_path)
        shutil.rmtree(base_dir, ignore_errors=True)
    except Exception:
        logger.warning("failed to cleanup export bundle: %s", bundle_path, exc_info=True)


def _load_bundle_json(bundle: zipfile.ZipFile, path: str) -> Any:
    try:
        with bundle.open(path) as handle:
            return json.load(handle)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"导入包缺少必要文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"导入包 JSON 无法解析: {path}") from exc


def _read_bundle_bytes(bundle: zipfile.ZipFile, path: str) -> bytes | None:
    try:
        with bundle.open(path) as handle:
            return handle.read()
    except KeyError:
        return None


def _bundle_data_tables(bundle: zipfile.ZipFile, manifest: dict[str, Any]) -> list[str]:
    available_tables = sorted(
        {
            entry[len("data/") : -len(".json")]
            for entry in bundle.namelist()
            if entry.startswith("data/") and entry.endswith(".json")
        }
    )

    manifest_order = manifest.get("table_order")
    if isinstance(manifest_order, list):
        normalized_manifest_order = [
            str(table).strip() for table in manifest_order if str(table).strip() in available_tables
        ]
    else:
        normalized_manifest_order = []

    if not normalized_manifest_order:
        return available_tables

    order = list(normalized_manifest_order)
    for table in available_tables:
        if table not in order:
            order.append(table)
    return order


async def _detect_project_conflict(
    db: AsyncSession,
    current_user: User,
    project_row: dict[str, Any],
) -> Project | None:
    zip_file_hash = str(project_row.get("zip_file_hash") or "").strip()
    if zip_file_hash:
        result = await db.execute(select(Project).where(Project.zip_file_hash == zip_file_hash))
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    result = await db.execute(
        select(Project).where(
            Project.owner_id == current_user.id,
            Project.name == project_row.get("name"),
            Project.source_type == project_row.get("source_type"),
            Project.repository_url == project_row.get("repository_url"),
        )
    )
    return result.scalar_one_or_none()


def _source_project_is_seed(project_row: dict[str, Any], zip_meta: dict[str, Any] | None) -> bool:
    owner = User(email=DEFAULT_DEMO_EMAIL, hashed_password="x")
    project = Project(
        id=str(project_row.get("id") or ""),
        name=project_row.get("name"),
        description=project_row.get("description"),
        source_type=project_row.get("source_type"),
        repository_url=project_row.get("repository_url"),
        repository_type=project_row.get("repository_type"),
        default_branch=project_row.get("default_branch"),
        programming_languages=project_row.get("programming_languages"),
        owner_id="seed-owner",
    )
    return _is_seed_project(project, owner, zip_meta)


def _select_rows_for_source_project(
    source_project_id: str,
    datasets: dict[str, list[dict[str, Any]]],
    table_order: list[str],
    specs: dict[str, DomainModelSpec],
) -> dict[str, list[dict[str, Any]]]:
    selected_rows: dict[str, list[dict[str, Any]]] = {table: [] for table in table_order}

    project_rows = datasets.get(Project.__table__.name, [])
    target_project_row = next(
        (
            row
            for row in project_rows
            if isinstance(row, dict) and str(row.get("id") or "") == source_project_id
        ),
        None,
    )
    if not target_project_row:
        return selected_rows

    selected_rows[Project.__table__.name] = [target_project_row]

    referenced_columns = _referenced_columns(table_order, specs)
    source_values: dict[str, dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))
    source_values[Project.__table__.name]["id"].add(source_project_id)

    for table_name in table_order:
        if table_name == Project.__table__.name:
            rows = selected_rows[table_name]
        else:
            rows = []
            for row in datasets.get(table_name, []):
                if not isinstance(row, dict):
                    continue
                for foreign_key in specs[table_name].foreign_keys:
                    parent_values = source_values[foreign_key.parent_table].get(
                        foreign_key.parent_column,
                        set(),
                    )
                    if not parent_values:
                        continue
                    if row.get(foreign_key.child_column) in parent_values:
                        rows.append(row)
                        break
            selected_rows[table_name] = rows

        for row in rows:
            for column_name in referenced_columns[table_name]:
                value = row.get(column_name)
                if value is not None:
                    source_values[table_name][column_name].add(value)

    return selected_rows


def _rebind_user_foreign_keys(
    spec: DomainModelSpec,
    payload: dict[str, Any],
    source_row: dict[str, Any],
    current_user: User,
) -> None:
    model_columns = {column.name: column for column in spec.model.__table__.columns}
    for column_name in spec.user_fk_columns:
        column = model_columns[column_name]
        source_value = source_row.get(column_name)
        if source_value is None and column.nullable:
            payload[column_name] = None
        else:
            payload[column_name] = current_user.id


def _remap_explicit_foreign_keys(
    spec: DomainModelSpec,
    payload: dict[str, Any],
    source_row: dict[str, Any],
    remap_values: dict[str, dict[str, dict[Any, Any]]],
) -> bool:
    for foreign_key in spec.foreign_keys:
        source_value = source_row.get(foreign_key.child_column)
        if source_value is None:
            continue

        parent_map = remap_values.get(foreign_key.parent_table, {}).get(foreign_key.parent_column, {})
        mapped_value = parent_map.get(source_value)
        if mapped_value is None:
            return False
        payload[foreign_key.child_column] = mapped_value

    return True


def _remap_soft_id_columns(
    payload: dict[str, Any],
    explicit_fk_columns: set[str],
    user_fk_columns: set[str],
    remap_values: dict[str, dict[str, dict[Any, Any]]],
) -> None:
    for column_name, value in list(payload.items()):
        if value is None:
            continue
        if not column_name.endswith("_id"):
            continue
        if column_name in explicit_fk_columns or column_name in user_fk_columns:
            continue

        candidates: set[Any] = set()
        for table_map in remap_values.values():
            id_map = table_map.get("id", {})
            if value in id_map:
                candidates.add(id_map[value])

        if len(candidates) == 1:
            payload[column_name] = next(iter(candidates))


def _record_column_remaps(
    table_name: str,
    source_row: dict[str, Any],
    payload: dict[str, Any],
    tracked_columns: set[str],
    remap_values: dict[str, dict[str, dict[Any, Any]]],
) -> None:
    for column_name in tracked_columns:
        source_value = source_row.get(column_name)
        target_value = payload.get(column_name)
        if source_value is None or target_value is None:
            continue
        remap_values.setdefault(table_name, {}).setdefault(column_name, {})[source_value] = target_value


def _is_duplicate_by_unique_columns(
    table_name: str,
    payload: dict[str, Any],
    unique_columns: tuple[tuple[str, ...], ...],
    unique_seen: dict[str, dict[tuple[str, ...], set[tuple[Any, ...]]]],
) -> bool:
    for column_set in unique_columns:
        if any(column not in payload for column in column_set):
            continue
        values = tuple(payload.get(column) for column in column_set)
        if any(value is None for value in values):
            continue
        seen = unique_seen.setdefault(table_name, {}).setdefault(column_set, set())
        if values in seen:
            return True
    return False


async def _find_existing_row_by_unique_columns(
    db: AsyncSession,
    spec: DomainModelSpec,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    for column_set in spec.unique_columns:
        if any(column not in payload for column in column_set):
            continue
        values = tuple(payload.get(column) for column in column_set)
        if any(value is None for value in values):
            continue
        conditions = [getattr(spec.model, column) == payload[column] for column in column_set]
        result = await db.execute(select(spec.model).where(and_(*conditions)).limit(1))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return _model_to_dict(existing)
    return None


def _mark_unique_columns_seen(
    table_name: str,
    payload: dict[str, Any],
    unique_columns: tuple[tuple[str, ...], ...],
    unique_seen: dict[str, dict[tuple[str, ...], set[tuple[Any, ...]]]],
) -> None:
    for column_set in unique_columns:
        if any(column not in payload for column in column_set):
            continue
        values = tuple(payload.get(column) for column in column_set)
        if any(value is None for value in values):
            continue
        unique_seen.setdefault(table_name, {}).setdefault(column_set, set()).add(values)


async def import_projects_bundle(
    db: AsyncSession,
    current_user: User,
    bundle_file: UploadFile,
    conflict_policy: str = "skip",
) -> ProjectImportSummary:
    if conflict_policy != "skip":
        raise HTTPException(status_code=400, detail="当前仅支持 skip 冲突策略")

    current_table_order, current_specs = _project_domain_specs()
    tracked_columns = _referenced_columns(current_table_order, current_specs)

    temp_dir = tempfile.mkdtemp(prefix="deepaudit-project-import-")
    bundle_path = os.path.join(temp_dir, bundle_file.filename or "project-transfer.zip")
    try:
        with open(bundle_path, "wb") as handle:
            shutil.copyfileobj(bundle_file.file, handle)

        imported_projects: list[dict[str, Any]] = []
        skipped_projects: list[dict[str, Any]] = []
        failed_projects: list[dict[str, Any]] = []
        warnings: list[str] = []

        with zipfile.ZipFile(bundle_path, "r") as bundle:
            manifest = _load_bundle_json(bundle, "manifest.json")
            if manifest.get("export_version") != TRANSFER_EXPORT_VERSION:
                raise HTTPException(status_code=400, detail="不支持的导出包版本")
            if manifest.get("scope") != TRANSFER_SCOPE:
                raise HTTPException(status_code=400, detail="导入包 scope 非 project-domain")

            bundle_table_order = _bundle_data_tables(bundle, manifest)
            bundle_tables_set = set(bundle_table_order)
            unknown_tables = [
                table for table in bundle_table_order if table not in current_specs
            ]
            for table in unknown_tables:
                warnings.append(f"table {table} is not recognized by current backend and was skipped")

            import_table_order = [
                table for table in current_table_order if table in bundle_tables_set and table in current_specs
            ]
            if Project.__table__.name not in import_table_order:
                raise HTTPException(status_code=400, detail="导入包缺少 projects 数据")

            datasets: dict[str, list[dict[str, Any]]] = {
                table: _load_bundle_json(bundle, f"data/{table}.json") for table in import_table_order
            }
            for table_name, rows in datasets.items():
                if not isinstance(rows, list):
                    raise HTTPException(status_code=400, detail=f"{table_name}.json 格式错误")

            project_rows = datasets.get(Project.__table__.name, [])
            zip_entries = manifest.get("zip_entries", {}) or {}

            for project_row in project_rows:
                if not isinstance(project_row, dict) or not project_row.get("id"):
                    continue

                source_project_id = project_row["id"]
                project_rows_by_table = _select_rows_for_source_project(
                    source_project_id=source_project_id,
                    datasets=datasets,
                    table_order=import_table_order,
                    specs=current_specs,
                )

                zip_meta_path = f"project_zips/{source_project_id}.meta"
                zip_meta = _load_bundle_json(bundle, zip_meta_path) if zip_meta_path in bundle.namelist() else None
                zip_blob = _read_bundle_bytes(bundle, f"project_zips/{source_project_id}.zip")

                if _source_project_is_seed(project_row, zip_meta):
                    skipped_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "name": project_row.get("name"),
                            "reason": "seed_project",
                        }
                    )
                    warnings.append(f"seed project {project_row.get('name') or source_project_id} was skipped")
                    continue

                existing = await _detect_project_conflict(db=db, current_user=current_user, project_row=project_row)
                merge_into_existing = existing is not None
                target_project_id = existing.id if merge_into_existing else str(uuid.uuid4())
                if merge_into_existing:
                    warnings.append(
                        f"project {source_project_id} conflicted with existing project {target_project_id} and was merged incrementally"
                    )

                zip_manifest_entry = zip_entries.get(source_project_id, {})
                if (
                    not merge_into_existing
                    and project_row.get("source_type") == "zip"
                    and zip_blob is None
                ):
                    failed_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "name": project_row.get("name"),
                            "reason": "missing_zip_archive",
                        }
                    )
                    continue

                new_project_id = target_project_id
                remap_values: dict[str, dict[str, dict[Any, Any]]] = defaultdict(lambda: defaultdict(dict))
                unique_seen: dict[str, dict[tuple[str, ...], set[tuple[Any, ...]]]] = defaultdict(dict)
                if merge_into_existing:
                    remap_values[Project.__table__.name]["id"][source_project_id] = target_project_id

                zip_temp_path: str | None = None
                try:
                    async with db.begin_nested():
                        for table_name in import_table_order:
                            rows = project_rows_by_table.get(table_name, [])
                            if not rows:
                                continue

                            spec = current_specs[table_name]
                            explicit_fk_columns = {fk.child_column for fk in spec.foreign_keys}
                            user_fk_columns = set(spec.user_fk_columns)

                            for source_row in rows:
                                if not isinstance(source_row, dict):
                                    continue
                                if merge_into_existing and table_name == Project.__table__.name:
                                    _record_column_remaps(
                                        table_name=table_name,
                                        source_row=source_row,
                                        payload={"id": target_project_id},
                                        tracked_columns=tracked_columns[table_name],
                                        remap_values=remap_values,
                                    )
                                    continue

                                payload = _coerce_row_for_model(spec.model, source_row)
                                _rebind_user_foreign_keys(
                                    spec=spec,
                                    payload=payload,
                                    source_row=source_row,
                                    current_user=current_user,
                                )

                                if table_name != Project.__table__.name:
                                    if not _remap_explicit_foreign_keys(
                                        spec=spec,
                                        payload=payload,
                                        source_row=source_row,
                                        remap_values=remap_values,
                                    ):
                                        continue

                                if table_name == Project.__table__.name:
                                    payload["id"] = new_project_id
                                    payload["owner_id"] = current_user.id

                                for primary_key in spec.primary_keys:
                                    if table_name == Project.__table__.name and primary_key == "id":
                                        continue
                                    if primary_key in explicit_fk_columns:
                                        continue
                                    if primary_key == "id":
                                        payload[primary_key] = str(uuid.uuid4())
                                    elif primary_key not in payload and primary_key in source_row:
                                        payload[primary_key] = source_row[primary_key]

                                _remap_soft_id_columns(
                                    payload=payload,
                                    explicit_fk_columns=explicit_fk_columns,
                                    user_fk_columns=user_fk_columns,
                                    remap_values=remap_values,
                                )

                                if _is_duplicate_by_unique_columns(
                                    table_name=table_name,
                                    payload=payload,
                                    unique_columns=spec.unique_columns,
                                    unique_seen=unique_seen,
                                ):
                                    existing_payload = await _find_existing_row_by_unique_columns(
                                        db=db,
                                        spec=spec,
                                        payload=payload,
                                    )
                                    if existing_payload is not None:
                                        _record_column_remaps(
                                            table_name=table_name,
                                            source_row=source_row,
                                            payload=existing_payload,
                                            tracked_columns=tracked_columns[table_name],
                                            remap_values=remap_values,
                                        )
                                    continue

                                existing_payload = await _find_existing_row_by_unique_columns(
                                    db=db,
                                    spec=spec,
                                    payload=payload,
                                )
                                if existing_payload is not None:
                                    _mark_unique_columns_seen(
                                        table_name=table_name,
                                        payload=existing_payload,
                                        unique_columns=spec.unique_columns,
                                        unique_seen=unique_seen,
                                    )
                                    _record_column_remaps(
                                        table_name=table_name,
                                        source_row=source_row,
                                        payload=existing_payload,
                                        tracked_columns=tracked_columns[table_name],
                                        remap_values=remap_values,
                                    )
                                    continue

                                db.add(spec.model(**payload))
                                _mark_unique_columns_seen(
                                    table_name=table_name,
                                    payload=payload,
                                    unique_columns=spec.unique_columns,
                                    unique_seen=unique_seen,
                                )
                                _record_column_remaps(
                                    table_name=table_name,
                                    source_row=source_row,
                                    payload=payload,
                                    tracked_columns=tracked_columns[table_name],
                                    remap_values=remap_values,
                                )

                        await db.flush()

                        if zip_blob is not None and not merge_into_existing:
                            fd, zip_temp_path = tempfile.mkstemp(prefix="project-transfer-zip-", suffix=".zip")
                            os.close(fd)
                            with open(zip_temp_path, "wb") as handle:
                                handle.write(zip_blob)
                            actual_sha256 = _compute_file_sha256(zip_temp_path)
                            manifest_sha256 = str(zip_manifest_entry.get("sha256") or "").strip()
                            if manifest_sha256 and actual_sha256 != manifest_sha256:
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"项目 {project_row.get('name') or source_project_id} ZIP 校验失败",
                                )
                            await save_project_zip(
                                project_id=new_project_id,
                                file_path=zip_temp_path,
                                original_filename=(zip_meta or {}).get("original_filename") or f"{new_project_id}.zip",
                            )

                    imported_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "project_id": new_project_id,
                            "name": project_row.get("name"),
                            "reason": "conflict_merged" if merge_into_existing else None,
                        }
                    )
                except Exception as exc:
                    if not merge_into_existing:
                        await delete_project_zip(new_project_id)
                    failed_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "name": project_row.get("name"),
                            "reason": str(exc),
                        }
                    )
                finally:
                    if zip_temp_path and os.path.exists(zip_temp_path):
                        os.remove(zip_temp_path)

            await db.commit()

            for warning in manifest.get("warnings", []) or []:
                if isinstance(warning, str):
                    warnings.append(warning)

        summary = ProjectImportSummary(
            imported_projects=imported_projects,
            skipped_projects=skipped_projects,
            failed_projects=failed_projects,
            warnings=sorted(set(warnings)),
        )
        logger.info(
            "project transfer import summary: imported=%s skipped=%s failed=%s warnings=%s",
            len(summary.imported_projects),
            len(summary.skipped_projects),
            len(summary.failed_projects),
            len(summary.warnings),
        )
        return summary
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
