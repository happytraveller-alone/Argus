import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"
SNAPSHOTS_DIR = BACKEND_ROOT / "app" / "db" / "schema_snapshots"


def _literal_eval_revision_value(source: str, variable_name: str):
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == variable_name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == variable_name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"Could not find {variable_name} in migration source")


def _load_revision_graph():
    revisions: dict[str, str] = {}
    down_revisions: dict[str, tuple[str, ...]] = {}
    file_names: dict[str, str] = {}

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        revision = _literal_eval_revision_value(source, "revision")
        raw_down_revision = _literal_eval_revision_value(source, "down_revision")
        if raw_down_revision is None:
            normalized_down_revision = ()
        elif isinstance(raw_down_revision, str):
            normalized_down_revision = (raw_down_revision,)
        else:
            normalized_down_revision = tuple(raw_down_revision)

        revisions[path.name] = revision
        down_revisions[revision] = normalized_down_revision
        file_names[revision] = path.name

    return revisions, down_revisions, file_names


def _created_tables_in_source(source: str) -> list[str]:
    module = ast.parse(source)
    created_tables: list[str] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "create_table":
            continue
        if not node.args:
            continue
        table_name_arg = node.args[0]
        if isinstance(table_name_arg, ast.Constant) and isinstance(
            table_name_arg.value, str
        ):
            created_tables.append(table_name_arg.value)

    return created_tables


def test_alembic_revisions_form_a_single_head_graph():
    revisions, down_revisions, _ = _load_revision_graph()
    all_revisions = set(down_revisions)
    referenced_revisions = {
        down_revision
        for item in down_revisions.values()
        for down_revision in item
    }
    heads = sorted(all_revisions - referenced_revisions)

    assert len(heads) == 1, f"Expected a single Alembic head, got {heads}"
    assert heads == ["c9d0e1f2a3b4"], heads
    assert len(revisions) == len(down_revisions)


def test_project_management_metrics_table_is_created_by_a_single_migration():
    matching_files = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "project_management_metrics" in _created_tables_in_source(source):
            matching_files.append(path.name)

    assert matching_files == ["e5f6a7b8c9d0_add_project_management_metrics.py"]


def test_alembic_versions_directory_keeps_expected_linearized_revisions():
    _, down_revisions, file_names = _load_revision_graph()
    base_revisions = sorted(
        revision for revision, parents in down_revisions.items() if len(parents) == 0
    )

    assert base_revisions == ["5b0f3c9a6d7e"]
    assert file_names["6c8d9e0f1a2b"] == "6c8d9e0f1a2b_finalize_projects_zip_file_hash.py"
    assert file_names["1f2e3d4c5b6a"] == "1f2e3d4c5b6a_add_verified_project_management_metrics.py"
    assert file_names["a8f1c2d3e4b5"] == "a8f1c2d3e4b5_add_agent_tasks_report_column.py"
    assert file_names["b9d8e7f6a5b4"] == "b9d8e7f6a5b4_drop_legacy_audit_tables.py"
    assert file_names["c9d0e1f2a3b4"] == "c9d0e1f2a3b4_add_yasa_rule_configs_and_task_binding.py"
    assert "048836873140" not in file_names
    assert "c4b1a7e8d9f0" not in file_names
    assert "d4e5f6a7b8c9" not in file_names
    assert "5f6a7b8c9d0e" not in file_names
    assert "90a71996ac03" not in file_names
    assert down_revisions["a8f1c2d3e4b5"] == ("b7e8f9a0b1c2",)
    assert down_revisions["b9d8e7f6a5b4"] == ("a8f1c2d3e4b5",)
    assert down_revisions["1f2e3d4c5b6a"] == ("f6a7b8c9d0e1",)
    assert down_revisions["c9d0e1f2a3b4"] == ("1f2e3d4c5b6a",)


def test_removed_bridge_revisions_stay_deleted_after_linearization():
    removed_files = [
        "c4b1a7e8d9f0_legacy_agent_findings_report_bridge.py",
        "d4e5f6a7b8c9_merge_phpstan_and_agent_heads.py",
        "5f6a7b8c9d0e_merge_project_metrics_and_yasa_phpstan_heads.py",
        "90a71996ac03_add_project_management_metrics_table.py",
    ]

    for file_name in removed_files:
        assert not (VERSIONS_DIR / file_name).exists()


def test_bridge_downgrade_keeps_zip_file_hash_baseline_contract():
    bridge_file = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "6c8d9e0f1a2b_finalize_projects_zip_file_hash.py"
    )
    bridge_source = bridge_file.read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS zip_file_hash" not in bridge_source
    assert "DROP INDEX IF EXISTS ix_projects_zip_file_hash" not in bridge_source


def test_static_finding_path_migration_downgrade_keeps_data_normalization_contract():
    migration_file = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "7f8e9d0c1b2a_normalize_static_finding_paths.py"
    )
    migration_source = migration_file.read_text(encoding="utf-8")

    assert "bandit_findings" in migration_source
    assert "opengrep_findings" in migration_source
    assert "downgrade" in migration_source
    assert "UPDATE bandit_findings" not in migration_source.split("def downgrade", 1)[1]
    assert "UPDATE opengrep_findings" not in migration_source.split("def downgrade", 1)[1]


def test_squashed_baseline_migration_uses_frozen_schema_snapshot():
    baseline_file = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "5b0f3c9a6d7e_squashed_baseline.py"
    )
    baseline_source = baseline_file.read_text(encoding="utf-8")

    assert "from app.models import *" not in baseline_source
    assert "Base.metadata.create_all" not in baseline_source
    assert "app.db.schema_snapshots.baseline_5b0f3c9a6d7e" in baseline_source


def test_squashed_baseline_snapshot_keeps_only_pre_squash_tables():
    snapshot_file = SNAPSHOTS_DIR / "baseline_5b0f3c9a6d7e.py"
    snapshot_source = snapshot_file.read_text(encoding="utf-8")
    module = ast.parse(snapshot_source)

    expected_tables = {
        "agent_checkpoints",
        "agent_events",
        "agent_findings",
        "agent_tasks",
        "agent_tree_nodes",
        "audit_issues",
        "audit_rule_sets",
        "audit_rules",
        "audit_tasks",
        "bandit_findings",
        "bandit_scan_tasks",
        "gitleaks_findings",
        "gitleaks_rules",
        "gitleaks_scan_tasks",
        "instant_analyses",
        "opengrep_findings",
        "opengrep_rules",
        "opengrep_scan_tasks",
        "phpstan_findings",
        "phpstan_scan_tasks",
        "project_info",
        "project_members",
        "projects",
        "prompt_templates",
        "user_configs",
        "users",
    }

    found_tables = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != "__tablename__":
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found_tables.add(node.value.value)

    assert found_tables == expected_tables
    assert "project_management_metrics" not in found_tables
    assert "bandit_rule_states" not in found_tables
    assert "phpstan_rule_states" not in found_tables
    assert "yasa_scan_tasks" not in found_tables
    assert "yasa_findings" not in found_tables
    assert "zip_file_hash" not in snapshot_source
