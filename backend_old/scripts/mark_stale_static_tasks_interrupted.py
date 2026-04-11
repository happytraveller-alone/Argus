#!/usr/bin/env python3
"""
One-off cleanup for stale static scan tasks.

Usage:
  python backend/scripts/mark_stale_static_tasks_interrupted.py --minutes 30
  python backend/scripts/mark_stale_static_tasks_interrupted.py --minutes 30 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select

from app.db.session import AsyncSessionLocal
from app.models.bandit import BanditScanTask
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from app.models.phpstan import PhpstanScanTask
from app.models.yasa import YasaScanTask


INTERRUPTED_ERROR_MESSAGE = "任务长时间未更新，已自动标记为中止"
RECOVERABLE_STATUSES = {"pending", "running"}


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _mark_interrupted(task: Any) -> bool:
    changed = False
    if _normalize_status(getattr(task, "status", "")) != "interrupted":
        task.status = "interrupted"
        changed = True

    if hasattr(task, "completed_at") and getattr(task, "completed_at", None) is None:
        task.completed_at = datetime.now(timezone.utc)
        changed = True

    if hasattr(task, "error_message") and not getattr(task, "error_message", None):
        task.error_message = INTERRUPTED_ERROR_MESSAGE
        changed = True

    return changed


async def cleanup_stale_tasks(minutes: int, dry_run: bool) -> dict[str, int]:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    # Best effort cleanup: we only touch tasks older than threshold.
    # Active in-memory subprocess tracking is process-local and not available here.
    specs = [
        ("opengrep", OpengrepScanTask),
        ("gitleaks", GitleaksScanTask),
        ("bandit", BanditScanTask),
        ("phpstan", PhpstanScanTask),
        ("yasa", YasaScanTask),
    ]
    counts = {name: 0 for name, _ in specs}

    async with AsyncSessionLocal() as db:
        for engine_name, model in specs:
            query = select(model).where(
                model.status.in_(sorted(RECOVERABLE_STATUSES)),
                or_(
                    model.updated_at < threshold,
                    model.updated_at.is_(None) & (model.created_at < threshold),
                ),
            )
            result = await db.execute(query)
            for task in result.scalars().all():
                if _mark_interrupted(task):
                    counts[engine_name] += 1

        if dry_run:
            await db.rollback()
        else:
            if any(counts.values()):
                await db.commit()
            else:
                await db.rollback()

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark stale static scan tasks as interrupted",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="stale threshold in minutes (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show affected counts without committing changes",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    if args.minutes <= 0:
        raise ValueError("--minutes must be > 0")

    counts = await cleanup_stale_tasks(minutes=args.minutes, dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print(
        f"[{mode}] stale>{args.minutes}m interrupted counts: "
        f"opengrep={counts['opengrep']}, "
        f"gitleaks={counts['gitleaks']}, "
        f"bandit={counts['bandit']}, "
        f"phpstan={counts['phpstan']}, "
        f"yasa={counts['yasa']}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
