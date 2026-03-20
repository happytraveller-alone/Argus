from __future__ import annotations

import shutil
import tempfile
import zipfile
from typing import Any, Dict, Tuple

from fastapi import HTTPException

from app.api.v1.endpoints.config import (
    _normalize_extracted_project_root,
    _resolve_verify_project,
)
from app.services.agent.agents.skill_test import SkillTestAgent
from app.services.agent.skills.scan_core import (
    SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
    get_scan_core_skill_test_policy,
)
from app.services.agent.tools import (
    CodeWindowTool,
    FileOutlineTool,
    FileSearchTool,
    FunctionSummaryTool,
    ListFilesTool,
    PatternMatchTool,
    QuickAuditTool,
    SmartScanTool,
    SymbolBodyTool,
)


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


class SkillTestRunner:
    def __init__(
        self,
        *,
        skill_id: str,
        prompt: str,
        max_iterations: int,
        llm_service: Any,
        db: Any,
        current_user: Any,
        event_emitter: Any,
    ):
        self.skill_id = str(skill_id or "").strip()
        self.prompt = str(prompt or "").strip()
        self.max_iterations = int(max_iterations or 4)
        self.llm_service = llm_service
        self.db = db
        self.current_user = current_user
        self.event_emitter = event_emitter

    async def run(self) -> Dict[str, Any]:
        policy = get_scan_core_skill_test_policy(self.skill_id)
        if not bool(policy.get("test_supported")):
            raise HTTPException(
                status_code=400,
                detail=str(policy.get("test_reason") or "当前 skill 暂不支持测试"),
            )

        project, zip_path, fallback_used = await _resolve_verify_project(
            db=self.db,
            current_user=self.current_user,
        )
        project_name = str(getattr(project, "name", "") or "").strip()
        if fallback_used or project_name != SCAN_CORE_DEFAULT_TEST_PROJECT_NAME:
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
            project_root = _normalize_extracted_project_root(temp_dir)
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
