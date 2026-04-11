from pathlib import Path

import pytest

from app.services.agent.bootstrap_entrypoints import _build_seed_from_entrypoints
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


@pytest.mark.asyncio
async def test_build_seed_from_entrypoints_returns_seeds_with_entry_points(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    # quick_mode=True 只扫描高风险文件名：包含 api/controller/route 等关键词
    (src_dir / "api.py").write_text(
        "\n".join(
            [
                "from flask import request",
                "",
                "def handler():",
                "    x = request.args.get('x')",
                "    return eval(x)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    entry_funcs = ["start", "handler"]
    seeds = await _build_seed_from_entrypoints(
        project_root=str(tmp_path),
        target_vulns=["command_injection"],
        entry_function_names=entry_funcs,
    )

    assert isinstance(seeds, list)
    assert seeds, "expected fallback seeds to be non-empty"
    first = seeds[0]
    assert first.get("file_path") == "src/api.py"
    assert isinstance(first.get("entry_points"), list)
    assert first.get("entry_points")[:2] == entry_funcs
