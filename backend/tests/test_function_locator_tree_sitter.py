from pathlib import Path

from app.services.agent.flow.lightweight.function_locator import EnclosingFunctionLocator


def test_function_locator_supports_java_kotlin_and_filters_c_attribute(tmp_path: Path):
    java_file = tmp_path / "Demo.java"
    java_file.write_text(
        "\n".join(
            [
                "public class Demo {",
                "    public Demo() {}",
                "    public String login(String user) {",
                "        return user;",
                "    }",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    kotlin_file = tmp_path / "Demo.kt"
    kotlin_file.write_text(
        "\n".join(
            [
                "class Demo {",
                "    fun login(user: String): String {",
                "        return user",
                "    }",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    c_file = tmp_path / "demo.c"
    c_file.write_text(
        "\n".join(
            [
                "static __attribute__((unused)) int parse_node(int input) {",
                "    return input + 1;",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    locator = EnclosingFunctionLocator(project_root=str(tmp_path))

    java_result = locator.locate(
        full_file_path=str(java_file),
        line_start=4,
        relative_file_path="Demo.java",
    )
    assert java_result["function"] == "login"
    assert java_result["language"] == "java"
    assert java_result["start_line"] <= 4 <= java_result["end_line"]

    kotlin_result = locator.locate(
        full_file_path=str(kotlin_file),
        line_start=3,
        relative_file_path="Demo.kt",
    )
    assert kotlin_result["function"] == "login"
    assert kotlin_result["language"] == "kotlin"
    assert kotlin_result["start_line"] <= 3 <= kotlin_result["end_line"]

    c_result = locator.locate(
        full_file_path=str(c_file),
        line_start=2,
        relative_file_path="demo.c",
    )
    assert c_result["function"] == "parse_node"
    assert c_result["function"] != "__attribute__"
    assert c_result["language"] == "c"
