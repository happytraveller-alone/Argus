from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .runtime import ToolExecutionResult, ToolRuntime


def normalize_listed_tools(raw: Any) -> List[Dict[str, Any]]:
    tools: Any = raw
    if isinstance(raw, dict):
        if isinstance(raw.get("tools"), list):
            tools = raw.get("tools")
        elif isinstance(raw.get("result"), dict) and isinstance(raw["result"].get("tools"), list):
            tools = raw["result"]["tools"]
        elif isinstance(raw.get("result"), list):
            tools = raw.get("result")

    if not isinstance(tools, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in tools:
        if isinstance(item, dict):
            source = dict(item)
        elif hasattr(item, "model_dump"):
            try:
                dumped = item.model_dump()  # type: ignore[attr-defined]
            except Exception:
                dumped = None
            if not isinstance(dumped, dict):
                continue
            source = dict(dumped)
        else:
            source = {
                "name": getattr(item, "name", ""),
                "description": getattr(item, "description", ""),
                "inputSchema": getattr(item, "inputSchema", getattr(item, "input_schema", {})),
            }
        name = str(source.get("name") or source.get("tool") or source.get("id") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        input_schema = (
            source.get("inputSchema")
            or source.get("input_schema")
            or source.get("schema")
            or source.get("parameters")
        )
        if not isinstance(input_schema, dict):
            input_schema = {}
        normalized.append(
            {
                "name": name,
                "description": str(source.get("description") or "").strip(),
                "inputSchema": dict(input_schema),
            }
        )
    return normalized


def _default_string_value(field_name: str, *, project_root: str, probe_file: str, probe_function: str) -> str:
    lowered = str(field_name or "").strip().lower()
    if "project" in lowered and "path" in lowered:
        return project_root
    if "root" in lowered and "path" in lowered:
        return project_root
    if "directory" in lowered:
        return "."
    if "file" in lowered and "path" in lowered:
        return probe_file
    if lowered == "path":
        return probe_file
    if "function" in lowered or "symbol" in lowered:
        return probe_function
    if "query" in lowered or "pattern" in lowered or "keyword" in lowered or "search" in lowered:
        return "runtime_verify"
    if "content" in lowered or "text" in lowered:
        return "runtime verify payload"
    if lowered.endswith("_id") or lowered == "id" or "doc_id" in lowered:
        return "__runtime_verify__"
    return "runtime_verify"


def _normalize_schema_type(schema: Dict[str, Any]) -> Optional[str]:
    type_value = schema.get("type")
    if isinstance(type_value, str) and type_value.strip():
        return type_value.strip().lower()
    if isinstance(type_value, list):
        for item in type_value:
            if isinstance(item, str) and item.strip() and item.strip().lower() != "null":
                return item.strip().lower()
    if isinstance(schema.get("properties"), dict):
        return "object"
    if schema.get("items") is not None:
        return "array"
    return None


def _schema_value(
    schema: Dict[str, Any],
    *,
    field_name: str,
    project_root: str,
    probe_file: str,
    probe_function: str,
    probe_line: int,
    depth: int = 0,
) -> Tuple[Any, Optional[str]]:
    if depth > 4:
        return None, "arg_generation_failed:max_depth"
    if not isinstance(schema, dict):
        return None, "arg_generation_failed:invalid_schema"
    if "default" in schema:
        return schema.get("default"), None
    if "const" in schema:
        return schema.get("const"), None
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0], None

    for variant_key in ("oneOf", "anyOf", "allOf"):
        variants = schema.get(variant_key)
        if isinstance(variants, list) and variants:
            last_error = "arg_generation_failed:variant_not_supported"
            has_none_candidate = False
            sorted_variants = sorted(
                variants,
                key=lambda item: (
                    1
                    if _normalize_schema_type(item if isinstance(item, dict) else {}) == "null"
                    else 0
                ),
            )
            for variant in sorted_variants:
                value, error = _schema_value(
                    variant if isinstance(variant, dict) else {},
                    field_name=field_name,
                    project_root=project_root,
                    probe_file=probe_file,
                    probe_function=probe_function,
                    probe_line=probe_line,
                    depth=depth + 1,
                )
                if error is None:
                    if value is None:
                        has_none_candidate = True
                        continue
                    return value, None
                last_error = error
            if has_none_candidate:
                return None, None
            return None, last_error

    schema_type = _normalize_schema_type(schema)
    if schema_type == "string":
        return _default_string_value(
            field_name,
            project_root=project_root,
            probe_file=probe_file,
            probe_function=probe_function,
        ), None
    if schema_type == "integer":
        lowered = str(field_name or "").lower()
        if "line" in lowered:
            return max(1, int(probe_line)), None
        minimum = schema.get("minimum")
        if isinstance(minimum, int):
            return minimum, None
        if isinstance(minimum, float):
            return int(minimum), None
        return 1, None
    if schema_type == "number":
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)):
            return float(minimum), None
        return 1.0, None
    if schema_type == "boolean":
        return False, None
    if schema_type == "null":
        return None, None
    if schema_type == "array":
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        item_value, item_error = _schema_value(
            item_schema,
            field_name=f"{field_name}_item",
            project_root=project_root,
            probe_file=probe_file,
            probe_function=probe_function,
            probe_line=probe_line,
            depth=depth + 1,
        )
        if item_error is not None:
            return [], None
        return [item_value], None
    if schema_type == "object":
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required_fields = [str(item) for item in schema.get("required", []) if isinstance(item, str)]
        payload: Dict[str, Any] = {}
        for req_key in required_fields:
            child_schema = properties.get(req_key) if isinstance(properties.get(req_key), dict) else {}
            child_value, child_error = _schema_value(
                child_schema,
                field_name=req_key,
                project_root=project_root,
                probe_file=probe_file,
                probe_function=probe_function,
                probe_line=probe_line,
                depth=depth + 1,
            )
            if child_error is not None:
                return None, f"arg_generation_failed:{req_key}:{child_error}"
            payload[req_key] = child_value
        for field, field_schema in properties.items():
            if field in payload or not isinstance(field_schema, dict):
                continue
            if not any(key in field_schema for key in ("default", "const", "enum")):
                continue
            child_value, child_error = _schema_value(
                field_schema,
                field_name=str(field),
                project_root=project_root,
                probe_file=probe_file,
                probe_function=probe_function,
                probe_line=probe_line,
                depth=depth + 1,
            )
            if child_error is None:
                payload[str(field)] = child_value
        return payload, None
    return None, "arg_generation_failed:unsupported_schema_type"


def _known_tool_args(
    *,
    adapter_id: str,
    tool_name: str,
    input_schema: Optional[Dict[str, Any]],
    project_root: str,
    filesystem_probe_file: str,
    filesystem_media_probe_file: str,
    qmd_probe_file: str = "",
    code_probe_file: str,
    code_probe_function: str,
    code_probe_line: int,
) -> Optional[Dict[str, Any]]:
    normalized_adapter = str(adapter_id or "").strip().lower()
    normalized_tool = str(tool_name or "").strip().lower()
    normalized_project_root = os.path.normpath(str(project_root or "").strip()) if str(project_root or "").strip() else ""

    def _abs_project_path(path_value: str) -> str:
        raw_path = str(path_value or "").strip()
        if not raw_path:
            return normalized_project_root
        if os.path.isabs(raw_path):
            return os.path.normpath(raw_path)
        if normalized_project_root:
            return os.path.normpath(os.path.join(normalized_project_root, raw_path))
        return os.path.normpath(raw_path)

    if normalized_tool == "set_project_path":
        return {
            "path": project_root,
            "project_path": project_root,
            "project_root": project_root,
            "directory": project_root,
            "root": project_root,
        }

    return None


def build_tool_args(
    *,
    adapter_id: str,
    tool_name: str,
    input_schema: Optional[Dict[str, Any]],
    project_root: str,
    filesystem_probe_file: str,
    filesystem_media_probe_file: str,
    qmd_probe_file: str = "",
    code_probe_file: str,
    code_probe_function: str,
    code_probe_line: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    known_args = _known_tool_args(
        adapter_id=adapter_id,
        tool_name=tool_name,
        input_schema=input_schema,
        project_root=project_root,
        filesystem_probe_file=filesystem_probe_file,
        filesystem_media_probe_file=filesystem_media_probe_file,
        qmd_probe_file=qmd_probe_file,
        code_probe_file=code_probe_file,
        code_probe_function=code_probe_function,
        code_probe_line=code_probe_line,
    )
    if known_args is not None:
        return known_args, None

    if not isinstance(input_schema, dict) or not input_schema:
        return None, "arg_generation_failed:missing_input_schema"

    schema_type = _normalize_schema_type(input_schema)
    if schema_type not in {None, "object"}:
        return None, f"arg_generation_failed:unsupported_root_type:{schema_type}"

    payload, error = _schema_value(
        input_schema,
        field_name=str(tool_name or "tool"),
        project_root=project_root,
        probe_file=filesystem_probe_file,
        probe_function=code_probe_function,
        probe_line=code_probe_line,
    )
    if error is not None:
        return None, error
    if isinstance(payload, dict):
        return payload, None
    if payload is None:
        return {}, None
    return None, "arg_generation_failed:invalid_generated_payload"


def _check_record(
    *,
    step: str,
    action: str,
    success: bool,
    duration_ms: int,
    tool: Optional[str] = None,
    runtime_domain: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "step": step,
        "action": action,
        "success": bool(success),
        "tool": tool,
        "runtime_domain": runtime_domain,
        "duration_ms": int(max(0, duration_ms)),
        "error": str(error or "").strip() or None,
    }


def _error_from_execution(result: ToolExecutionResult) -> str:
    error_text = str(result.error or "").strip()
    if error_text:
        return error_text
    metadata = dict(result.metadata or {})
    skip_reason = str(metadata.get("runtime_skip_reason") or "").strip()
    if skip_reason:
        return skip_reason
    if not result.handled:
        return "tool_not_handled"
    return "tool_failed"


def _is_filesystem_write_tool(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"write_file", "edit_file", "create_directory", "move_file", "delete_file"}:
        return True
    write_prefixes = ("write_", "edit_", "create_", "move_", "delete_")
    return normalized.startswith(write_prefixes)


async def run_protocol_verification(
    *,
    runtime: ToolRuntime,
    adapter_id: str,
    project_root: str,
    filesystem_probe_file: Optional[str] = None,
    filesystem_media_probe_file: Optional[str] = None,
    qmd_probe_file: Optional[str] = None,
    code_probe_file: Optional[str] = None,
    code_probe_function: Optional[str] = None,
    code_probe_line: Optional[int] = None,
) -> Dict[str, Any]:
    normalized_adapter = str(adapter_id or "").strip().lower()
    probe_file = str(filesystem_probe_file or "tmp/.runtime_verify_protocol_probe.txt").strip()
    probe_media_file = str(filesystem_media_probe_file or "tmp/.runtime_verify_protocol_probe.png").strip()
    probe_qmd_file = str(qmd_probe_file or "tmp/.runtime_verify_qmd_probe.md").strip()
    probe_code_file = str(code_probe_file or "tmp/.runtime_verify_code_probe.c").strip()
    probe_function = str(code_probe_function or "runtime_probe_sum").strip()
    probe_line = max(1, int(code_probe_line or 2))

    checks: List[Dict[str, Any]] = []
    runtime_domains: set[str] = set()

    list_started = time.perf_counter()
    list_result = await runtime.list_adapter_tools(normalized_adapter)
    list_duration = int((time.perf_counter() - list_started) * 1000)
    list_metadata = dict(list_result.get("metadata") or {}) if isinstance(list_result, dict) else {}
    list_runtime_domain = str(list_metadata.get("runtime_domain") or "").strip() or None
    if list_runtime_domain:
        runtime_domains.add(list_runtime_domain)
    list_tools_ok = bool(list_result.get("success")) if isinstance(list_result, dict) else False
    discovered_tools = normalize_listed_tools(list_result.get("tools") if isinstance(list_result, dict) else None)
    if list_tools_ok and not discovered_tools:
        list_tools_ok = False
    list_error = None if list_tools_ok else str((list_result or {}).get("error") or "tools_list_empty")
    checks.append(
        _check_record(
            step="tools_list",
            action="tools/list",
            success=list_tools_ok,
            tool="tools/list",
            runtime_domain=list_runtime_domain,
            duration_ms=list_duration,
            error=list_error,
        )
    )

    call_attempted_count = 0
    call_success_count = 0
    call_failed_count = 0
    arg_failed_count = 0
    skipped_unsupported_count = 0
    if list_tools_ok:
        for item in discovered_tools:
            tool_name = str(item.get("name") or "").strip()
            if normalized_adapter == "filesystem" and _is_filesystem_write_tool(tool_name):
                skipped_unsupported_count += 1
                checks.append(
                    _check_record(
                        step=f"tools_call::{tool_name}",
                        action="policy/skip",
                        success=True,
                        tool=tool_name,
                        duration_ms=0,
                        error="readonly_policy_skip",
                    )
                )
                continue

            input_schema = item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {}
            args, args_error = build_tool_args(
                adapter_id=normalized_adapter,
                tool_name=tool_name,
                input_schema=input_schema,
                project_root=project_root,
                filesystem_probe_file=probe_file,
                filesystem_media_probe_file=probe_media_file,
                qmd_probe_file=probe_qmd_file,
                code_probe_file=probe_code_file,
                code_probe_function=probe_function,
                code_probe_line=probe_line,
            )
            if args_error is not None or args is None:
                arg_failed_count += 1
                call_failed_count += 1
                checks.append(
                    _check_record(
                        step=f"tools_call::{tool_name}",
                        action="tools/call",
                        success=False,
                        tool=tool_name,
                        duration_ms=0,
                        error=args_error or "arg_generation_failed:unknown",
                    )
                )
                continue

            call_attempted_count += 1
            started = time.perf_counter()
            call_result = await runtime.call_adapter_tool(
                adapter_name=normalized_adapter,
                tool_name=tool_name,
                arguments=args,
                agent_name="runtime_verify",
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            metadata = dict(call_result.metadata or {})
            call_runtime_domain = str(metadata.get("runtime_domain") or "").strip() or None
            if call_runtime_domain:
                runtime_domains.add(call_runtime_domain)
            call_success = bool(call_result.handled and call_result.success)
            call_error = None if call_success else _error_from_execution(call_result)

            if call_success:
                call_success_count += 1
            else:
                call_failed_count += 1
            checks.append(
                _check_record(
                    step=f"tools_call::{tool_name}",
                    action="tools/call",
                    success=call_success,
                    tool=tool_name,
                    runtime_domain=call_runtime_domain,
                    duration_ms=duration_ms,
                    error=call_error,
                )
            )

    protocol_success = bool(list_tools_ok and call_failed_count == 0 and len(discovered_tools) > 0)
    verification_tools = [str(item.get("name") or "").strip() for item in discovered_tools if str(item.get("name") or "").strip()]
    protocol_summary = {
        "adapter_id": normalized_adapter,
        "list_tools_success": bool(list_tools_ok),
        "discovered_count": len(discovered_tools),
        "called_count": int(call_attempted_count),
        "call_success_count": int(call_success_count),
        "call_failed_count": int(call_failed_count),
        "arg_failed_count": int(arg_failed_count),
        "skipped_unsupported_count": int(skipped_unsupported_count),
        "runtime_domains": sorted(runtime_domains),
        "required_gate": list(getattr(runtime, "required_adapters", []) or []),
    }

    return {
        "success": protocol_success,
        "checks": checks,
        "verification_tools": verification_tools,
        "discovered_tools": discovered_tools,
        "protocol_summary": protocol_summary,
    }
