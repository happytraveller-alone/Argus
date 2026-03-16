import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models.bandit  # noqa: F401
import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401
import app.models.phpstan  # noqa: F401
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import Base
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
from app.services.project_transfer_service import (
    TRANSFER_EXPORT_VERSION,
    cleanup_export_bundle,
    export_projects_bundle,
    import_projects_bundle,
)
from app.services.zip_storage import load_project_zip, save_project_zip
from conftest import _is_sqlite_incompatible_index


async def _make_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    removed_indexes = []
    for table in Base.metadata.tables.values():
        incompatible_indexes = [
            index for index in list(table.indexes) if _is_sqlite_incompatible_index(index)
        ]
        for index in incompatible_indexes:
            table.indexes.remove(index)
            removed_indexes.append((table, index))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    session = factory()
    session._test_engine = engine  # type: ignore[attr-defined]
    session._removed_indexes = removed_indexes  # type: ignore[attr-defined]
    return session


async def _close_session(session: AsyncSession) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    removed_indexes = session._removed_indexes  # type: ignore[attr-defined]
    await session.close()
    await engine.dispose()
    for table, index in removed_indexes:
        table.indexes.add(index)


def _make_project_zip(tmp_path: Path, filename: str, content: str = "print('hello')\n") -> str:
    zip_path = tmp_path / filename
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("src/main.py", content)
    return str(zip_path)


async def _create_user(db: AsyncSession, email: str, full_name: str) -> User:
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash("password123"),
        is_active=True,
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_export_projects_bundle_excludes_seed_projects_and_warns_missing_zip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "ZIP_STORAGE_PATH", str(tmp_path / "zip-storage"))
    db = await _make_session()
    try:
        demo_user = await _create_user(db, DEFAULT_DEMO_EMAIL, "Demo User")
        seed = _build_default_seed_projects()[0]

        seed_project = Project(
            name=seed.name,
            description="seed",
            source_type="zip",
            owner_id=demo_user.id,
            repository_type="other",
            default_branch="main",
            programming_languages="[]",
        )
        normal_project = Project(
            name="Customer Project",
            description="normal",
            source_type="zip",
            owner_id=demo_user.id,
            repository_type="other",
            default_branch="main",
            programming_languages='["Python"]',
        )
        missing_zip_project = Project(
            name="Missing Zip Project",
            description="missing",
            source_type="zip",
            owner_id=demo_user.id,
            repository_type="other",
            default_branch="main",
            programming_languages="[]",
        )
        db.add_all([seed_project, normal_project, missing_zip_project])
        await db.commit()
        await db.refresh(seed_project)
        await db.refresh(normal_project)
        await db.refresh(missing_zip_project)

        await save_project_zip(seed_project.id, _make_project_zip(tmp_path, seed.archive_name), seed.archive_name)

        normal_zip = _make_project_zip(tmp_path, "customer-project.zip")
        await save_project_zip(normal_project.id, normal_zip, "customer-project.zip")

        bundle = await export_projects_bundle(db=db, current_user=demo_user)
        try:
            with zipfile.ZipFile(bundle.path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json"))
                exported_projects = json.loads(archive.read("data/projects.json"))

            exported_names = [row["name"] for row in exported_projects]
            assert seed.name not in exported_names
            assert "Customer Project" in exported_names
            assert "Missing Zip Project" in exported_names
            assert manifest["excluded_seed_projects"] == [{"id": seed_project.id, "name": seed.name}]
            assert any("missing ZIP archive" in warning for warning in manifest["warnings"])
        finally:
            cleanup_export_bundle(bundle.path)
    finally:
        await _close_session(db)


async def _build_full_source_bundle(tmp_path: Path) -> tuple[bytes, str, str]:
    source_db = await _make_session()
    try:
        source_user = await _create_user(source_db, "source@example.com", "Source User")
        project = Project(
            name="Imported Project",
            description="bundle source",
            source_type="zip",
            owner_id=source_user.id,
            repository_type="other",
            default_branch="main",
            programming_languages='["Python"]',
            zip_file_hash="hash-import-project",
        )
        source_db.add(project)
        await source_db.commit()
        await source_db.refresh(project)

        source_db.add(
            ProjectMember(
                project_id=project.id,
                user_id=source_user.id,
                role="owner",
                permissions='{"manage": true}',
            )
        )
        source_db.add(
            ProjectInfo(
                project_id=project.id,
                language_info={"Python": 10},
                description="generated summary",
                status="completed",
            )
        )
        await source_db.commit()

        audit_task = AuditTask(
            project_id=project.id,
            created_by=source_user.id,
            task_type="full_scan",
            status="completed",
            branch_name="main",
        )
        source_db.add(audit_task)
        await source_db.commit()
        await source_db.refresh(audit_task)

        source_db.add(
            AuditIssue(
                task_id=audit_task.id,
                file_path="src/main.py",
                issue_type="command_injection",
                severity="high",
                title="Dangerous call",
                resolved_by=source_user.id,
            )
        )

        agent_task = AgentTask(
            project_id=project.id,
            created_by=source_user.id,
            name="Agent Audit",
            task_type="agent_audit",
            status="completed",
        )
        source_db.add(agent_task)
        await source_db.commit()
        await source_db.refresh(agent_task)

        agent_finding = AgentFinding(
            task_id=agent_task.id,
            vulnerability_type="command_injection",
            severity="high",
            title="system(cmd)",
            file_path="src/main.py",
            is_verified=True,
        )
        source_db.add(agent_finding)
        await source_db.commit()
        await source_db.refresh(agent_finding)

        source_db.add(
            AgentEvent(
                task_id=agent_task.id,
                event_type="finding_new",
                message="new finding",
                finding_id=agent_finding.id,
                sequence=1,
            )
        )

        opengrep_task = OpengrepScanTask(
            project_id=project.id,
            name="opengrep",
            status="completed",
            target_path=".",
        )
        gitleaks_task = GitleaksScanTask(
            project_id=project.id,
            name="gitleaks",
            status="completed",
            target_path=".",
        )
        bandit_task = BanditScanTask(
            project_id=project.id,
            name="bandit",
            status="completed",
            target_path=".",
        )
        phpstan_task = PhpstanScanTask(
            project_id=project.id,
            name="phpstan",
            status="completed",
            target_path=".",
        )
        source_db.add_all([opengrep_task, gitleaks_task, bandit_task, phpstan_task])
        await source_db.commit()
        await source_db.refresh(opengrep_task)
        await source_db.refresh(gitleaks_task)
        await source_db.refresh(bandit_task)
        await source_db.refresh(phpstan_task)

        source_db.add_all(
            [
                OpengrepFinding(
                    scan_task_id=opengrep_task.id,
                    file_path="src/main.py",
                    severity="ERROR",
                    status="open",
                    rule={"id": "rule-1"},
                ),
                GitleaksFinding(
                    scan_task_id=gitleaks_task.id,
                    rule_id="aws-access-key",
                    file_path="src/main.py",
                    status="open",
                ),
                BanditFinding(
                    scan_task_id=bandit_task.id,
                    test_id="B602",
                    test_name="subprocess_popen_with_shell_equals_true",
                    issue_severity="HIGH",
                    issue_confidence="HIGH",
                    file_path="src/main.py",
                    status="open",
                ),
                PhpstanFinding(
                    scan_task_id=phpstan_task.id,
                    file_path="src/main.php",
                    message="Undefined variable",
                    status="open",
                ),
            ]
        )
        await source_db.commit()

        zip_path = _make_project_zip(tmp_path, "imported-project.zip")
        await save_project_zip(project.id, zip_path, "imported-project.zip")

        bundle = await export_projects_bundle(
            db=source_db,
            current_user=source_user,
            project_ids=[project.id],
        )
        bundle_bytes = Path(bundle.path).read_bytes()
        cleanup_export_bundle(bundle.path)
        return bundle_bytes, project.id, source_user.id
    finally:
        await _close_session(source_db)


@pytest.mark.asyncio
async def test_import_projects_bundle_restores_graph_and_rebinds_user(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "ZIP_STORAGE_PATH", str(tmp_path / "zip-storage"))
    bundle_bytes, source_project_id, source_user_id = await _build_full_source_bundle(tmp_path)

    target_db = await _make_session()
    try:
        target_user = await _create_user(target_db, "target@example.com", "Target User")
        upload = UploadFile(filename="bundle.zip", file=io.BytesIO(bundle_bytes))
        summary = await import_projects_bundle(target_db, target_user, upload)

        assert [item["source_project_id"] for item in summary.imported_projects] == [source_project_id]
        assert summary.failed_projects == []
        imported_project_id = summary.imported_projects[0]["project_id"]
        assert imported_project_id != source_project_id

        project = await target_db.get(Project, imported_project_id)
        assert project is not None
        assert project.owner_id == target_user.id
        assert project.zip_file_hash == "hash-import-project"

        project_zip_path = await load_project_zip(imported_project_id)
        assert project_zip_path is not None
        assert os.path.exists(project_zip_path)

        member = (
            await target_db.execute(select(ProjectMember).where(ProjectMember.project_id == imported_project_id))
        ).scalar_one()
        assert member.user_id == target_user.id

        audit_task = (
            await target_db.execute(select(AuditTask).where(AuditTask.project_id == imported_project_id))
        ).scalar_one()
        assert audit_task.created_by == target_user.id

        audit_issue = (
            await target_db.execute(select(AuditIssue).where(AuditIssue.task_id == audit_task.id))
        ).scalar_one()
        assert audit_issue.resolved_by == target_user.id

        agent_task = (
            await target_db.execute(select(AgentTask).where(AgentTask.project_id == imported_project_id))
        ).scalar_one()
        assert agent_task.created_by == target_user.id

        agent_finding = (
            await target_db.execute(select(AgentFinding).where(AgentFinding.task_id == agent_task.id))
        ).scalar_one()
        agent_event = (
            await target_db.execute(select(AgentEvent).where(AgentEvent.task_id == agent_task.id))
        ).scalar_one()
        assert agent_event.finding_id == agent_finding.id

        gitleaks_task = (
            await target_db.execute(select(GitleaksScanTask).where(GitleaksScanTask.project_id == imported_project_id))
        ).scalar_one()
        gitleaks_finding = (
            await target_db.execute(
                select(GitleaksFinding).where(GitleaksFinding.scan_task_id == gitleaks_task.id)
            )
        ).scalar_one()
        assert gitleaks_finding.scan_task_id == gitleaks_task.id

        assert source_user_id != target_user.id
    finally:
        await _close_session(target_db)


@pytest.mark.asyncio
async def test_import_projects_bundle_skips_conflicting_zip_hash(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "ZIP_STORAGE_PATH", str(tmp_path / "zip-storage"))
    bundle_bytes, _, _ = await _build_full_source_bundle(tmp_path)

    db = await _make_session()
    try:
        user = await _create_user(db, "target@example.com", "Target User")
        existing_project = Project(
            name="Existing",
            description="conflict",
            source_type="zip",
            owner_id=user.id,
            repository_type="other",
            default_branch="main",
            programming_languages="[]",
            zip_file_hash="hash-import-project",
        )
        db.add(existing_project)
        await db.commit()

        summary = await import_projects_bundle(
            db,
            user,
            UploadFile(filename="bundle.zip", file=io.BytesIO(bundle_bytes)),
        )
        assert summary.imported_projects == []
        assert summary.failed_projects == []
        assert summary.skipped_projects[0]["reason"] == "conflict"

        projects = (await db.execute(select(Project))).scalars().all()
        assert len(projects) == 1
    finally:
        await _close_session(db)


@pytest.mark.asyncio
async def test_import_projects_bundle_skips_seed_and_rejects_unsupported_version(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "ZIP_STORAGE_PATH", str(tmp_path / "zip-storage"))
    db = await _make_session()
    try:
        user = await _create_user(db, "target@example.com", "Target User")
        seed = _build_default_seed_projects()[0]

        seed_bundle_path = tmp_path / "seed-bundle.zip"
        with zipfile.ZipFile(seed_bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            manifest = {
                "export_version": TRANSFER_EXPORT_VERSION,
                "scope": "project-domain",
                "zip_entries": {"seed-project": {"sha256": "", "included": True}},
                "warnings": [],
            }
            bundle.writestr("manifest.json", json.dumps(manifest))
            bundle.writestr(
                "data/projects.json",
                json.dumps(
                    [
                        {
                            "id": "seed-project",
                            "name": seed.name,
                            "description": "seed",
                            "source_type": "zip",
                            "repository_url": None,
                            "repository_type": "other",
                            "default_branch": "main",
                            "programming_languages": "[]",
                            "owner_id": "source-user",
                            "is_active": True,
                            "zip_file_hash": "seed-hash",
                        }
                    ]
                ),
            )
            for name in [
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
            ]:
                bundle.writestr(f"data/{name}.json", "[]")
            bundle.writestr("project_zips/seed-project.meta", json.dumps({"original_filename": seed.archive_name}))
            bundle.writestr("project_zips/seed-project.zip", b"zip-bytes")

        summary = await import_projects_bundle(
            db,
            user,
            UploadFile(filename="seed-bundle.zip", file=io.BytesIO(seed_bundle_path.read_bytes())),
        )
        assert summary.imported_projects == []
        assert summary.skipped_projects[0]["reason"] == "seed_project"

        bad_bundle_path = tmp_path / "bad-bundle.zip"
        with zipfile.ZipFile(bad_bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps({"export_version": "legacy", "scope": "project-domain"}))
            for name in [
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
            ]:
                bundle.writestr(f"data/{name}.json", "[]")

        with pytest.raises(Exception) as exc_info:
            await import_projects_bundle(
                db,
                user,
                UploadFile(filename="bad-bundle.zip", file=io.BytesIO(bad_bundle_path.read_bytes())),
            )
        assert "不支持的导出包版本" in str(exc_info.value)
    finally:
        await _close_session(db)
