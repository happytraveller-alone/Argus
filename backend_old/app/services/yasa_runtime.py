from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

YASA_RUNNER_BINARY = "/opt/yasa/bin/yasa"
YASA_RUNNER_RESOURCE_DIR = "/opt/yasa/resource"

_YASA_UAST_BINARY_BY_LANGUAGE: dict[str, str] = {
    "golang": "uast4go",
    "python": "uast4py",
}

_YASA_UAST_SEARCH_ROOTS: tuple[Path, ...] = (
    Path("/opt/yasa/engine/deps"),
    Path("/snapshot/YASA-Engine/deps"),
)

_YASA_RUNNER_UAST_BINARY_BY_LANGUAGE: dict[str, str] = {
    "golang": "/opt/yasa/engine/deps/uast4go/uast4go",
    "python": "/opt/yasa/engine/deps/uast4py/uast4py",
}


def resolve_yasa_uast_sdk_path(
    language: Optional[str],
    *,
    prefer_runner_paths: bool = False,
) -> Optional[str]:
    normalized = str(language or "").strip().lower()
    binary_name = _YASA_UAST_BINARY_BY_LANGUAGE.get(normalized)
    if not binary_name:
        return None

    for root in _YASA_UAST_SEARCH_ROOTS:
        candidate = root / binary_name / binary_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    if prefer_runner_paths:
        return _YASA_RUNNER_UAST_BINARY_BY_LANGUAGE.get(normalized)
    return None


def build_yasa_rule_config_path(
    rule_config_name: str,
    *,
    resource_dir: str = YASA_RUNNER_RESOURCE_DIR,
) -> str:
    normalized = str(rule_config_name or "").strip()
    if not normalized:
        raise ValueError("rule_config_name is required")
    return str(Path(resource_dir) / "example-rule-config" / normalized)


def build_yasa_scan_command(
    *,
    binary: str,
    source_path: str,
    language: str,
    report_dir: str,
    checker_pack_ids: list[str],
    checker_ids: Optional[list[str]] = None,
    rule_config_file: Optional[str] = None,
    use_runner_paths: bool = False,
) -> list[str]:
    cmd = [
        binary,
        "--sourcePath",
        source_path,
        "--language",
        language,
        "--report",
        report_dir,
        "--checkerPackIds",
        ",".join(checker_pack_ids),
    ]
    if checker_ids:
        cmd.extend(["--checkerIds", ",".join(checker_ids)])
    if rule_config_file:
        cmd.extend(["--ruleConfigFile", rule_config_file])

    uast_sdk_path = resolve_yasa_uast_sdk_path(
        language,
        prefer_runner_paths=use_runner_paths,
    )
    if uast_sdk_path:
        cmd.extend(["--uastSDKPath", uast_sdk_path])

    return cmd
