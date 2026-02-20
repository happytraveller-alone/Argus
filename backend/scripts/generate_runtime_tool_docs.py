#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Tuple


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.v1.endpoints.agent_tasks import _initialize_tools  # noqa: E402
from app.services.agent.tools import FunctionContextTool, RAGQueryTool, SecurityCodeSearchTool  # noqa: E402


DOCS_ROOT = BACKEND_DIR / "docs" / "agent-tools"
TOOLS_DOC_DIR = DOCS_ROOT / "tools"
SHARED_CATALOG_PATH = DOCS_ROOT / "TOOL_SHARED_CATALOG.md"
INDEX_PATH = DOCS_ROOT / "INDEX.md"

OPTIONAL_RUNTIME_TOOLS = {
    "rag_query": ("analysis", RAGQueryTool(SimpleNamespace())),
    "security_search": ("analysis", SecurityCodeSearchTool(SimpleNamespace())),
    "function_context": ("analysis", FunctionContextTool(SimpleNamespace())),
}

CATEGORY_ORDER = [
    "代码读取与定位",
    "候选发现与模式扫描",
    "可达性与逻辑分析",
    "漏洞验证与 PoC 规划",
    "报告与协作编排",
]


def _ensure_demo_project(project_root: Path) -> None:
    (project_root / "src").mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "main.py").write_text(
        "def main(payload):\n    return payload\n",
        encoding="utf-8",
    )


async def _collect_runtime_tools_async() -> Dict[str, Dict[str, Any]]:
    with TemporaryDirectory(prefix="tool_docs_") as tmp:
        project_root = Path(tmp) / "demo_project"
        _ensure_demo_project(project_root)

        tools = await _initialize_tools(
            project_root=str(project_root),
            llm_service=SimpleNamespace(),
            user_config=None,
            sandbox_manager=SimpleNamespace(),
            rag_enabled=False,
            verification_level="analysis_with_poc_plan",
            exclude_patterns=[],
            target_files=None,
            project_id="docs-generator",
            event_emitter=None,
            task_id=None,
        )

    registry: Dict[str, Dict[str, Any]] = {}
    for phase_name, phase_tools in tools.items():
        if not isinstance(phase_tools, dict):
            continue
        for runtime_key, tool in phase_tools.items():
            item = registry.setdefault(
                runtime_key,
                {
                    "tool": tool,
                    "phases": set(),
                    "optional": False,
                },
            )
            item["phases"].add(phase_name)

    for runtime_key, (phase_name, tool) in OPTIONAL_RUNTIME_TOOLS.items():
        item = registry.setdefault(
            runtime_key,
            {
                "tool": tool,
                "phases": set(),
                "optional": True,
            },
        )
        item["phases"].add(phase_name)
        item["optional"] = True

    return registry


def collect_runtime_tools() -> Dict[str, Dict[str, Any]]:
    return asyncio.run(_collect_runtime_tools_async())


def _schema_dict(args_schema: Any) -> Dict[str, Any]:
    if args_schema is None:
        return {}
    if hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema() or {}
    if hasattr(args_schema, "schema"):
        return args_schema.schema() or {}
    return {}


def _example_value(field_schema: Dict[str, Any]) -> Any:
    field_type = field_schema.get("type")
    if field_type == "string":
        return field_schema.get("default", "<text>")
    if field_type == "integer":
        return field_schema.get("default", 1)
    if field_type == "number":
        return field_schema.get("default", 0.5)
    if field_type == "boolean":
        return field_schema.get("default", True)
    if field_type == "array":
        return field_schema.get("default", [])
    if field_type == "object":
        return field_schema.get("default", {})
    if "enum" in field_schema and isinstance(field_schema["enum"], list) and field_schema["enum"]:
        return field_schema["enum"][0]
    return field_schema.get("default", "<value>")


def _infer_goal_and_tasks(runtime_key: str, description: str, phases: Iterable[str]) -> Tuple[str, List[str], str]:
    key = runtime_key.lower()
    phase_text = "/".join(sorted({str(p) for p in phases}))
    if key in {"read_file", "list_files", "search_code", "extract_function", "function_context"}:
        return (
            "定位目标代码、函数上下文与证据位置。",
            [
                "读取代码文件并定位行号上下文。",
                "快速检索关键词并筛选有效命中。",
                "提取函数级上下文供后续验证链路使用。",
            ],
            "代码读取与定位",
        )
    if key in {"smart_scan", "quick_audit", "pattern_match", "rag_query", "security_search", "query_security_knowledge", "get_vulnerability_knowledge"}:
        return (
            "快速发现候选漏洞与高风险模式。",
            [
                "批量扫描候选风险点。",
                "按漏洞类型或语义检索相关代码。",
                "为后续验证阶段提供优先级线索。",
            ],
            "候选发现与模式扫描",
        )
    if key in {"dataflow_analysis", "controlflow_analysis_light", "logic_authz_analysis", "joern_reachability_verify"}:
        return (
            "判断漏洞是否可达、是否受逻辑/授权路径约束。",
            [
                "分析源到汇的数据流链路。",
                "计算控制流可达路径与关键条件。",
                "验证授权边界和业务逻辑约束。",
            ],
            "可达性与逻辑分析",
        )
    if key.startswith("test_") or key in {"universal_vuln_test"}:
        return (
            "执行非武器化验证步骤并收集可复现实验信号。",
            [
                "构造安全可控的测试输入。",
                "观察返回、日志与行为差异。",
                "输出验证结果与证据摘要。",
            ],
            "漏洞验证与 PoC 规划",
        )
    return (
        f"在 {phase_text or 'agent'} 阶段支撑审计编排和结果产出。",
        [
            "协助 Agent 制定下一步行动。",
            "沉淀中间结论与可追溯信息。",
            "保障任务收敛与结果可交付性。",
        ],
        "报告与协作编排",
    )


def _build_tool_doc(runtime_key: str, tool: Any, phases: Iterable[str], optional: bool) -> Tuple[str, str]:
    description = str(getattr(tool, "description", "") or "").strip()
    goal, tasks, category = _infer_goal_and_tasks(runtime_key, description, phases)
    schema = _schema_dict(getattr(tool, "args_schema", None))
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = set(schema.get("required", [])) if isinstance(schema, dict) else set()

    example_payload: Dict[str, Any] = {}
    input_lines: List[str] = []
    for field_name, field_schema in properties.items():
        field_desc = str(field_schema.get("description", "")).strip()
        field_type = str(field_schema.get("type", "any"))
        required_text = "required" if field_name in required else "optional"
        input_lines.append(f"- `{field_name}` ({field_type}, {required_text}): {field_desc or 'N/A'}")
        if field_name in required or len(example_payload) < 3:
            example_payload[field_name] = _example_value(field_schema)

    if not input_lines:
        input_lines = ["- 无显式参数（工具内部处理）。"]

    phases_text = ", ".join(sorted({str(p) for p in phases})) or "unknown"
    optional_text = "是" if optional else "否"

    doc = f"""# Tool: `{runtime_key}`

## Tool Purpose
{description or "N/A"}

## Goal
{goal}

## Task List
{"".join(f"- {item}\n" for item in tasks)}

## Inputs
{"".join(f"{line}\n" for line in input_lines)}

### Example Input
```json
{json.dumps(example_payload, ensure_ascii=False, indent=2)}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“{goal}”时触发。
- 常见阶段: `{phases_text}`。
- 分类: `{category}`。
- 可选工具: `{optional_text}`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
"""
    return doc, category


def _build_shared_catalog(registry: Dict[str, Dict[str, Any]], tool_categories: Dict[str, str]) -> str:
    sections: Dict[str, List[str]] = {name: [] for name in CATEGORY_ORDER}

    for runtime_key in sorted(registry):
        tool_info = registry[runtime_key]
        tool = tool_info["tool"]
        phases = tool_info["phases"]
        goal, tasks, _ = _infer_goal_and_tasks(runtime_key, str(getattr(tool, "description", "")), phases)
        category = tool_categories.get(runtime_key, "报告与协作编排")
        sections.setdefault(category, [])
        sections[category].append(
            "\n".join(
                [
                    f"- 工具: `{runtime_key}`",
                    f"  - 目标: {goal}",
                    f"  - 推荐任务: {'；'.join(tasks)}",
                    "  - 反例/误用: 在无有效输入或无证据时直接下结论。",
                ]
            )
        )

    lines: List[str] = [
        "# TOOL_SHARED_CATALOG",
        "",
        "该目录按“目标 -> 推荐工具 -> 可完成任务 -> 反例/误用”汇总运行时工具能力。",
        "",
    ]
    for category in CATEGORY_ORDER:
        lines.append(f"## {category}")
        if sections.get(category):
            lines.extend(sections[category])
        else:
            lines.append("- 暂无工具映射。")
        lines.append("")

    lines.append("## 工具全量索引")
    for runtime_key in sorted(registry):
        lines.append(f"- `{runtime_key}`")
    lines.append("")
    return "\n".join(lines)


def _build_index(registry: Dict[str, Dict[str, Any]]) -> str:
    lines = [
        "# Agent Tool Docs Index",
        "",
        f"- Runtime 工具总数: **{len(registry)}**",
        f"- 共享目录: `{SHARED_CATALOG_PATH.relative_to(BACKEND_DIR)}`",
        "",
        "## Tool Docs",
    ]
    for runtime_key in sorted(registry):
        rel = (TOOLS_DOC_DIR / f"{runtime_key}.md").relative_to(BACKEND_DIR)
        lines.append(f"- `{runtime_key}` -> `{rel}`")
    lines.append("")
    return "\n".join(lines)


def generate_runtime_tool_docs() -> Dict[str, Any]:
    registry = collect_runtime_tools()
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    TOOLS_DOC_DIR.mkdir(parents=True, exist_ok=True)

    tool_categories: Dict[str, str] = {}
    for runtime_key in sorted(registry):
        info = registry[runtime_key]
        tool_doc, category = _build_tool_doc(
            runtime_key=runtime_key,
            tool=info["tool"],
            phases=info["phases"],
            optional=bool(info.get("optional")),
        )
        tool_categories[runtime_key] = category
        (TOOLS_DOC_DIR / f"{runtime_key}.md").write_text(tool_doc, encoding="utf-8")

    SHARED_CATALOG_PATH.write_text(_build_shared_catalog(registry, tool_categories), encoding="utf-8")
    INDEX_PATH.write_text(_build_index(registry), encoding="utf-8")

    return {
        "tool_count": len(registry),
        "tools_dir": str(TOOLS_DOC_DIR),
        "shared_catalog": str(SHARED_CATALOG_PATH),
        "index": str(INDEX_PATH),
    }


def main() -> None:
    result = generate_runtime_tool_docs()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

