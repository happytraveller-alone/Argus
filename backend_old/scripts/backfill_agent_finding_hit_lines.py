#!/usr/bin/env python3
"""
Backfill Agent finding hit lines to function start line when out of function range.

Usage:
  python backend/scripts/backfill_agent_finding_hit_lines.py
  python backend/scripts/backfill_agent_finding_hit_lines.py --apply
  python backend/scripts/backfill_agent_finding_hit_lines.py --task-id <task-id> --apply
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from typing import Any, Dict, Tuple

from sqlalchemy import select

from app.api.v1.endpoints.agent_tasks_findings import (
    _align_hit_line_to_function_start_if_outside,
)
from app.db.session import AsyncSessionLocal
from app.models.agent_task import AgentFinding


def _extract_function_range(verification_result: Any) -> Tuple[Any, Any]:
    if not isinstance(verification_result, dict):
        return None, None
    reachability_target = verification_result.get("reachability_target")
    if not isinstance(reachability_target, dict):
        return None, None
    return reachability_target.get("start_line"), reachability_target.get("end_line")


async def backfill_agent_finding_hit_lines(
    *,
    apply_changes: bool,
    task_id: str | None = None,
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "scanned": 0,
        "correctable": 0,
        "updated": 0,
        "skipped": Counter(),
    }

    async with AsyncSessionLocal() as db:
        query = select(AgentFinding)
        if task_id:
            query = query.where(AgentFinding.task_id == task_id)
        result = await db.execute(query)
        findings = result.scalars().all()

        for finding in findings:
            stats["scanned"] += 1
            function_start, function_end = _extract_function_range(
                getattr(finding, "verification_result", None)
            )
            original_line_start = getattr(finding, "line_start", None)
            original_line_end = getattr(finding, "line_end", None)
            corrected_line_start, corrected_line_end, diagnostics = (
                _align_hit_line_to_function_start_if_outside(
                    line_start=original_line_start,
                    line_end=original_line_end,
                    function_start=function_start,
                    function_end=function_end,
                )
            )

            correction_applied = bool(diagnostics.get("correction_applied"))
            if not correction_applied:
                skipped_reason = diagnostics.get("correction_skipped_reason") or "already_valid"
                stats["skipped"][str(skipped_reason)] += 1
                continue

            if (
                corrected_line_start == original_line_start
                and corrected_line_end == original_line_end
            ):
                stats["skipped"]["already_valid"] += 1
                continue

            stats["correctable"] += 1
            if not apply_changes:
                continue

            finding.line_start = corrected_line_start
            finding.line_end = corrected_line_end

            metadata = (
                dict(finding.finding_metadata)
                if isinstance(getattr(finding, "finding_metadata", None), dict)
                else {}
            )
            if "raw_line_start" not in metadata and original_line_start is not None:
                metadata["raw_line_start"] = original_line_start
            if "raw_line_end" not in metadata and original_line_end is not None:
                metadata["raw_line_end"] = original_line_end
            finding.finding_metadata = metadata
            stats["updated"] += 1

        if apply_changes and stats["updated"] > 0:
            await db.commit()
        else:
            await db.rollback()

    stats["skipped"] = dict(stats["skipped"])
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Agent finding hit lines when they are missing or outside function range"
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply changes to database (default is dry-run)",
    )
    parser.add_argument(
        "--task-id",
        type=str,
        default="",
        help="optional task id filter",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    stats = await backfill_agent_finding_hit_lines(
        apply_changes=bool(args.apply),
        task_id=str(args.task_id or "").strip() or None,
    )
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] scanned={stats['scanned']} "
        f"correctable={stats['correctable']} "
        f"updated={stats['updated']}"
    )
    skipped = stats.get("skipped") or {}
    if skipped:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(skipped.items()))
        print(f"[{mode}] skipped: {parts}")


if __name__ == "__main__":
    asyncio.run(_main())
