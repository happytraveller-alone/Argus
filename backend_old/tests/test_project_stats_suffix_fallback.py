import json

import pytest

from app.services.upload import project_stats


def test_build_suffix_fallback_payload_counts_languages(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.py").write_text("print('a')\nprint('b')\n", encoding="utf-8")
    (src_dir / "app.ts").write_text("const a = 1;\n", encoding="utf-8")

    ignored_dir = tmp_path / "node_modules"
    ignored_dir.mkdir(parents=True, exist_ok=True)
    (ignored_dir / "ignore.js").write_text("console.log('skip')\n", encoding="utf-8")

    payload = project_stats._build_suffix_fallback_payload(str(tmp_path))
    parsed = json.loads(payload)

    assert parsed["total"] == 3
    assert parsed["total_files"] == 2
    assert parsed["languages"]["Python"]["loc_number"] == 2
    assert parsed["languages"]["Python"]["files_count"] == 1
    assert parsed["languages"]["TypeScript"]["loc_number"] == 1
    assert parsed["languages"]["TypeScript"]["files_count"] == 1


@pytest.mark.asyncio
async def test_get_cloc_stats_from_extracted_dir_uses_suffix_fallback_when_cloc_empty(
    tmp_path, monkeypatch
):
    (tmp_path / "main.py").write_text("print('fallback')\n", encoding="utf-8")

    monkeypatch.setattr(
        project_stats,
        "_run_cloc_on_directory",
        lambda *_args, **_kwargs: '{"total": 0, "total_files": 0, "languages": {}}',
    )

    payload = await project_stats.get_cloc_stats_from_extracted_dir(str(tmp_path))
    parsed = json.loads(payload)

    assert parsed["total_files"] == 1
    assert "Python" in parsed["languages"]


def test_is_non_empty_language_payload():
    assert project_stats._is_non_empty_language_payload(
        '{"total": 3, "total_files": 2, "languages": {"Python": {"loc_number": 3, "files_count": 2, "proportion": 1.0}}}'
    )
    assert not project_stats._is_non_empty_language_payload(
        '{"total": 0, "total_files": 0, "languages": {}}'
    )
