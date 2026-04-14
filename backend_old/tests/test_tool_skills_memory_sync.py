from app.api.v1.endpoints.agent_tasks_tool_runtime import (
    _build_tool_skills_snapshot,
    _sync_tool_playbook_to_memory,
    _sync_tool_skills_to_memory,
)
from app.services.agent.memory.markdown_memory import MarkdownMemoryStore


def test_build_tool_skills_snapshot_has_core_tools():
    snapshot = _build_tool_skills_snapshot(max_chars=12000)

    assert "Tool Playbook" in snapshot
    assert "Skill: read_file" in snapshot
    assert "Skill: search_code" in snapshot
    assert "Skill: list_files" in snapshot
    assert "`get_symbol_body`" in snapshot
    assert "Skill: locate_enclosing_function" in snapshot


def test_tool_skills_sync_writes_skills_memory(tmp_path):
    store = MarkdownMemoryStore(project_id="tool-skill-sync", base_dir=tmp_path, max_bytes=2_000_000)
    store.ensure()

    _sync_tool_skills_to_memory(
        memory_store=store,
        task_id="task-tool-skill-sync-1",
        max_chars=12000,
    )
    _sync_tool_playbook_to_memory(
        memory_store=store,
        task_id="task-tool-skill-sync-1",
        max_chars=12000,
    )

    bundle = store.load_bundle(max_chars=26000, skills_max_lines=520)
    skills_text = bundle.get("skills", "")
    shared_text = bundle.get("shared", "")
    first_220_lines = "\n".join(skills_text.splitlines()[:220])

    assert "Agent Tool Skills Snapshot" in skills_text
    assert "Skill: search_code" in first_220_lines
    assert "Skill: read_file" in skills_text
    assert "Skill: list_files" in skills_text
    assert "`get_symbol_body`" in skills_text
    assert "工具说明同步" in shared_text
    assert "MCP 工具说明同步" not in shared_text
