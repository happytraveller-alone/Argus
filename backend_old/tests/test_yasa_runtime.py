from pathlib import Path

import app.services.yasa_runtime as yasa_runtime


def test_resolve_yasa_uast_sdk_path_returns_language_specific_binary(
    tmp_path: Path,
    monkeypatch,
):
    uast_binary = tmp_path / "uast4go" / "uast4go"
    uast_binary.parent.mkdir(parents=True)
    uast_binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uast_binary.chmod(0o755)

    monkeypatch.setattr(yasa_runtime, "_YASA_UAST_SEARCH_ROOTS", (tmp_path,))

    assert yasa_runtime.resolve_yasa_uast_sdk_path("golang") == str(uast_binary)


def test_build_yasa_scan_command_appends_uast_sdk_path_for_golang(monkeypatch):
    monkeypatch.setattr(
        yasa_runtime,
        "resolve_yasa_uast_sdk_path",
        lambda language, **_kwargs: "/opt/yasa/engine/deps/uast4go/uast4go",
    )

    cmd = yasa_runtime.build_yasa_scan_command(
        binary="/opt/yasa/bin/yasa",
        source_path="/tmp/project",
        language="golang",
        report_dir="/tmp/report",
        checker_pack_ids=["taint-flow-golang-default"],
        checker_ids=["custom-checker"],
        rule_config_file="/opt/yasa/resource/example-rule-config/rule_config_go.json",
    )

    assert cmd == [
        "/opt/yasa/bin/yasa",
        "--sourcePath",
        "/tmp/project",
        "--language",
        "golang",
        "--report",
        "/tmp/report",
        "--checkerPackIds",
        "taint-flow-golang-default",
        "--checkerIds",
        "custom-checker",
        "--ruleConfigFile",
        "/opt/yasa/resource/example-rule-config/rule_config_go.json",
        "--uastSDKPath",
        "/opt/yasa/engine/deps/uast4go/uast4go",
    ]


def test_build_yasa_scan_command_skips_uast_sdk_path_when_not_needed(monkeypatch):
    monkeypatch.setattr(yasa_runtime, "resolve_yasa_uast_sdk_path", lambda language, **_kwargs: None)

    cmd = yasa_runtime.build_yasa_scan_command(
        binary="/opt/yasa/bin/yasa",
        source_path="/tmp/project",
        language="java",
        report_dir="/tmp/report",
        checker_pack_ids=["taint-flow-java-default"],
    )

    assert "--uastSDKPath" not in cmd
