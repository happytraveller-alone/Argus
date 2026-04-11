#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.generate_runtime_tool_docs import (  # noqa: E402
    DOCS_ROOT,
    FILE_TOOL_SKILL_SPECS,
    PLAYBOOK_PATH,
    SKILLS_DOC_DIR,
    SKILLS_INDEX_PATH,
    SHARED_CATALOG_PATH,
    TOOLS_DOC_DIR,
    collect_runtime_tools,
)


REQUIRED_DOC_HEADING_ALIASES = {
    "## Goal": [
        "## Goal",
        "## 目标",
        "## Tool Purpose",
        "## 概述",
    ],
    "## Task List": [
        "## Task List",
        "## 推荐调用链",
        "## 任务清单",
        "## 工作原理",
        "## 使用方法",
        "## Typical Triggers",
    ],
    "## Inputs": [
        "## Inputs",
        "## 输入参数",
        "## 输入",
    ],
    "## Outputs": [
        "## Outputs",
        "## 输出",
        "## 返回格式",
    ],
}


def validate_runtime_tool_docs() -> Dict[str, Any]:
    registry = collect_runtime_tools()
    expected_tools = sorted(registry.keys())

    missing_docs: List[str] = []
    missing_headings: Dict[str, List[str]] = {}

    for runtime_key in expected_tools:
        doc_path = TOOLS_DOC_DIR / f"{runtime_key}.md"
        if not doc_path.exists():
            missing_docs.append(runtime_key)
            continue
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        missing = [
            heading
            for heading, aliases in REQUIRED_DOC_HEADING_ALIASES.items()
            if not any(alias in text for alias in aliases)
        ]
        if missing:
            missing_headings[runtime_key] = missing

    missing_catalog_entries: List[str] = []
    catalog_text = ""
    if SHARED_CATALOG_PATH.exists():
        catalog_text = SHARED_CATALOG_PATH.read_text(encoding="utf-8", errors="replace")
    for runtime_key in expected_tools:
        if f"`{runtime_key}`" not in catalog_text:
            missing_catalog_entries.append(runtime_key)

    missing_skill_docs: List[str] = []
    for tool_name in sorted(FILE_TOOL_SKILL_SPECS.keys()):
        skill_path = SKILLS_DOC_DIR / f"{tool_name}.skill.md"
        if not skill_path.exists():
            missing_skill_docs.append(tool_name)

    missing_skills_index = not SKILLS_INDEX_PATH.exists()
    missing_playbook = not PLAYBOOK_PATH.exists()

    return {
        "expected_tool_count": len(expected_tools),
        "missing_docs": missing_docs,
        "missing_headings": missing_headings,
        "missing_catalog_entries": missing_catalog_entries,
        "missing_skill_docs": missing_skill_docs,
        "missing_skills_index": missing_skills_index,
        "missing_playbook": missing_playbook,
        "docs_root": str(DOCS_ROOT),
    }


def main() -> None:
    result = validate_runtime_tool_docs()
    ok = (
        not result["missing_docs"]
        and not result["missing_headings"]
        and not result["missing_catalog_entries"]
        and not result["missing_skill_docs"]
        and not result["missing_skills_index"]
        and not result["missing_playbook"]
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
