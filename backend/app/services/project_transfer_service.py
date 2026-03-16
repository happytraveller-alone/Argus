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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.init_db import DEFAULT_DEMO_EMAIL, _build_default_seed_projects
from app.models.agent_task import AgentEvent, AgentFinding, AgentTask
from app.models.audit import AuditIssue, AuditTask
from app.models.bandit import BanditFinding, BanditScanTask
from app.models.gitleaks import GitleaksFinding, GitleaksScanTask
from app.models.opengrep import OpengrepFinding, OpengrepScanTask
from app.models.phpstan import PhpstanFinding, PhpstanScanTask
from app.models.project import Project, ProjectMember
from app.models.project_info import ProjectInfo
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

DATA_FILE_ORDER = [
    "projects",
    "project_members",
    "project_info",
    "audit_tasks",
    "audit_issues",
    "agent_tasks",
    "agent_events",
    "agent_findings",
    "opengrep_scan_tasks",
    "opengrep_findings",
    "gitleaks_scan_tasks",
    "gitleaks_findings",
    "bandit_scan_tasks",
    "bandit_findings",
    "phpstan_scan_tasks",
    "phpstan_findings",
]


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


async def _resolve_export_projects(
    db: AsyncSession,
    current_user: User,
    project_ids: list[str] | None,
) -> tuple[list[Project], list[dict[str, Any]], list[str]]:
    member_project_ids: list[str] = []
    member_result = await db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)
    )
    member_project_ids = [row[0] for row in member_result.all()]

    query = select(Project).options(selectinload(Project.owner)).where(Project.is_active == True)
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
) -> dict[str, list[dict[str, Any]]]:
    project_ids = [project.id for project in projects]
    datasets: dict[str, list[dict[str, Any]]] = {name: [] for name in DATA_FILE_ORDER}

    if not project_ids:
        return datasets

    project_member_result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id.in_(project_ids))
    )
    project_info_result = await db.execute(
        select(ProjectInfo).where(ProjectInfo.project_id.in_(project_ids))
    )
    audit_task_result = await db.execute(select(AuditTask).where(AuditTask.project_id.in_(project_ids)))
    agent_task_result = await db.execute(select(AgentTask).where(AgentTask.project_id.in_(project_ids)))
    opengrep_task_result = await db.execute(
        select(OpengrepScanTask).where(OpengrepScanTask.project_id.in_(project_ids))
    )
    gitleaks_task_result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.project_id.in_(project_ids))
    )
    bandit_task_result = await db.execute(
        select(BanditScanTask).where(BanditScanTask.project_id.in_(project_ids))
    )
    phpstan_task_result = await db.execute(
        select(PhpstanScanTask).where(PhpstanScanTask.project_id.in_(project_ids))
    )

    audit_tasks = audit_task_result.scalars().all()
    agent_tasks = agent_task_result.scalars().all()
    opengrep_tasks = opengrep_task_result.scalars().all()
    gitleaks_tasks = gitleaks_task_result.scalars().all()
    bandit_tasks = bandit_task_result.scalars().all()
    phpstan_tasks = phpstan_task_result.scalars().all()

    audit_task_ids = [row.id for row in audit_tasks]
    agent_task_ids = [row.id for row in agent_tasks]
    opengrep_task_ids = [row.id for row in opengrep_tasks]
    gitleaks_task_ids = [row.id for row in gitleaks_tasks]
    bandit_task_ids = [row.id for row in bandit_tasks]
    phpstan_task_ids = [row.id for row in phpstan_tasks]

    audit_issue_result = await db.execute(
        select(AuditIssue).where(AuditIssue.task_id.in_(audit_task_ids or ["__none__"]))
    )
    agent_event_result = await db.execute(
        select(AgentEvent).where(AgentEvent.task_id.in_(agent_task_ids or ["__none__"]))
    )
    agent_finding_result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id.in_(agent_task_ids or ["__none__"]))
    )
    opengrep_finding_result = await db.execute(
        select(OpengrepFinding).where(OpengrepFinding.scan_task_id.in_(opengrep_task_ids or ["__none__"]))
    )
    gitleaks_finding_result = await db.execute(
        select(GitleaksFinding).where(GitleaksFinding.scan_task_id.in_(gitleaks_task_ids or ["__none__"]))
    )
    bandit_finding_result = await db.execute(
        select(BanditFinding).where(BanditFinding.scan_task_id.in_(bandit_task_ids or ["__none__"]))
    )
    phpstan_finding_result = await db.execute(
        select(PhpstanFinding).where(PhpstanFinding.scan_task_id.in_(phpstan_task_ids or ["__none__"]))
    )

    datasets["projects"] = _stable_sort_rows([_model_to_dict(project) for project in projects])
    datasets["project_members"] = _stable_sort_rows(
        [_model_to_dict(row) for row in project_member_result.scalars().all()]
    )
    datasets["project_info"] = _stable_sort_rows(
        [_model_to_dict(row) for row in project_info_result.scalars().all()]
    )
    datasets["audit_tasks"] = _stable_sort_rows([_model_to_dict(row) for row in audit_tasks])
    datasets["audit_issues"] = _stable_sort_rows(
        [_model_to_dict(row) for row in audit_issue_result.scalars().all()]
    )
    datasets["agent_tasks"] = _stable_sort_rows([_model_to_dict(row) for row in agent_tasks])
    datasets["agent_events"] = _stable_sort_rows(
        [_model_to_dict(row) for row in agent_event_result.scalars().all()]
    )
    datasets["agent_findings"] = _stable_sort_rows(
        [_model_to_dict(row) for row in agent_finding_result.scalars().all()]
    )
    datasets["opengrep_scan_tasks"] = _stable_sort_rows(
        [_model_to_dict(row) for row in opengrep_tasks]
    )
    datasets["opengrep_findings"] = _stable_sort_rows(
        [_model_to_dict(row) for row in opengrep_finding_result.scalars().all()]
    )
    datasets["gitleaks_scan_tasks"] = _stable_sort_rows(
        [_model_to_dict(row) for row in gitleaks_tasks]
    )
    datasets["gitleaks_findings"] = _stable_sort_rows(
        [_model_to_dict(row) for row in gitleaks_finding_result.scalars().all()]
    )
    datasets["bandit_scan_tasks"] = _stable_sort_rows([_model_to_dict(row) for row in bandit_tasks])
    datasets["bandit_findings"] = _stable_sort_rows(
        [_model_to_dict(row) for row in bandit_finding_result.scalars().all()]
    )
    datasets["phpstan_scan_tasks"] = _stable_sort_rows([_model_to_dict(row) for row in phpstan_tasks])
    datasets["phpstan_findings"] = _stable_sort_rows(
        [_model_to_dict(row) for row in phpstan_finding_result.scalars().all()]
    )
    return datasets


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
    datasets = await _collect_project_domain_rows(db=db, projects=projects)

    tmp_dir = tempfile.mkdtemp(prefix="deepaudit-project-export-")
    bundle_filename = f"{TRANSFER_BUNDLE_PREFIX}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.zip"
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
        "created_at": datetime.now(UTC).isoformat(),
        "source_app_version": _git_commit(),
        "scope": TRANSFER_SCOPE,
        "conflict_policy": "skip",
        "project_count": len(projects),
        "table_counts": {name: len(datasets[name]) for name in DATA_FILE_ORDER},
        "zip_entries": zip_entries,
        "excluded_seed_projects": excluded_seed_projects,
        "warnings": sorted(set(warnings)),
    }

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", _to_json_bytes(manifest))
        for name in DATA_FILE_ORDER:
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


async def import_projects_bundle(
    db: AsyncSession,
    current_user: User,
    bundle_file: UploadFile,
    conflict_policy: str = "skip",
) -> ProjectImportSummary:
    if conflict_policy != "skip":
        raise HTTPException(status_code=400, detail="当前仅支持 skip 冲突策略")

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

            datasets = {name: _load_bundle_json(bundle, f"data/{name}.json") for name in DATA_FILE_ORDER}
            project_rows = datasets["projects"]
            if not isinstance(project_rows, list):
                raise HTTPException(status_code=400, detail="projects.json 格式错误")

            project_rows_by_id = {row["id"]: row for row in project_rows if isinstance(row, dict) and row.get("id")}
            project_member_rows = datasets["project_members"]
            project_info_rows = datasets["project_info"]
            audit_task_rows = datasets["audit_tasks"]
            audit_issue_rows = datasets["audit_issues"]
            agent_task_rows = datasets["agent_tasks"]
            agent_event_rows = datasets["agent_events"]
            agent_finding_rows = datasets["agent_findings"]
            opengrep_task_rows = datasets["opengrep_scan_tasks"]
            opengrep_finding_rows = datasets["opengrep_findings"]
            gitleaks_task_rows = datasets["gitleaks_scan_tasks"]
            gitleaks_finding_rows = datasets["gitleaks_findings"]
            bandit_task_rows = datasets["bandit_scan_tasks"]
            bandit_finding_rows = datasets["bandit_findings"]
            phpstan_task_rows = datasets["phpstan_scan_tasks"]
            phpstan_finding_rows = datasets["phpstan_findings"]

            zip_entries = manifest.get("zip_entries", {}) or {}
            saved_project_ids: list[str] = []

            for project_row in project_rows:
                if not isinstance(project_row, dict) or not project_row.get("id"):
                    continue

                source_project_id = project_row["id"]
                zip_meta = _load_bundle_json(bundle, f"project_zips/{source_project_id}.meta") if f"project_zips/{source_project_id}.meta" in bundle.namelist() else None
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
                if existing:
                    skipped_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "name": project_row.get("name"),
                            "reason": "conflict",
                            "existing_project_id": existing.id,
                        }
                    )
                    continue

                zip_manifest_entry = zip_entries.get(source_project_id, {})
                if project_row.get("source_type") == "zip" and zip_blob is None:
                    failed_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "name": project_row.get("name"),
                            "reason": "missing_zip_archive",
                        }
                    )
                    continue

                new_project_id = str(uuid.uuid4())
                audit_task_id_map: dict[str, str] = {}
                agent_task_id_map: dict[str, str] = {}
                agent_finding_id_map: dict[str, str] = {}
                opengrep_task_id_map: dict[str, str] = {}
                gitleaks_task_id_map: dict[str, str] = {}
                bandit_task_id_map: dict[str, str] = {}
                phpstan_task_id_map: dict[str, str] = {}

                zip_temp_path: str | None = None
                try:
                    async with db.begin_nested():
                        project_data = _coerce_row_for_model(Project, project_row)
                        project_data.update(
                            {
                                "id": new_project_id,
                                "owner_id": current_user.id,
                            }
                        )
                        project = Project(**project_data)
                        db.add(project)

                        membership_payload = {
                            "id": str(uuid.uuid4()),
                            "project_id": new_project_id,
                            "user_id": current_user.id,
                            "role": "owner",
                            "permissions": "{}",
                        }
                        source_member = next(
                            (row for row in project_member_rows if row.get("project_id") == source_project_id),
                            None,
                        )
                        if source_member:
                            membership_payload["role"] = source_member.get("role") or "owner"
                            membership_payload["permissions"] = source_member.get("permissions") or "{}"
                            membership_payload["joined_at"] = _parse_datetime(source_member.get("joined_at"))
                            membership_payload["created_at"] = _parse_datetime(source_member.get("created_at"))
                        db.add(ProjectMember(**membership_payload))

                        for row in project_info_rows:
                            if row.get("project_id") != source_project_id:
                                continue
                            payload = _coerce_row_for_model(ProjectInfo, row)
                            payload.update({"id": str(uuid.uuid4()), "project_id": new_project_id})
                            db.add(ProjectInfo(**payload))

                        for row in audit_task_rows:
                            if row.get("project_id") != source_project_id:
                                continue
                            new_id = str(uuid.uuid4())
                            audit_task_id_map[row["id"]] = new_id
                            payload = _coerce_row_for_model(AuditTask, row)
                            payload.update(
                                {
                                    "id": new_id,
                                    "project_id": new_project_id,
                                    "created_by": current_user.id,
                                }
                            )
                            db.add(AuditTask(**payload))

                        for row in audit_issue_rows:
                            source_task_id = row.get("task_id")
                            if source_task_id not in audit_task_id_map:
                                continue
                            payload = _coerce_row_for_model(AuditIssue, row)
                            payload.update(
                                {
                                    "id": str(uuid.uuid4()),
                                    "task_id": audit_task_id_map[source_task_id],
                                    "resolved_by": current_user.id if row.get("resolved_by") else None,
                                }
                            )
                            db.add(AuditIssue(**payload))

                        for row in agent_task_rows:
                            if row.get("project_id") != source_project_id:
                                continue
                            new_id = str(uuid.uuid4())
                            agent_task_id_map[row["id"]] = new_id
                            payload = _coerce_row_for_model(AgentTask, row)
                            payload.update(
                                {
                                    "id": new_id,
                                    "project_id": new_project_id,
                                    "created_by": current_user.id,
                                }
                            )
                            db.add(AgentTask(**payload))

                        for row in agent_finding_rows:
                            source_task_id = row.get("task_id")
                            if source_task_id not in agent_task_id_map:
                                continue
                            new_id = str(uuid.uuid4())
                            agent_finding_id_map[row["id"]] = new_id
                            payload = _coerce_row_for_model(AgentFinding, row)
                            payload.update({"id": new_id, "task_id": agent_task_id_map[source_task_id]})
                            db.add(AgentFinding(**payload))

                        for row in agent_event_rows:
                            source_task_id = row.get("task_id")
                            if source_task_id not in agent_task_id_map:
                                continue
                            payload = _coerce_row_for_model(AgentEvent, row)
                            payload.update(
                                {
                                    "id": str(uuid.uuid4()),
                                    "task_id": agent_task_id_map[source_task_id],
                                    "finding_id": agent_finding_id_map.get(row.get("finding_id")),
                                }
                            )
                            db.add(AgentEvent(**payload))

                        for model, rows, task_id_map, task_model_name, task_fk, finding_model in [
                            (OpengrepScanTask, opengrep_task_rows, opengrep_task_id_map, "opengrep", "scan_task_id", OpengrepFinding),
                            (GitleaksScanTask, gitleaks_task_rows, gitleaks_task_id_map, "gitleaks", "scan_task_id", GitleaksFinding),
                            (BanditScanTask, bandit_task_rows, bandit_task_id_map, "bandit", "scan_task_id", BanditFinding),
                            (PhpstanScanTask, phpstan_task_rows, phpstan_task_id_map, "phpstan", "scan_task_id", PhpstanFinding),
                        ]:
                            for row in rows:
                                if row.get("project_id") != source_project_id:
                                    continue
                                new_id = str(uuid.uuid4())
                                task_id_map[row["id"]] = new_id
                                payload = _coerce_row_for_model(model, row)
                                payload.update({"id": new_id, "project_id": new_project_id})
                                db.add(model(**payload))

                            finding_rows = {
                                "opengrep": opengrep_finding_rows,
                                "gitleaks": gitleaks_finding_rows,
                                "bandit": bandit_finding_rows,
                                "phpstan": phpstan_finding_rows,
                            }[task_model_name]
                            for row in finding_rows:
                                source_task_id = row.get(task_fk)
                                if source_task_id not in task_id_map:
                                    continue
                                payload = _coerce_row_for_model(finding_model, row)
                                payload.update({"id": str(uuid.uuid4()), task_fk: task_id_map[source_task_id]})
                                db.add(finding_model(**payload))

                        await db.flush()

                        if zip_blob is not None:
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
                            saved_project_ids.append(new_project_id)

                    imported_projects.append(
                        {
                            "source_project_id": source_project_id,
                            "project_id": new_project_id,
                            "name": project_row.get("name"),
                        }
                    )
                except Exception as exc:
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
