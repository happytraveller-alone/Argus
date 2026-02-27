from pathlib import Path

from app.services.agent.qmd.task_kb import QmdTaskKnowledgeBase


def test_task_kb_upsert_deduplicates_and_uses_mask(tmp_path):
    kb = QmdTaskKnowledgeBase(
        project_root=str(tmp_path),
        task_id="task-1",
        command="npx -y @tobilu/qmd",
    )
    calls: list[list[str]] = []

    def _fake_run_cli(args, *, expect_json, ensure_collection=True):
        del expect_json, ensure_collection
        calls.append(list(args))
        return {"success": True, "stdout": "", "stderr": "", "data": []}

    kb._run_cli = _fake_run_cli  # type: ignore[method-assign]

    ready = kb.ensure_ready()
    assert ready["success"] is True
    assert any(call[:3] == ["collection", "add", str(kb.task_root)] for call in calls)
    assert any("--mask" in call for call in calls)

    assert kb.upsert_text("agents/recon.md", "hello") is True
    assert kb.upsert_text("agents/recon.md", "hello") is False

    update = kb.update_index(force=False)
    assert update["success"] is True
    assert update["updated"] is True
    assert kb.update_index(force=False)["updated"] is False


def test_task_kb_query_falls_back_to_search(tmp_path):
    kb = QmdTaskKnowledgeBase(
        project_root=str(tmp_path),
        task_id="task-2",
        command="npx -y @tobilu/qmd",
    )
    kb._collection_ready = True

    def _fake_ensure_ready():
        return {"success": True}

    steps: list[str] = []

    def _fake_run_cli(args, *, expect_json, ensure_collection=True):
        del expect_json, ensure_collection
        cmd = str(args[0])
        steps.append(cmd)
        if cmd == "query":
            return {"success": False, "error": "llama_unavailable", "stdout": "", "stderr": "missing build deps"}
        if cmd == "search":
            return {"success": True, "data": [{"docid": "a.md"}], "stdout": "[]", "stderr": ""}
        return {"success": True, "data": [], "stdout": "", "stderr": ""}

    kb.ensure_ready = _fake_ensure_ready  # type: ignore[method-assign]
    kb._run_cli = _fake_run_cli  # type: ignore[method-assign]

    result = kb.query(query_text="find parser", limit=3)
    assert result["success"] is True
    assert result["data"] == [{"docid": "a.md"}]
    assert result.get("metadata", {}).get("fallback") == "search"
    assert steps[:2] == ["query", "search"]


def test_task_kb_prevents_path_escape(tmp_path):
    kb = QmdTaskKnowledgeBase(
        project_root=str(tmp_path),
        task_id="task-3",
        command="npx -y @tobilu/qmd",
    )
    kb._collection_ready = True
    kb.ensure_ready = lambda: {"success": True}  # type: ignore[method-assign]
    kb._run_cli = lambda *args, **kwargs: {"success": True, "data": []}  # type: ignore[method-assign]

    try:
        kb.upsert_text("../escape.txt", "x")
    except ValueError as exc:
        assert "path_outside_task_root" in str(exc)
    else:
        raise AssertionError("expected ValueError for path traversal")

    assert not Path(tmp_path / "escape.txt").exists()
