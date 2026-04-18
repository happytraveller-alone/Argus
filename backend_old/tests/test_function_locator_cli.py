from pathlib import Path

from app.services.agent.core.flow.lightweight.function_locator import EnclosingFunctionLocator
from app.services.agent.core.flow.lightweight.function_locator_cli import (
    locate_with_tree_sitter_cli,
)


def test_function_locator_cli_supports_multiline_c_signature(tmp_path: Path):
    target = tmp_path / "time64.c"
    target.write_text(
        "\n".join(
            [
                "char *asctime64_r(const struct tm *tm, char *buf)",
                "{",
                "  if (!buf) return 0;",
                "  return buf;",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    result = locate_with_tree_sitter_cli(
        file_path=str(target),
        line_start=4,
        language="c",
    )

    assert result["function"] == "asctime64_r"
    assert result["start_line"] == 1
    assert result["end_line"] >= 5
    assert result["resolution_engine"] == "tree_sitter_cli_regex"


def test_enclosing_function_locator_reports_unknown_language(tmp_path: Path):
    target = tmp_path / "demo.rb"
    target.write_text(
        "\n".join(
            [
                "def login(user)",
                "  user",
                "end",
            ]
        ),
        encoding="utf-8",
    )

    locator = EnclosingFunctionLocator(project_root=str(tmp_path))
    result = locator.locate(
        full_file_path=str(target),
        line_start=2,
        relative_file_path="demo.rb",
    )

    assert result["function"] is None
    assert result["resolution_engine"] == "unsupported_language"
    assert result["diagnostics"] == ["unknown_language"]
