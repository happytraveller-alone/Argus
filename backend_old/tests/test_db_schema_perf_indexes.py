import os

import asyncpg
import pytest


def _db_dsn() -> str:
    return (
        os.getenv("PERF_TEST_DSN")
        or os.getenv("POSTGRES_DSN")
        or os.getenv("DATABASE_DSN")
        or "postgresql://postgres:postgres@localhost:5432/vulhunter"
    )


async def _connect_or_skip() -> asyncpg.Connection:
    dsn = _db_dsn()
    try:
        return await asyncpg.connect(dsn=dsn, timeout=3)
    except Exception as exc:  # pragma: no cover - depends on runtime env
        pytest.skip(f"PostgreSQL not available for perf schema tests: {exc}")


@pytest.mark.asyncio
async def test_perf_indexes_and_constraints_exist():
    conn = await _connect_or_skip()
    try:
        existing_index_rows = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            """
        )
        existing = {row["indexname"] for row in existing_index_rows}
        if "ix_agent_events_task_sequence" not in existing:
            pytest.skip("performance schema fixtures are not present in this database")

        ext = await conn.fetchval(
            "SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'"
        )
        assert ext == "pg_trgm"

        expected_indexes = {
            "ix_users_role_active_created_at",
            "ix_projects_owner_active_created_at",
            "ix_projects_name_trgm",
            "ix_project_members_project_joined_at",
            "ix_instant_analyses_user_created_at",
            "ix_project_info_project_created_at",
            "ix_audit_rule_sets_active_language_type",
            "ix_audit_rules_rule_set_enabled_sort",
            "ix_prompt_templates_name_trgm",
            "ix_opengrep_rules_active_filters",
            "ix_opengrep_tasks_project_lower_status_created_at",
            "ix_opengrep_findings_scan_task_sev_status_line",
            "ix_gitleaks_tasks_project_lower_status_created_at",
            "ix_gitleaks_findings_scan_task_status_created",
            "ix_agent_tasks_project_status_created",
            "ix_agent_events_task_sequence",
            "ix_agent_findings_task_status_created",
            "ix_agent_checkpoints_task_agent_created",
            "ix_agent_tree_nodes_task_depth_created",
        }

        missing = expected_indexes - existing
        assert not missing, f"missing indexes: {sorted(missing)}"

        expected_constraints = {
            "uq_project_members_project_user",
            "uq_project_info_project_id",
            "uq_audit_rules_rule_set_code",
            "uq_opengrep_rules_name",
        }
        constraint_rows = await conn.fetch(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND constraint_type IN ('UNIQUE', 'PRIMARY KEY')
            """
        )
        existing_constraints = {row["constraint_name"] for row in constraint_rows}
        missing_constraints = expected_constraints - existing_constraints
        assert not missing_constraints, f"missing constraints: {sorted(missing_constraints)}"
    finally:
        await conn.close()
