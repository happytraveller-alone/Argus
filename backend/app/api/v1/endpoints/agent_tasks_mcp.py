"""MCP runtime helpers and tool documentation sync for agent tasks."""

import asyncio
import json
import logging
import os
import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent.mcp import (
    HARD_MAX_WRITABLE_FILES_PER_TASK,
    FastMCPStdioAdapter,
    MCPRuntime,
    TaskWriteScopeGuard,
)
from app.services.agent.mcp.health_probe import probe_mcp_endpoint_readiness
from app.services.agent.mcp.protocol_verify import (
    build_tool_args as build_mcp_probe_tool_args,
    normalize_listed_tools as normalize_mcp_listed_tools,
)

logger = logging.getLogger(__name__)

def _parse_mcp_args(raw_args: Any) -> List[str]:
    if isinstance(raw_args, list):
        return [str(item) for item in raw_args if str(item).strip()]
    text = str(raw_args or "").strip()
    if not text:
        return []
    try:
        return [str(item) for item in shlex.split(text) if str(item).strip()]
    except Exception:
        return [item for item in text.split(" ") if item]


def _extract_allowed_directories_from_payload(payload: Any) -> list[str]:
    candidate = payload
    if isinstance(candidate, str):
        stripped = candidate.strip()
        if stripped:
            try:
                candidate = json.loads(stripped)
            except Exception:
                normalized_text = stripped.replace("\\r\\n", "\n").replace("\\n", "\n")
                match = re.search(
                    r"allowed directories:\s*(.+)",
                    normalized_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if match:
                    raw_block = str(match.group(1) or "")
                    parsed_paths: list[str] = []
                    for raw_line in raw_block.splitlines():
                        cleaned = str(raw_line or "").strip().strip(",")
                        if not cleaned:
                            continue
                        if cleaned.startswith("/") or re.match(r"^[A-Za-z]:[\/]", cleaned):
                            cleaned = re.split(r"[\"'\}\)]", cleaned, maxsplit=1)[0].rstrip(",").strip()
                        if not cleaned:
                            continue
                        if os.path.isabs(cleaned) or re.match(r"^[A-Za-z]:[\/]", cleaned):
                            parsed_paths.append(cleaned)
                    if parsed_paths:
                        return list(dict.fromkeys(parsed_paths))
                candidate = stripped
    if isinstance(candidate, dict):
        for key in ("allowedDirectories", "allowed_directories", "directories", "paths"):
            value = candidate.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(candidate, list):
        return [str(item).strip() for item in candidate if str(item).strip()]
    return []


def _project_root_is_allowed(project_root: str, allowed_directories: List[str]) -> bool:
    project_root_text = str(project_root or "").strip()
    if not project_root_text:
        return False
    for item in allowed_directories:
        candidate = str(item or "").strip()
        if not candidate:
            continue
        normalized_candidate = candidate.rstrip(os.sep)
        if project_root_text == candidate or project_root_text.startswith(f"{normalized_candidate}{os.sep}"):
            return True
    return False


async def _run_task_llm_connection_test(
    *,
    llm_service: Any,
    event_emitter: Optional[Any] = None,
) -> Dict[str, Any]:
    if event_emitter:
        await event_emitter.emit_info(
            "🧪 正在测试 LLM 连接...",
            metadata={"step_name": "LLM_CONNECTION_TEST", "status": "running"},
        )
    started_at = time.perf_counter()
    response = await llm_service.chat_completion_raw(
        [{"role": "user", "content": "Say Hello in one word."}],
    )
    content = str(response.get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM 测试返回空响应")
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    usage = dict(response.get("usage") or {}) if isinstance(response, dict) else {}
    if event_emitter:
        await event_emitter.emit_info(
            f"LLM 连接测试通过 ({elapsed_ms}ms)",
            metadata={
                "step_name": "LLM_CONNECTION_TEST",
                "status": "completed",
                "elapsed_ms": elapsed_ms,
                "response_preview": content[:32],
                "usage": usage,
            },
        )
    return {"elapsed_ms": elapsed_ms, "response_preview": content[:32], "usage": usage}


async def _bootstrap_task_mcp_runtime(
    runtime: MCPRuntime,
    *,
    project_root: str,
    event_emitter: Optional[Any] = None,
) -> Dict[str, Any]:
    _ = runtime
    _ = project_root
    _ = event_emitter
    return {}


def _build_task_mcp_runtime(
    *,
    project_root: str,
    user_config: Optional[Dict[str, Any]],
    target_files: Optional[List[str]],
    bootstrap_findings: Optional[List[Dict[str, Any]]] = None,
    project_id: Optional[str] = None,
    prefer_stdio_when_http_unavailable: bool = False,
    active_mcp_ids: Optional[List[str]] = None,
    enforce_mcp_only: bool = False,
) -> MCPRuntime:
    from app.core.config import settings

    _ = project_id
    _ = prefer_stdio_when_http_unavailable

    normalized_project_root = os.path.abspath(project_root)

    _ = user_config
    write_policy: Dict[str, Any] = {}

    hard_limit = max(1, int(getattr(settings, "MCP_WRITE_HARD_LIMIT", HARD_MAX_WRITABLE_FILES_PER_TASK)))
    configured_max = write_policy.get(
        "max_writable_files_per_task",
        getattr(settings, "MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK", hard_limit),
    )
    try:
        max_writable_files = int(configured_max)
    except Exception:
        max_writable_files = int(getattr(settings, "MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK", hard_limit))
    max_writable_files = max(1, min(max_writable_files, hard_limit))

    write_guard = TaskWriteScopeGuard(
        project_root=normalized_project_root,
        max_writable_files_per_task=max_writable_files,
        require_evidence_binding=bool(
            write_policy.get(
                "require_evidence_binding",
                getattr(settings, "MCP_REQUIRE_EVIDENCE_BINDING", True),
            )
        ),
        forbid_project_wide_writes=True,
    )
    write_guard.seed_from_task_inputs(target_files=target_files, findings=bootstrap_findings or [])

    active_ids = {str(item).strip().lower() for item in (active_mcp_ids or []) if str(item).strip()}

    adapters: Dict[str, Any] = {}
    domain_adapters: Dict[str, Dict[str, Any]] = {}
    runtime_modes: Dict[str, str] = {}
    required_mcps: List[str] = []

    return MCPRuntime(
        enabled=bool(getattr(settings, "MCP_ENABLED", True)),
        prefer_mcp=(True if enforce_mcp_only else bool(getattr(settings, "MCP_PREFER", True))),
        adapters=adapters,
        domain_adapters=domain_adapters,
        runtime_modes=runtime_modes,
        required_mcps=required_mcps,
        write_scope_guard=write_guard,
        allow_filesystem_writes=False,
        default_runtime_mode="stdio_only",
        strict_mode=(True if enforce_mcp_only else bool(getattr(settings, "MCP_STRICT_MODE", True))),
        project_root=normalized_project_root,
    )


async def _probe_required_mcp_runtime(
    runtime: MCPRuntime,
    *,
    runtime_domain: str = "all",
) -> Dict[str, Any]:
    INTERNAL_TOOLS = {
        "set_project_path",
        "configure_file_watcher",
        "refresh_index",
        "build_deep_index",
    }
    WRITE_TOOL_PREFIXES = ("write", "edit", "create", "move", "delete")
    CALL_RETRY_COUNT = 2
    CALL_BACKOFF_SECONDS = 0.3

    def _prepare_probe_context() -> Dict[str, Any]:
        project_root = str(getattr(runtime, "project_root", "") or "").strip()
        if not project_root:
            return {
                "project_root": "",
                "filesystem_probe_file": "README.md",
                "filesystem_media_probe_file": "tmp/.mcp_required_media_probe.png",
                "code_probe_file": "tmp/.mcp_required_code_probe.c",
                "code_probe_function": "mcp_required_probe_sum",
                "code_probe_line": 2,
            }
        probe_dir = os.path.join(project_root, "tmp")
        os.makedirs(probe_dir, exist_ok=True)
        filesystem_probe_abs = os.path.join(probe_dir, ".mcp_required_filesystem_probe.txt")
        filesystem_media_abs = os.path.join(probe_dir, ".mcp_required_media_probe.png")
        code_probe_abs = os.path.join(probe_dir, ".mcp_required_code_probe.c")
        try:
            with open(filesystem_probe_abs, "w", encoding="utf-8") as handle:
                handle.write("mcp required filesystem probe\n")
        except Exception:
            pass
        try:
            with open(filesystem_media_abs, "wb") as handle:
                handle.write(b"PNG")
        except Exception:
            pass
        try:
            with open(code_probe_abs, "w", encoding="utf-8") as handle:
                handle.write(
                    "#include <stdio.h>\n"
                    "int mcp_required_probe_sum(int a, int b) {\n"
                    "    return a + b;\n"
                    "}\n"
                )
        except Exception:
            pass
        return {
            "project_root": project_root,
            "filesystem_probe_file": os.path.relpath(filesystem_probe_abs, project_root).replace("\\", "/"),
            "filesystem_media_probe_file": os.path.relpath(filesystem_media_abs, project_root).replace("\\", "/"),
            "code_probe_file": os.path.relpath(code_probe_abs, project_root).replace("\\", "/"),
            "code_probe_function": "mcp_required_probe_sum",
            "code_probe_line": 2,
        }

    def _is_write_tool(tool_name: str) -> bool:
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return True
        if normalized in INTERNAL_TOOLS:
            return True
        return normalized.startswith(WRITE_TOOL_PREFIXES)

    def _tool_priority(mcp_name: str, tool_name: str) -> int:
        normalized_mcp = str(mcp_name or "").strip().lower()
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return -999
        if _is_write_tool(normalized):
            return -500

        if normalized_mcp == "filesystem":
            filesystem_priority = {
                "list_allowed_directories": 1000,
                "read_file": 900,
                "read_text_file": 890,
                "search_files": 800,
                "list_directory": 700,
                "list_directory_with_sizes": 690,
                "directory_tree": 680,
                "get_file_info": 500,
            }
            return filesystem_priority.get(normalized, 0)

        score = 0
        if normalized.startswith(("search", "list", "read", "get", "status", "sequential")):
            score += 100
        if "summary" in normalized or "info" in normalized:
            score += 20
        if "media" in normalized:
            score -= 20
        return score

    def _extract_allowed_directories(payload: Any) -> list[str]:
        return _extract_allowed_directories_from_payload(payload)

    def _probe_failure_reason(
        *,
        mcp_name: str,
        tool_name: str,
        error_text: str,
        tool_args: dict[str, Any],
        project_root_value: str,
    ) -> tuple[str, str, Optional[str]]:
        normalized_mcp = str(mcp_name or "").strip().lower()
        normalized_error = str(error_text or "").strip()
        normalized_tool = str(tool_name or "").strip().lower()
        probe_path = None
        for key in ("path", "file_path", "directory", "source"):
            raw = tool_args.get(key)
            if isinstance(raw, str) and raw.strip():
                probe_path = raw.strip()
                break
        if probe_path and project_root_value and not os.path.isabs(probe_path):
            probe_path = os.path.normpath(os.path.join(project_root_value, probe_path))
        lowered_error = normalized_error.lower()
        if normalized_mcp == "filesystem" and "outside allowed directories" in lowered_error:
            return "filesystem_project_root_not_allowed", "filesystem_project_root_not_allowed", probe_path
        if normalized_mcp == "filesystem" and normalized_tool == "list_allowed_directories":
            return "filesystem_allowed_dirs_probe_failed", "filesystem_allowed_dirs_probe_failed", probe_path
        return normalized_error or "mcp_probe_call_failed", "mcp_probe_call_failed", probe_path

    required_mcps: List[str] = []
    if hasattr(runtime, "_required_mcp_names"):
        try:
            required_mcps = list(runtime._required_mcp_names())  # type: ignore[attr-defined]
        except Exception:
            required_mcps = []
    if not required_mcps:
        required_mcps = list(getattr(runtime, "required_mcps", []) or [])

    not_ready: List[Dict[str, Any]] = []
    details: Dict[str, Dict[str, Any]] = {}
    domain_value = str(runtime_domain or "all").strip().lower() or "all"
    probe_context = _prepare_probe_context()

    probe_runtime = runtime
    try:
        adapter_failure_threshold = max(
            6,
            int(getattr(runtime, "adapter_failure_threshold", 2) or 2) + 2,
        )
        probe_runtime = MCPRuntime(
            enabled=bool(getattr(runtime, "enabled", True)),
            prefer_mcp=bool(getattr(runtime, "prefer_mcp", True)),
            adapters=dict(getattr(runtime, "adapters", {}) or {}),
            domain_adapters=dict(getattr(runtime, "domain_adapters", {}) or {}),
            runtime_modes=dict(getattr(runtime, "runtime_modes", {}) or {}),
            required_mcps=list(getattr(runtime, "required_mcps", []) or []),
            write_scope_guard=getattr(runtime, "write_scope_guard", None),
            default_runtime_mode=str(
                getattr(runtime, "default_runtime_mode", "stdio_only")
                or "stdio_only"
            ),
            strict_mode=bool(getattr(runtime, "strict_mode", True)),
            adapter_failure_threshold=adapter_failure_threshold,
            project_root=probe_context.get("project_root"),
        )
    except Exception:
        probe_runtime = runtime

    for mcp_name in required_mcps:
        normalized_mcp = str(mcp_name or "").strip().lower()
        if not normalized_mcp:
            continue

        mcp_detail: Dict[str, Any] = {
            "probe_ready": False,
            "reason": "probe_not_started",
            "tools_list_success": False,
            "tools_call_success": False,
            "call_retry_count": CALL_RETRY_COUNT,
            "call_backoff_seconds": CALL_BACKOFF_SECONDS,
        }

        list_started = time.perf_counter()
        try:
            list_result = await probe_runtime.list_mcp_tools(normalized_mcp)
        except Exception as exc:
            list_result = {
                "success": False,
                "tools": [],
                "error": f"mcp_list_tools_failed:{exc}",
                "metadata": {},
            }
        list_duration_ms = int((time.perf_counter() - list_started) * 1000)

        list_metadata = list_result.get("metadata")
        if not isinstance(list_metadata, dict):
            list_metadata = {}
        list_runtime_domain = str(list_metadata.get("mcp_runtime_domain") or "").strip() or None
        discovered_tools = normalize_mcp_listed_tools(list_result.get("tools"))
        visible_tools = [
            tool
            for tool in discovered_tools
            if not _is_write_tool(str(tool.get("name") or ""))
        ]

        if not bool(list_result.get("success")):
            reason = str(list_result.get("error") or "mcp_tools_list_failed")
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "tools_list_success": False,
                    "tools_list_duration_ms": list_duration_ms,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/list",
                }
            )
            continue

        mcp_detail["tools_list_success"] = True
        mcp_detail["tools_list_duration_ms"] = list_duration_ms
        mcp_detail["discovered_tools"] = [str(item.get("name") or "") for item in discovered_tools]

        if not visible_tools:
            reason = "mcp_probe_tool_unavailable"
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/select",
                }
            )
            continue

        selected_tool = sorted(
            visible_tools,
            key=lambda item: _tool_priority(normalized_mcp, str(item.get("name") or "")),
            reverse=True,
        )[0]
        selected_tool_name = str(selected_tool.get("name") or "").strip()
        selected_input_schema = (
            dict(selected_tool.get("inputSchema"))
            if isinstance(selected_tool.get("inputSchema"), dict)
            else {}
        )

        tool_args, args_error = build_mcp_probe_tool_args(
            mcp_id=normalized_mcp,
            tool_name=selected_tool_name,
            input_schema=selected_input_schema,
            project_root=str(probe_context.get("project_root") or ""),
            filesystem_probe_file=str(probe_context.get("filesystem_probe_file") or "README.md"),
            filesystem_media_probe_file=str(
                probe_context.get("filesystem_media_probe_file") or "tmp/.mcp_required_media_probe.png"
            ),
            code_probe_file=str(probe_context.get("code_probe_file") or "tmp/.mcp_required_code_probe.c"),
            code_probe_function=str(probe_context.get("code_probe_function") or "mcp_required_probe_sum"),
            code_probe_line=int(probe_context.get("code_probe_line") or 2),
        )
        if args_error is not None or not isinstance(tool_args, dict):
            reason = str(args_error or "mcp_probe_arg_generation_failed")
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "selected_tool": selected_tool_name,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/call",
                    "tool_name": selected_tool_name,
                }
            )
            continue

        total_attempts = 1 + int(CALL_RETRY_COUNT)
        last_error = "mcp_probe_call_failed"
        last_reason_class = "mcp_probe_call_failed"
        last_probe_path = None
        last_allowed_directories: list[str] = []
        last_runtime_domain = list_runtime_domain
        call_ok = False
        for attempt in range(1, total_attempts + 1):
            call_started = time.perf_counter()
            try:
                call_result = await probe_runtime.call_mcp_tool(
                    mcp_name=normalized_mcp,
                    tool_name=selected_tool_name,
                    arguments=dict(tool_args),
                    agent_name="MCP_RUNTIME_PROBE",
                    alias_used=f"startup_probe:{selected_tool_name}",
                )
            except Exception as exc:
                call_result = None
                call_duration_ms = int((time.perf_counter() - call_started) * 1000)
                last_error = f"mcp_call_exception:{exc.__class__.__name__}"
                last_reason_class = "mcp_call_exception"
                mcp_detail["tools_call_duration_ms"] = call_duration_ms
                if attempt < total_attempts:
                    await asyncio.sleep(CALL_BACKOFF_SECONDS)
                    continue
                break

            call_duration_ms = int((time.perf_counter() - call_started) * 1000)
            call_metadata = dict(call_result.metadata) if isinstance(call_result.metadata, dict) else {}
            call_runtime_domain = str(call_metadata.get("mcp_runtime_domain") or "").strip() or list_runtime_domain
            last_runtime_domain = call_runtime_domain
            call_data = call_result.data
            if normalized_mcp == "filesystem" and selected_tool_name == "list_allowed_directories" and bool(call_result.handled and call_result.success):
                allowed_directories = _extract_allowed_directories(call_data)
                last_allowed_directories = allowed_directories
                project_root_text = str(probe_context.get("project_root") or "").strip()
                project_allowed = any(
                    project_root_text == item or project_root_text.startswith(f"{item.rstrip(os.sep)}{os.sep}")
                    for item in allowed_directories
                )
                if not project_allowed:
                    last_error = "filesystem_project_root_not_allowed"
                    last_reason_class = "filesystem_project_root_not_allowed"
                    last_probe_path = project_root_text
                    mcp_detail.update(
                        {
                            "tools_call_duration_ms": call_duration_ms,
                            "selected_tool": selected_tool_name,
                            "mcp_runtime_domain": call_runtime_domain,
                            "attempt": attempt,
                            "max_attempts": total_attempts,
                            "project_root": project_root_text,
                            "allowed_directories": allowed_directories,
                            "probe_path": project_root_text,
                        }
                    )
                    if attempt < total_attempts:
                        await asyncio.sleep(CALL_BACKOFF_SECONDS)
                        continue
                else:
                    mcp_detail.update(
                        {
                            "allowed_directories": allowed_directories,
                            "project_root": project_root_text,
                            "probe_path": project_root_text,
                        }
                    )
            if bool(call_result.handled and call_result.success) and not (last_reason_class == "filesystem_project_root_not_allowed"):
                mcp_detail.update(
                    {
                        "probe_ready": True,
                        "reason": "probe_ok",
                        "reason_class": "probe_ok",
                        "tools_call_success": True,
                        "tools_call_duration_ms": call_duration_ms,
                        "selected_tool": selected_tool_name,
                        "mcp_runtime_domain": call_runtime_domain,
                        "attempt": attempt,
                        "max_attempts": total_attempts,
                        "probe_path": last_probe_path or (tool_args.get("path") if isinstance(tool_args.get("path"), str) else None),
                        "project_root": str(probe_context.get("project_root") or "").strip() or None,
                        "allowed_directories": last_allowed_directories,
                    }
                )
                call_ok = True
                break

            classified_reason, classified_reason_class, classified_probe_path = _probe_failure_reason(
                mcp_name=normalized_mcp,
                tool_name=selected_tool_name,
                error_text=str(call_result.error or "mcp_call_failed"),
                tool_args=dict(tool_args),
                project_root_value=str(probe_context.get("project_root") or ""),
            )
            last_error = classified_reason
            last_reason_class = classified_reason_class
            last_probe_path = classified_probe_path
            mcp_detail.update(
                {
                    "tools_call_duration_ms": call_duration_ms,
                    "selected_tool": selected_tool_name,
                    "mcp_runtime_domain": call_runtime_domain,
                    "attempt": attempt,
                    "max_attempts": total_attempts,
                    "probe_path": classified_probe_path,
                    "project_root": str(probe_context.get("project_root") or "").strip() or None,
                    "allowed_directories": last_allowed_directories,
                    "reason_class": classified_reason_class,
                    "raw_reason": str(call_result.error or "mcp_call_failed"),
                }
            )
            if attempt < total_attempts:
                await asyncio.sleep(CALL_BACKOFF_SECONDS)

        if call_ok:
            details[normalized_mcp] = mcp_detail
            continue

        mcp_detail.update(
            {
                "probe_ready": False,
                "reason": last_error,
                "reason_class": last_reason_class,
                "tools_call_success": False,
                "probe_path": last_probe_path,
                "project_root": str(probe_context.get("project_root") or "").strip() or None,
                "allowed_directories": last_allowed_directories,
            }
        )
        details[normalized_mcp] = mcp_detail
        not_ready.append(
            {
                "mcp": normalized_mcp,
                "runtime_domain": last_runtime_domain or domain_value,
                "reason": last_error,
                "reason_class": last_reason_class,
                "step": "tools/call",
                "tool_name": selected_tool_name,
                "probe_path": last_probe_path,
            }
        )

    return {
        "ready": len(not_ready) == 0,
        "runtime_domain": domain_value,
        "required_mcps": required_mcps,
        "not_ready": not_ready,
        "details": details,
    }

def _sync_tool_catalog_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    """同步共享工具目录到 Markdown memory shared.md（追加式，保留历史）。"""
    catalog_path = Path(__file__).resolve().parents[4] / "docs" / "agent-tools" / "TOOL_SHARED_CATALOG.md"
    if not catalog_path.exists():
        return

    try:
        content = catalog_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read catalog failed: %s", exc)
        return

    clipped = content[: max(0, int(max_chars))]
    if not clipped.strip():
        return

    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="tool_catalog_sync",
            title="工具共享目录同步",
            summary="将 TOOL_SHARED_CATALOG.md 摘要同步到 shared memory，供各 Agent 提示词检出。",
            payload={
                "catalog_path": str(catalog_path),
                "max_chars": int(max_chars),
                "content": clipped,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append shared entry failed: %s", exc)


def _load_mcp_tool_playbook(*, max_chars: int) -> Tuple[Optional[Path], str]:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    playbook_path = docs_root / "MCP_TOOL_PLAYBOOK.md"
    if not playbook_path.exists():
        return None, ""
    try:
        content = playbook_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read MCP tool playbook failed: %s", exc)
        return playbook_path, ""
    clipped = content[: max(0, int(max_chars))]
    return playbook_path, clipped


def _sync_mcp_tool_playbook_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    playbook_path, playbook_content = _load_mcp_tool_playbook(max_chars=max_chars)
    if not playbook_path or not playbook_content.strip():
        return
    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="mcp_tool_playbook_sync",
            title="MCP 工具说明同步",
            summary="将 MCP_TOOL_PLAYBOOK.md 同步到 shared memory，供各 Agent 快速检索标准工具调用方式。",
            payload={
                "playbook_path": str(playbook_path),
                "max_chars": int(max_chars),
                "content": playbook_content,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append MCP playbook failed: %s", exc)


def _build_tool_skills_snapshot(*, max_chars: int) -> str:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    index_path = docs_root / "SKILLS_INDEX.md"
    skills_dir = docs_root / "skills"
    preferred_skill_order = [
        "mcp_reliability_workflow.skill.md",
        "push_finding_to_queue.skill.md",
        "get_recon_risk_queue_status.skill.md",
        "search_code.skill.md",
        "list_files.skill.md",
        "get_code_window.skill.md",
        "get_file_outline.skill.md",
        "get_function_summary.skill.md",
        "get_symbol_body.skill.md",
        "locate_enclosing_function.skill.md",
        "function_context.skill.md",
    ]

    fragments: List[str] = []
    if index_path.exists():
        try:
            fragments.append(index_path.read_text(encoding="utf-8", errors="replace").strip())
        except Exception as exc:
            logger.warning("[ToolDocSync] read skills index failed: %s", exc)

    if skills_dir.exists():
        all_skill_docs = {doc.name: doc for doc in skills_dir.glob("*.skill.md")}
        ordered_skill_docs: List[Path] = []
        for preferred_name in preferred_skill_order:
            preferred_doc = all_skill_docs.pop(preferred_name, None)
            if preferred_doc is not None:
                ordered_skill_docs.append(preferred_doc)
        ordered_skill_docs.extend(all_skill_docs[name] for name in sorted(all_skill_docs.keys()))

        for skill_doc in ordered_skill_docs:
            try:
                fragments.append(skill_doc.read_text(encoding="utf-8", errors="replace").strip())
            except Exception as exc:
                logger.warning("[ToolDocSync] read skill doc failed (%s): %s", skill_doc, exc)

    _playbook_path, playbook_content = _load_mcp_tool_playbook(max_chars=max_chars)
    if playbook_content.strip():
        fragments.append(playbook_content.strip())

    snapshot = "\n\n---\n\n".join(item for item in fragments if str(item or "").strip())
    if not snapshot.strip():
        return ""
    return snapshot[: max(0, int(max_chars))]


def _sync_tool_skills_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    skill_snapshot = _build_tool_skills_snapshot(max_chars=max_chars)
    if not skill_snapshot:
        return

    if hasattr(memory_store, "write_skills_snapshot"):
        try:
            memory_store.write_skills_snapshot(
                skill_snapshot,
                source="tool_skill_sync",
                task_id=task_id,
            )
            return
        except Exception as exc:
            logger.warning("[ToolDocSync] write skills snapshot failed: %s", exc)

    # Backward-compatible fallback.
    try:
        memory_store.append_entry(
            "skills",
            task_id=task_id,
            source="tool_skill_sync",
            title="工具 skill 规范同步",
            summary="将文件读取相关 skill 文档同步到 skills memory。",
            payload={"content": skill_snapshot},
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append skills entry failed: %s", exc)


__all__ = [name for name in globals() if not name.startswith("__")]
