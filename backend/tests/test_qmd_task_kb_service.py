from pathlib import Path
import subprocess

from app.services.agent.qmd.task_kb import QmdTaskKnowledgeBase


def test_task_kb_upsert_deduplicates_and_uses_mask(tmp_path):
    kb = QmdTaskKnowledgeBase(
        project_root=str(tmp_path),
        task_id="task-1",
        command="qmd",
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
        command="qmd",
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
        command="qmd",
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


def test_task_kb_retries_with_qmd_when_dlx_binding_missing(tmp_path, monkeypatch):
    kb = QmdTaskKnowledgeBase(
        project_root=str(tmp_path),
        task_id="task-4",
        command="pnpm dlx @tobilu/qmd",
    )
    kb._collection_ready = True
    kb.ensure_ready = lambda: {"success": True}  # type: ignore[method-assign]

    def _fake_which(binary: str):
        if binary == "qmd":
            return "/usr/local/bin/qmd"
        return None

    def _fake_run(command, **kwargs):
        del kwargs
        if command and str(command[0]).endswith("pnpm"):
            return subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout="",
                stderr="Ignored build scripts for better-sqlite3; Could not locate the bindings file node-v127",
            )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("app.services.agent.qmd.task_kb.shutil.which", _fake_which)
    monkeypatch.setattr("app.services.agent.qmd.task_kb.subprocess.run", _fake_run)

    result = kb.status()

    assert result["success"] is True
    assert result.get("fallback_command_used") == "/usr/local/bin/qmd"
    assert result.get("fallback_reason") == "dlx_native_binding_failure"
