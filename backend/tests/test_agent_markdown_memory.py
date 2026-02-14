from pathlib import Path

from app.services.agent.memory.markdown_memory import MarkdownMemoryStore


def test_markdown_memory_append_and_rotate(tmp_path: Path):
    store = MarkdownMemoryStore(project_id="p1", base_dir=tmp_path, max_bytes=300)
    store.ensure()

    project_dir = tmp_path / "p1"
    for name in (
        "shared.md",
        "orchestrator.md",
        "recon.md",
        "analysis.md",
        "verification.md",
        "skills.md",
    ):
        assert (project_dir / name).exists()

    store.append_entry(
        "shared",
        task_id="t1",
        source="opengrep_bootstrap",
        title="small",
        summary="a" * 80,
        payload={"k": 1},
    )

    store.append_entry(
        "shared",
        task_id="t1",
        source="opengrep_bootstrap",
        title="big",
        summary="b" * 600,
        payload={"k": 2, "data": "x" * 200},
    )

    archives = list(project_dir.glob("shared.*.archive.md"))
    assert archives, "expected rotation to create an archive file"

    shared_text = (project_dir / "shared.md").read_text(encoding="utf-8", errors="replace")
    assert "archived:" in shared_text
    assert "```json" in shared_text

    bundle = store.load_bundle(max_chars=2000, skills_max_lines=10)
    assert "shared" in bundle and "skills" in bundle

