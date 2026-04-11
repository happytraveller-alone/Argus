import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from app.services.agent.bootstrap_entrypoints import (
    _build_seed_from_entrypoints,
    _discover_entry_points_deterministic,
)


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_entry_points_deterministic_ignores_hidden_test_and_config_paths():
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        _write_file(root / "src" / "main.py", '@app.get("/alive")\ndef alive():\n    return "ok"\n')
        _write_file(root / "tests" / "test_api.py", '@app.get("/from-test")\ndef bad():\n    return "bad"\n')
        _write_file(root / ".github" / "scanner.py", '@app.get("/from-hidden")\ndef bad():\n    return "bad"\n')
        _write_file(root / "app" / "settings.py", "DEBUG=True\n")

        result = _discover_entry_points_deterministic(str(root))
        files = {item["file"] for item in result["entry_points"]}

        assert "src/main.py" in files
        assert "tests/test_api.py" not in files
        assert ".github/scanner.py" not in files
        assert "app/settings.py" not in files


def test_build_seed_from_entrypoints_returns_seeds_with_entry_points():
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        _write_file(
            root / "src" / "api.py",
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
        )

        entry_funcs = ["start", "handler"]
        tools_module = ModuleType("app.services.agent.tools")

        class _FakeSmartScanTool:
            def __init__(self, *_args, **_kwargs):
                pass

            async def execute(self, **_kwargs):
                return SimpleNamespace(
                    success=True,
                    metadata={
                        "findings": [
                            {
                                "file_path": "src/api.py",
                                "line_number": 4,
                                "vulnerability_type": "command_injection",
                                "severity": "high",
                                "pattern_name": "dangerous-eval",
                                "matched_line": "return eval(x)",
                            }
                        ]
                    },
                )

        tools_module.SmartScanTool = _FakeSmartScanTool

        with patch.dict("sys.modules", {"app.services.agent.tools": tools_module}):
            seeds = asyncio.run(
                _build_seed_from_entrypoints(
                    project_root=str(root),
                    target_vulns=["command_injection"],
                    entry_function_names=entry_funcs,
                )
            )

        assert isinstance(seeds, list)
        assert seeds
        first = seeds[0]
        assert first.get("file_path") == "src/api.py"
        assert first.get("entry_points")[:2] == entry_funcs
