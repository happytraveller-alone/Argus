from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Tuple

from fastapi import HTTPException

from app.services.agent.agents.skill_test import SkillTestAgent
from app.services.agent.event_manager import normalize_tool_output_envelope
from app.services.agent.skills.scan_core import (
    SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
    get_scan_core_skill_test_policy,
)
from app.services.agent.tools import (
    CodeWindowTool,
    ControlFlowAnalysisLightTool,
    DataFlowAnalysisTool,
    FileOutlineTool,
    FileSearchTool,
    FunctionSummaryTool,
    ListFilesTool,
    PatternMatchTool,
    QuickAuditTool,
    SmartScanTool,
    SymbolBodyTool,
)
from app.services.agent.tools.base import ToolResult
from app.services.agent.flow.flow_parser_runner import get_flow_parser_runner_client


def normalize_extracted_project_root(base_path: str) -> str:
    candidates = [
        item
        for item in os.listdir(base_path)
        if not str(item).startswith("__") and not str(item).startswith(".")
    ]
    if len(candidates) != 1:
        return base_path
    nested = os.path.join(base_path, candidates[0])
    if os.path.isdir(nested):
        return nested
    return base_path


_SUPPORTED_TOOL_BUILDERS = {
    "get_code_window": lambda project_root, llm_service: CodeWindowTool(project_root),
    "get_file_outline": lambda project_root, llm_service: FileOutlineTool(project_root),
    "get_function_summary": lambda project_root, llm_service: FunctionSummaryTool(project_root),
    "get_symbol_body": lambda project_root, llm_service: SymbolBodyTool(project_root),
    "list_files": lambda project_root, llm_service: ListFilesTool(project_root),
    "search_code": lambda project_root, llm_service: FileSearchTool(project_root),
    "pattern_match": lambda project_root, llm_service: PatternMatchTool(project_root),
    "smart_scan": lambda project_root, llm_service: SmartScanTool(project_root),
    "quick_audit": lambda project_root, llm_service: QuickAuditTool(project_root),
}


def build_skill_test_tool_allowlist(skill_id: str) -> Tuple[str, ...]:
    policy = get_scan_core_skill_test_policy(skill_id)
    if not bool(policy.get("test_supported")):
        raise HTTPException(
            status_code=400,
            detail=str(policy.get("test_reason") or "当前 skill 暂不支持测试"),
        )
    ordered = [str(skill_id or "").strip()]
    return tuple(item for item in ordered if item)


def build_skill_test_tools(skill_id: str, project_root: str, llm_service: Any) -> Dict[str, Any]:
    tools: Dict[str, Any] = {}
    for tool_name in build_skill_test_tool_allowlist(skill_id):
        builder = _SUPPORTED_TOOL_BUILDERS.get(tool_name)
        if builder is None:
            raise HTTPException(status_code=400, detail=f"当前 skill 暂未接入测试 runner: {tool_name}")
        tools[tool_name] = builder(project_root, llm_service)
    return tools


def build_structured_tool_test_tool(skill_id: str, project_root: str, llm_service: Any) -> Any:
    normalized = str(skill_id or "").strip()
    if normalized == "dataflow_analysis":
        return DataFlowAnalysisTool(llm_service=llm_service, project_root=project_root)
    if normalized == "controlflow_analysis_light":
        return ControlFlowAnalysisLightTool(project_root=project_root)
    raise HTTPException(status_code=400, detail=f"当前 skill 暂未接入结构化测试 runner: {normalized}")


def _extract_summary_from_tool_result(result: ToolResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    if metadata.get("summary"):
        return str(metadata["summary"])
    data = result.data
    if isinstance(data, dict):
        for key in ("summary", "message"):
            if data.get(key):
                return str(data[key])
    if isinstance(data, str) and data.strip():
        return data.strip()
    return result.to_string(max_length=800)


def _infer_language(file_path: str) -> str:
    suffix = Path(str(file_path or "")).suffix.lower()
    if suffix in {".c", ".h"}:
        return "c"
    if suffix in {".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"}:
        return "cpp"
    if suffix == ".py":
        return "python"
    return "text"


def _safe_relative_file_content(project_root: str, file_path: str) -> str:
    root = Path(project_root).resolve()
    candidate = (root / str(file_path or "")).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=400, detail=f"非法文件路径: {file_path}")
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail=f"目标文件不存在: {file_path}")
    return candidate.read_text(encoding="utf-8", errors="replace")


def _resolve_function_via_flow_parser_runner(
    *,
    project_root: str,
    file_path: str,
    function_name: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> Dict[str, Any]:
    normalized_file_path = str(file_path or "").replace("\\", "/").lstrip("./")
    normalized_function_name = str(function_name or "").strip()
    if not normalized_file_path or not normalized_function_name:
        raise HTTPException(status_code=400, detail="结构化工具测试必须提供 file_path 和 function_name")

    content = _safe_relative_file_content(project_root, normalized_file_path)
    runner_client = get_flow_parser_runner_client()
    runner_image = str(getattr(runner_client, "image", "") or "")
    payload = runner_client.extract_definitions_batch(
        [
            {
                "file_path": normalized_file_path,
                "language": _infer_language(normalized_file_path),
                "content": content,
            }
        ]
    )
    result = payload.get(normalized_file_path) if isinstance(payload, dict) else None
    if not isinstance(result, dict) or not bool(result.get("ok")):
        raise HTTPException(status_code=400, detail=f"flow parser runner 无法解析目标文件: {normalized_file_path}")

    diagnostics = list(result.get("diagnostics") or [])
    definitions = list(result.get("definitions") or [])
    matching_definition = None
    for item in definitions:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip() == normalized_function_name:
            matching_definition = item
            break
    if matching_definition is None:
        raise HTTPException(
            status_code=400,
            detail=f"flow parser runner 未在 {normalized_file_path} 中定位到函数: {normalized_function_name}",
        )

    start_point = matching_definition.get("start_point") or [0, 0]
    end_point = matching_definition.get("end_point") or start_point
    resolved_line_start = int(line_start) if line_start else int(start_point[0]) + 1
    resolved_line_end = int(line_end) if line_end else int(end_point[0]) + 1
    if resolved_line_end < resolved_line_start:
        resolved_line_end = resolved_line_start

    return {
        "runner_image": runner_image,
        "diagnostics": diagnostics,
        "file_path": normalized_file_path,
        "function_name": normalized_function_name,
        "line_start": resolved_line_start,
        "line_end": resolved_line_end,
    }


def _build_structured_tool_execution_payload(
    *,
    skill_id: str,
    request_payload: Dict[str, Any],
    resolution: Dict[str, Any],
) -> Dict[str, Any]:
    tool_input = dict(request_payload.get("tool_input") or {})
    normalized_skill_id = str(skill_id or "").strip()
    if normalized_skill_id == "dataflow_analysis":
        tool_input.setdefault("variable_name", "plist_xml")
        tool_input.setdefault("sink_hints", ["xmlReadMemory", "xmlParseMemory", "xml_to_node"])
        tool_input["file_path"] = resolution["file_path"]
        tool_input["start_line"] = resolution["line_start"]
        tool_input["end_line"] = resolution["line_end"]
        return tool_input
    if normalized_skill_id == "controlflow_analysis_light":
        tool_input.setdefault("vulnerability_type", "xxe")
        tool_input["file_path"] = resolution["file_path"]
        tool_input["function_name"] = resolution["function_name"]
        tool_input["line_start"] = resolution["line_start"]
        tool_input["line_end"] = resolution["line_end"]
        return tool_input
    raise HTTPException(status_code=400, detail=f"当前 skill 不支持结构化工具测试: {normalized_skill_id}")


class StructuredToolTestRunner:
    def __init__(
        self,
        *,
        skill_id: str,
        request_payload: Dict[str, Any],
        llm_service: Any | None = None,
        project_name: str,
        zip_path: str,
        fallback_used: bool,
        event_emitter: Any,
    ):
        self.skill_id = str(skill_id or "").strip()
        self.request_payload = dict(request_payload or {})
        self.llm_service = llm_service
        self.project_name = str(project_name or "").strip()
        self.zip_path = str(zip_path or "").strip()
        self.fallback_used = bool(fallback_used)
        self.event_emitter = event_emitter

    async def run(self) -> Dict[str, Any]:
        policy = get_scan_core_skill_test_policy(self.skill_id)
        if str(policy.get("test_mode") or "") != "structured_tool":
            raise HTTPException(status_code=400, detail="当前 skill 暂不支持结构化工具测试")

        project_name = self.project_name
        zip_path = self.zip_path
        if self.fallback_used or project_name != SCAN_CORE_DEFAULT_TEST_PROJECT_NAME:
            raise HTTPException(
                status_code=400,
                detail="未找到可用于技能测试的默认 libplist ZIP 项目，请先修复默认 libplist 资源。",
            )

        temp_dir = ""
        cleanup_success = True
        cleanup_error = None
        pending_error: Exception | None = None
        result_payload: Dict[str, Any] | None = None
        execution_payload: Dict[str, Any] | None = None
        tool_result_emitted = False

        await self.event_emitter.emit_event(
            "project_prepare",
            "默认测试项目命中 libplist",
            {
                "project_name": project_name,
                "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
                "zip_path": zip_path,
            },
        )

        try:
            temp_dir = tempfile.mkdtemp(prefix=f"structured-tool-test-{self.skill_id}-", dir="/tmp")
            await self.event_emitter.emit_event(
                "project_prepare",
                "临时目录已创建，开始解压测试项目",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                },
            )
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            project_root = normalize_extracted_project_root(temp_dir)
            await self.event_emitter.emit_event(
                "project_prepare",
                "测试项目准备完成",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                    "project_root": project_root,
                },
            )

            resolution = _resolve_function_via_flow_parser_runner(
                project_root=project_root,
                file_path=str(self.request_payload.get("file_path") or ""),
                function_name=str(self.request_payload.get("function_name") or ""),
                line_start=self.request_payload.get("line_start"),
                line_end=self.request_payload.get("line_end"),
            )
            await self.event_emitter.emit_event(
                "runner_prepare",
                "flow parser runner 已定位目标函数",
                {
                    "runner_image": resolution["runner_image"],
                    "resolved_file_path": resolution["file_path"],
                    "resolved_line_start": resolution["line_start"],
                    "resolved_line_end": resolution["line_end"],
                    "target_function": resolution["function_name"],
                    "diagnostics": resolution["diagnostics"],
                },
            )

            execution_payload = _build_structured_tool_execution_payload(
                skill_id=self.skill_id,
                request_payload=self.request_payload,
                resolution=resolution,
            )
            tool = build_structured_tool_test_tool(self.skill_id, project_root, self.llm_service)
            await self.event_emitter.emit(
                SimpleNamespace(
                    event_type="tool_call",
                    message=f"结构化测试调用 {self.skill_id}",
                    tool_name=self.skill_id,
                    tool_input=execution_payload,
                    tool_output=None,
                    metadata={},
                )
            )
            tool_result = await tool.execute(**execution_payload)
            tool_output = normalize_tool_output_envelope(
                {
                    "result": tool_result.to_string(max_length=800),
                    "truncated": False,
                    "metadata": dict(tool_result.metadata) if isinstance(tool_result.metadata, dict) else None,
                    "error": str(tool_result.error or "") or None,
                    "error_code": str(getattr(tool_result, "error_code", "") or "") or None,
                }
            )
            await self.event_emitter.emit(
                SimpleNamespace(
                    event_type="tool_result",
                    message=f"{self.skill_id} 执行完成" if tool_result.success else f"{self.skill_id} 执行失败",
                    tool_name=self.skill_id,
                    tool_input=execution_payload,
                    tool_output=tool_output,
                    metadata={},
                )
            )
            tool_result_emitted = True
            if not tool_result.success:
                raise RuntimeError(str(tool_result.error or f"{self.skill_id} 执行失败"))

            result_payload = {
                "skill_id": self.skill_id,
                "tool_name": self.skill_id,
                "final_text": _extract_summary_from_tool_result(tool_result),
                "project_name": project_name,
                "test_mode": "structured_tool",
                "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
                "project_root": project_root,
                "target_function": resolution["function_name"],
                "resolved_file_path": resolution["file_path"],
                "resolved_line_start": resolution["line_start"],
                "resolved_line_end": resolution["line_end"],
                "runner_image": resolution["runner_image"],
                "input_payload": {
                    "file_path": resolution["file_path"],
                    "function_name": resolution["function_name"],
                    "line_start": resolution["line_start"],
                    "line_end": resolution["line_end"],
                    "tool_input": dict(self.request_payload.get("tool_input") or {}),
                },
            }
        except Exception as exc:
            if execution_payload is not None and not tool_result_emitted:
                await self.event_emitter.emit(
                    SimpleNamespace(
                        event_type="tool_result",
                        message=f"{self.skill_id} 执行失败",
                        tool_name=self.skill_id,
                        tool_input=execution_payload,
                        tool_output=normalize_tool_output_envelope(
                            {
                                "result": str(exc),
                                "truncated": False,
                                "error": str(exc),
                                "error_code": type(exc).__name__,
                            }
                        ),
                        metadata={},
                    )
                )
            pending_error = exc
        finally:
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir)
                except Exception as exc:
                    cleanup_success = False
                    cleanup_error = str(exc)
            await self.event_emitter.emit_event(
                "project_cleanup",
                "临时目录清理完成" if cleanup_success else "临时目录清理失败",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                    "cleanup_success": cleanup_success,
                    "cleanup_error": cleanup_error,
                },
            )

        cleanup_payload = {
            "success": cleanup_success,
            "temp_dir": temp_dir,
            "error": cleanup_error,
        }
        if result_payload is not None:
            result_payload["cleanup"] = cleanup_payload
            return result_payload
        if pending_error is not None:
            raise pending_error
        raise RuntimeError("structured_tool_test_runner_failed_without_result")


class SkillTestRunner:
    def __init__(
        self,
        *,
        skill_id: str,
        prompt: str,
        max_iterations: int,
        llm_service: Any,
        project_name: str,
        zip_path: str,
        fallback_used: bool,
        event_emitter: Any,
    ):
        self.skill_id = str(skill_id or "").strip()
        self.prompt = str(prompt or "").strip()
        self.max_iterations = int(max_iterations or 4)
        self.llm_service = llm_service
        self.project_name = str(project_name or "").strip()
        self.zip_path = str(zip_path or "").strip()
        self.fallback_used = bool(fallback_used)
        self.event_emitter = event_emitter

    async def run(self) -> Dict[str, Any]:
        policy = get_scan_core_skill_test_policy(self.skill_id)
        if not bool(policy.get("test_supported")):
            raise HTTPException(
                status_code=400,
                detail=str(policy.get("test_reason") or "当前 skill 暂不支持测试"),
            )

        project_name = self.project_name
        zip_path = self.zip_path
        if self.fallback_used or project_name != SCAN_CORE_DEFAULT_TEST_PROJECT_NAME:
            raise HTTPException(
                status_code=400,
                detail="未找到可用于技能测试的默认 libplist ZIP 项目，请先修复默认 libplist 资源。",
            )

        temp_dir = ""
        cleanup_success = True
        cleanup_error = None
        pending_error: Exception | None = None
        result_payload: Dict[str, Any] | None = None

        await self.event_emitter.emit_event(
            "project_prepare",
            "默认测试项目命中 libplist",
            {
                "project_name": project_name,
                "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
                "zip_path": zip_path,
            },
        )

        try:
            temp_dir = tempfile.mkdtemp(prefix=f"skill-test-{self.skill_id}-", dir="/tmp")
            await self.event_emitter.emit_event(
                "project_prepare",
                "临时目录已创建，开始解压测试项目",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                },
            )
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            project_root = normalize_extracted_project_root(temp_dir)
            await self.event_emitter.emit_event(
                "project_prepare",
                "测试项目准备完成",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                    "project_root": project_root,
                },
            )

            tools = build_skill_test_tools(self.skill_id, project_root, self.llm_service)
            agent = SkillTestAgent(
                llm_service=self.llm_service,
                tools=tools,
                selected_skill_id=self.skill_id,
                max_iterations=self.max_iterations,
                event_emitter=self.event_emitter,
            )
            agent_result = await agent.run(
                {
                    "project_info": {
                        "name": project_name,
                        "root": project_root,
                    },
                    "task": self.prompt,
                }
            )
            final_text = _extract_final_text(agent_result)
            result_payload = {
                "skill_id": self.skill_id,
                "final_text": final_text,
                "project_name": project_name,
                "test_mode": str(policy.get("test_mode") or "single_skill_strict"),
                "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
                "project_root": project_root,
            }
        except Exception as exc:
            pending_error = exc
        finally:
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir)
                except Exception as exc:
                    cleanup_success = False
                    cleanup_error = str(exc)
            await self.event_emitter.emit_event(
                "project_cleanup",
                "临时目录清理完成" if cleanup_success else "临时目录清理失败",
                {
                    "project_name": project_name,
                    "temp_dir": temp_dir,
                    "cleanup_success": cleanup_success,
                    "cleanup_error": cleanup_error,
                },
            )

        cleanup_payload = {
            "success": cleanup_success,
            "temp_dir": temp_dir,
            "error": cleanup_error,
        }
        if result_payload is not None:
            result_payload["cleanup"] = cleanup_payload
            return result_payload
        if pending_error is not None:
            raise pending_error
        raise RuntimeError("skill_test_runner_failed_without_result")


def _extract_final_text(agent_result: Any) -> str:
    payload = getattr(agent_result, "data", agent_result)
    if isinstance(payload, dict):
        final_text = str(payload.get("final_text") or "").strip()
        if final_text:
            return final_text
    return str(payload or "测试完成，但未生成最终文本。")
