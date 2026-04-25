import os

import asyncpg
import pytest


def _db_dsn() -> str:
    return (
        os.getenv("PERF_TEST_DSN")
        or os.getenv("POSTGRES_DSN")
        or os.getenv("DATABASE_DSN")
        or "postgresql://postgres:postgres@localhost:5432/Argus"
    )


async def _connect_or_skip() -> asyncpg.Connection:
    dsn = _db_dsn()
    try:
        return await asyncpg.connect(dsn=dsn, timeout=3)
    except Exception as exc:  # pragma: no cover - depends on runtime env
        pytest.skip(f"PostgreSQL not available for query plan tests: {exc}")


async def _explain(conn: asyncpg.Connection, sql: str) -> str:
    rows = await conn.fetch(f"EXPLAIN {sql}")
    return "\n".join(row["QUERY PLAN"] for row in rows)


def _assert_uses_index(plan: str, index_name: str) -> None:
    normalized = plan.lower()
    assert "seq scan" not in normalized, f"sequential scan detected:\n{plan}"
    assert index_name.lower() in normalized, f"expected index {index_name} not used:\n{plan}"


@pytest.mark.asyncio
async def test_query_plans_use_perf_indexes():
    conn = await _connect_or_skip()
    try:
        indexes = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            """
        )
        index_names = {row["indexname"] for row in indexes}
        if "ix_agent_events_task_sequence" not in index_names:
            pytest.skip("performance schema fixtures are not present in this database")

        await conn.execute("SET enable_seqscan = off")
        await conn.execute("SET enable_sort = off")

        plan_events = await _explain(
            conn,
            """
            SELECT id, task_id, sequence
            FROM agent_events
            WHERE task_id = 'task-plan-test' AND sequence > 0
            ORDER BY sequence
            LIMIT 50
            """,
        )
        _assert_uses_index(plan_events, "ix_agent_events_task_sequence")

        plan_findings = await _explain(
            conn,
            """
            SELECT id, task_id, status, severity, created_at
            FROM agent_findings
            WHERE task_id = 'task-plan-test' AND status <> 'false_positive'
            ORDER BY created_at DESC
            LIMIT 50
            """,
        )
        _assert_uses_index(plan_findings, "ix_agent_findings_task_status_created")

        plan_projects_search = await _explain(
            conn,
            """
            SELECT id, name
            FROM projects
            WHERE lower(name) LIKE '%demo%'
            ORDER BY created_at DESC
            LIMIT 20
            """,
        )
        _assert_uses_index(plan_projects_search, "ix_projects_name_trgm")

        plan_opengrep = await _explain(
            conn,
            """
            SELECT id, project_id, status, created_at
            FROM opengrep_scan_tasks
            WHERE project_id = 'project-plan-test' AND lower(status) = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
        )
        _assert_uses_index(
            plan_opengrep,
            "ix_opengrep_tasks_project_lower_status_created_at",
        )
    finally:
        await conn.close()
