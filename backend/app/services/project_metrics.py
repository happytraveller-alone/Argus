import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models import (
    AgentTask,
    AuditTask,
    BanditScanTask,
    GitleaksScanTask,
    OpengrepScanTask,
    PhpstanScanTask,
    Project,
    ProjectManagementMetrics,
)
from app.services.zip_storage import get_project_zip_meta

logger = logging.getLogger(__name__)


class ProjectMetricsService:
    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    COMPLETED_STATUSES = {"completed"}
    RUNNING_STATUSES = {"pending", "running"}

    @classmethod
    async def recalc_project(
        cls,
        db: AsyncSession,
        project_id: str,
    ) -> ProjectManagementMetrics:
        project = await db.get(Project, project_id)
        if not project:
            raise ValueError(f"项目不存在：{project_id}")

        metrics = await db.get(ProjectManagementMetrics, project_id)
        if not metrics:
            metrics = ProjectManagementMetrics(project_id=project_id)
        metrics.status = cls.STATUS_PENDING
        metrics.error_message = None
        metrics.updated_at = datetime.now(timezone.utc)
        db.add(metrics)
        await db.flush()

        try:
            payload = await cls._build_payload(db, project_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to build project metrics: %s", project_id)
            metrics.status = cls.STATUS_FAILED
            metrics.error_message = str(exc)
            metrics.updated_at = datetime.now(timezone.utc)
            db.add(metrics)
            await db.commit()
            await db.refresh(metrics)
            raise

        for field, value in payload.items():
            setattr(metrics, field, value)
        metrics.status = cls.STATUS_READY
        metrics.error_message = None
        metrics.updated_at = datetime.now(timezone.utc)
        db.add(metrics)
        await db.commit()
        await db.refresh(metrics)
        return metrics

    @classmethod
    async def _build_payload(
        cls,
        db: AsyncSession,
        project_id: str,
    ) -> Dict[str, Optional[int]]:
        payload: Dict[str, Optional[object]] = {
            "archive_size_bytes": 0,
            "archive_original_filename": None,
            "archive_uploaded_at": None,
            "total_tasks": 0,
            "completed_tasks": 0,
            "running_tasks": 0,
            "audit_tasks": 0,
            "agent_tasks": 0,
            "opengrep_tasks": 0,
            "gitleaks_tasks": 0,
            "bandit_tasks": 0,
            "phpstan_tasks": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "last_completed_task_at": None,
        }

        await cls._apply_archive_meta(payload, project_id)
        await cls._apply_audit_tasks(db, payload, project_id)
        await cls._apply_agent_tasks(db, payload, project_id)
        await cls._apply_opengrep_tasks(db, payload, project_id)
        await cls._apply_gitleaks_tasks(db, payload, project_id)
        await cls._apply_bandit_tasks(db, payload, project_id)
        await cls._apply_phpstan_tasks(db, payload, project_id)

        return payload

    @staticmethod
    async def _apply_archive_meta(payload: Dict[str, Optional[object]], project_id: str) -> None:
        meta = await get_project_zip_meta(project_id)
        if not meta:
            return
        payload["archive_size_bytes"] = int(meta.get("file_size") or 0)
        payload["archive_original_filename"] = meta.get("original_filename")
        uploaded_at = meta.get("uploaded_at")
        if isinstance(uploaded_at, str):
            try:
                payload["archive_uploaded_at"] = datetime.fromisoformat(uploaded_at)
            except ValueError:
                payload["archive_uploaded_at"] = None
        else:
            payload["archive_uploaded_at"] = uploaded_at

    @classmethod
    async def _apply_audit_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(AuditTask.status, AuditTask.completed_at).where(
            AuditTask.project_id == project_id
        )
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="audit_tasks")

    @classmethod
    async def _apply_agent_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(
            AgentTask.status,
            AgentTask.completed_at,
            AgentTask.critical_count,
            AgentTask.high_count,
            AgentTask.medium_count,
            AgentTask.low_count,
        ).where(AgentTask.project_id == project_id)
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="agent_tasks")

        critical = sum(int(row.critical_count or 0) for row in rows)
        high = sum(int(row.high_count or 0) for row in rows)
        medium = sum(int(row.medium_count or 0) for row in rows)
        low = sum(int(row.low_count or 0) for row in rows)
        payload["critical"] = (payload.get("critical") or 0) + critical
        payload["high"] = (payload.get("high") or 0) + high
        payload["medium"] = (payload.get("medium") or 0) + medium
        payload["low"] = (payload.get("low") or 0) + low

    @classmethod
    async def _apply_opengrep_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(
            OpengrepScanTask.status,
            OpengrepScanTask.completed_at,
            OpengrepScanTask.total_findings,
            OpengrepScanTask.error_count,
            OpengrepScanTask.warning_count,
        ).where(OpengrepScanTask.project_id == project_id)
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="opengrep_tasks")
        for row in rows:
            total = max(int(row.total_findings or 0), 0)
            medium = max(int(row.error_count or 0), 0) + max(
                int(row.warning_count or 0), 0
            )
            low = max(total - medium, 0)
            payload["medium"] = (payload.get("medium") or 0) + medium
            payload["low"] = (payload.get("low") or 0) + low

    @classmethod
    async def _apply_gitleaks_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(
            GitleaksScanTask.status,
            GitleaksScanTask.completed_at,
            GitleaksScanTask.total_findings,
        ).where(GitleaksScanTask.project_id == project_id)
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="gitleaks_tasks")
        payload["low"] = (payload.get("low") or 0) + sum(
            max(int(row.total_findings or 0), 0) for row in rows
        )

    @classmethod
    async def _apply_bandit_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(
            BanditScanTask.status,
            BanditScanTask.completed_at,
            BanditScanTask.high_count,
            BanditScanTask.medium_count,
            BanditScanTask.low_count,
        ).where(BanditScanTask.project_id == project_id)
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="bandit_tasks")
        payload["high"] = (payload.get("high") or 0) + sum(
            max(int(row.high_count or 0), 0) for row in rows
        )
        payload["medium"] = (payload.get("medium") or 0) + sum(
            max(int(row.medium_count or 0), 0) for row in rows
        )
        payload["low"] = (payload.get("low") or 0) + sum(
            max(int(row.low_count or 0), 0) for row in rows
        )

    @classmethod
    async def _apply_phpstan_tasks(
        cls,
        db: AsyncSession,
        payload: Dict[str, Optional[object]],
        project_id: str,
    ) -> None:
        stmt = select(
            PhpstanScanTask.status,
            PhpstanScanTask.completed_at,
            PhpstanScanTask.total_findings,
        ).where(PhpstanScanTask.project_id == project_id)
        rows = (await db.execute(stmt)).all()
        cls._apply_task_rollup(payload, rows, bucket_key="phpstan_tasks")
        payload["low"] = (payload.get("low") or 0) + sum(
            max(int(row.total_findings or 0), 0) for row in rows
        )

    @classmethod
    def _apply_task_rollup(
        cls,
        payload: Dict[str, Optional[object]],
        rows: Sequence,
        *,
        bucket_key: str,
    ) -> None:
        total = len(rows)
        completed = 0
        running = 0
        last_completed: Optional[datetime] = payload.get("last_completed_task_at")
        for row in rows:
            status = cls._normalize_status(row.status)
            if status in cls.COMPLETED_STATUSES:
                completed += 1
                completed_at = getattr(row, "completed_at", None)
                if completed_at:
                    if last_completed is None or completed_at > last_completed:
                        last_completed = completed_at
            if status in cls.RUNNING_STATUSES:
                running += 1
        payload[bucket_key] = total
        payload["total_tasks"] = (payload.get("total_tasks") or 0) + total
        payload["completed_tasks"] = (payload.get("completed_tasks") or 0) + completed
        payload["running_tasks"] = (payload.get("running_tasks") or 0) + running
        if last_completed:
            payload["last_completed_task_at"] = last_completed

    @staticmethod
    def _normalize_status(value: Optional[str]) -> str:
        return str(value or "").strip().lower()


class ProjectMetricsRefresher:
    def __init__(self) -> None:
        self._pending: set[str] = set()

    def enqueue(self, project_id: Optional[str]) -> None:
        if not project_id:
            return
        if project_id in self._pending:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pending.add(project_id)
            try:
                asyncio.run(self._refresh(project_id))
            finally:
                self._pending.discard(project_id)
            return
        self._pending.add(project_id)
        loop.create_task(self._run_refresh(project_id))

    async def _run_refresh(self, project_id: str) -> None:
        try:
            await self._refresh(project_id)
        finally:
            self._pending.discard(project_id)

    async def _refresh(self, project_id: str):
        try:
            async with async_session_factory() as db:
                await ProjectMetricsService.recalc_project(db, project_id)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Project metrics refresh failed for %s", project_id)

    async def recalc_now(self, project_id: str) -> ProjectManagementMetrics:
        async with async_session_factory() as db:
            return await ProjectMetricsService.recalc_project(db, project_id)


project_metrics_refresher = ProjectMetricsRefresher()
