from app.api.v1.endpoints.agent_tasks_tool_runtime import _sync_tool_catalog_to_memory
from app.services.agent.memory.markdown_memory import MarkdownMemoryStore


def test_tool_catalog_sync_writes_shared_memory(tmp_path):
    store = MarkdownMemoryStore(project_id="tool-sync", base_dir=tmp_path, max_bytes=2_000_000)
    store.ensure()

    _sync_tool_catalog_to_memory(
        memory_store=store,
        task_id="task-tool-sync-1",
        max_chars=3000,
    )

    bundle = store.load_bundle(max_chars=10000, skills_max_lines=30)
    shared_text = bundle.get("shared", "")
    assert "tool_catalog_sync" in shared_text
    assert "TOOL_SHARED_CATALOG" in shared_text
