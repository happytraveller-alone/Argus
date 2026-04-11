from __future__ import annotations

import copy
import logging
import time
import uuid
from typing import Any, Dict, Iterable, List

from .context import ToolCallContext, ToolFailureState
from .contracts import ToolContractViolation, ToolInputContractRegistry, ToolOutputContractRegistry
from .hooks import (
    AtomicReadPolicyHook,
    DiagnosticsEnvelopeHook,
    EvidenceMetadataHook,
    FailureReflectionHook,
    LocatorConfidenceHook,
    LocatorInputCanonicalizationHook,
    LocatorOutputContractHook,
    PushFindingInputCanonicalizationHook,
    ProjectPathNormalizeHook,
    ProjectScopeGuardHook,
    ReasoningPreflightHook,
    StableErrorCodeHook,
    StrictUnknownFieldHook,
    ToolHook,
    ToolHookResult,
    ToolPresentationHook,
)

logger = logging.getLogger(__name__)


class ToolExecutionCoordinator:
    def __init__(self) -> None:
        self._global_hooks: List[ToolHook] = [
            ProjectPathNormalizeHook(),
            StrictUnknownFieldHook(),
            StableErrorCodeHook(),
            DiagnosticsEnvelopeHook(),
            ReasoningPreflightHook(),
            ToolPresentationHook(),
            FailureReflectionHook(),
        ]
        self._family_hooks: Dict[str, List[ToolHook]] = {
            "code_lookup": [
                ProjectScopeGuardHook(),
                EvidenceMetadataHook(),
                AtomicReadPolicyHook(),
            ],
            "reasoning": [],
        }
        self._tool_hooks: Dict[str, List[ToolHook]] = {
            "locate_enclosing_function": [
                LocatorInputCanonicalizationHook(),
                LocatorOutputContractHook(),
                LocatorConfidenceHook(),
            ],
            "push_finding_to_queue": [
                PushFindingInputCanonicalizationHook(),
            ],
        }

    def _tool_family(self, tool_name: str) -> str:
        if str(tool_name or "").strip().lower() in {
            "list_files",
            "search_code",
            "get_code_window",
            "get_file_outline",
            "get_function_summary",
            "get_symbol_body",
            "locate_enclosing_function",
        }:
            return "code_lookup"
        return "reasoning"

    def _hooks_for(self, tool_name: str) -> Iterable[ToolHook]:
        family = self._tool_family(tool_name)
        return [
            *self._global_hooks,
            *self._family_hooks.get(family, []),
            *self._tool_hooks.get(str(tool_name or "").strip().lower(), []),
        ]

    @staticmethod
    def _expected_args(tool: Any) -> Dict[str, Any] | None:
        builder = getattr(tool, "_build_expected_args", None)
        if callable(builder):
            return builder()
        return None

    def _failure_result(
        self,
        *,
        tool: Any,
        started_at: float,
        error: str,
        error_code: str,
        diagnostics: list[str] | None = None,
        data: Any = None,
        metadata: Dict[str, Any] | None = None,
    ):
        from ..base import ToolResult

        result = ToolResult(
            success=False,
            error=error,
            error_code=error_code,
            data=data,
            metadata=dict(metadata or {}),
            diagnostics=list(diagnostics or []),
        )
        result.duration_ms = int((time.time() - started_at) * 1000)
        return result

    @staticmethod
    def _clone_payload(value: Any) -> Any:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    @staticmethod
    def _payload_changed(before: Any, after: Any) -> bool:
        try:
            return before != after
        except Exception:
            return False

    @staticmethod
    def _raise_for_stage_rejection(stage: str, outputs: List[ToolHookResult]) -> None:
        for item in outputs:
            if item.continue_execution:
                continue
            if item.error_code or item.error:
                raise ToolContractViolation(
                    message=item.error or f"hook 在 {stage} 阶段拒绝执行",
                    error_code=item.error_code or "policy_blocked",
                    diagnostics=list(item.diagnostics_additions),
                )

    @staticmethod
    def _enforce_payload_stability(stage: str, before_payload: Any, result: Any) -> None:
        if ToolExecutionCoordinator._payload_changed(before_payload, getattr(result, "data", None)):
            raise ToolContractViolation(
                message=f"{stage} hook 不允许修改已生成 payload",
                error_code="output_contract_violation",
                diagnostics=[f"payload_mutated:{stage}"],
            )

    async def _reflect_failed_result(
        self,
        *,
        tool: Any,
        context: ToolCallContext,
        result: Any,
    ) -> Any:
        error_text = str(getattr(result, "error", "") or "工具执行失败")
        error_code = StableErrorCodeHook.classify_message(
            error_text,
            str(getattr(result, "error_code", "") or ""),
        )
        diagnostics = list(getattr(result, "diagnostics", []) or [])
        context.failure_state = ToolFailureState(
            error=error_text,
            error_code=error_code,
            diagnostics=diagnostics,
        )
        await self._apply_stage("on_reflect", tool=tool, context=context)
        reflection = (
            dict(context.failure_state.reflection)
            if context.failure_state and isinstance(context.failure_state.reflection, dict)
            else {}
        )
        result.error = error_text
        result.error_code = error_code
        result.diagnostics = diagnostics
        metadata = dict(getattr(result, "metadata", {}) or {})
        metadata["reflection"] = reflection
        metadata.setdefault("runtime_trace", {})
        metadata["runtime_trace"].update(
            {
                "tool_name": context.tool_name,
                "requested_tool_name": context.requested_tool_name,
                "phase": context.phase,
                "agent_type": context.agent_type,
            }
        )
        metadata.setdefault("reasoning_preflight", context.runtime_policy.get("reason_before_tool"))
        result.metadata = metadata
        return result

    async def _apply_stage(
        self,
        stage: str,
        *,
        tool: Any,
        context: ToolCallContext,
        result: Any = None,
        error: Exception | None = None,
    ) -> List[ToolHookResult]:
        outputs: List[ToolHookResult] = []
        for hook in self._hooks_for(context.tool_name):
            method = getattr(hook, stage)
            hook_result = await method(
                tool=tool,
                context=context,
                **({"result": result} if result is not None and stage.startswith("post_") else {}),
                **({"error": error} if error is not None and stage == "on_error" else {}),
            )
            outputs.append(hook_result)
            if hook_result.normalized_input is not None:
                context.normalized_input = dict(hook_result.normalized_input)
            if hook_result.diagnostics_additions:
                if context.failure_state is None:
                    context.failure_state = ToolFailureState()
                context.failure_state.diagnostics.extend(hook_result.diagnostics_additions)
            if not hook_result.continue_execution:
                break
        return outputs

    async def execute(self, tool: Any, payload: Dict[str, Any]) -> Any:
        from ..base import ToolResult

        started_at = time.time()
        runtime_context = getattr(tool, "_runtime_context", None) or {}
        context = ToolCallContext(
            tool_name=str(getattr(tool, "name", "") or ""),
            requested_tool_name=str(runtime_context.get("requested_tool_name") or getattr(tool, "name", "") or ""),
            phase=str(runtime_context.get("phase") or ""),
            agent_type=str(runtime_context.get("agent_type") or ""),
            raw_input=dict(payload or {}),
            normalized_input=dict(payload or {}),
            attempt=int(runtime_context.get("attempt") or 1),
            caller=str(runtime_context.get("caller") or ""),
            trace_id=str(runtime_context.get("trace_id") or uuid.uuid4()),
            runtime_policy=dict(runtime_context.get("runtime_policy") or {}),
        )

        try:
            pre_normalize_outputs = await self._apply_stage("pre_normalize", tool=tool, context=context)
            self._raise_for_stage_rejection("pre_normalize", pre_normalize_outputs)
            ToolInputContractRegistry.validate_unknown_fields(schema=getattr(tool, "args_schema", None), payload=context.normalized_input)
            pre_validate_outputs = await self._apply_stage("pre_validate", tool=tool, context=context)
            self._raise_for_stage_rejection("pre_validate", pre_validate_outputs)
            context.validated_input = ToolInputContractRegistry.validate_and_dump(
                schema=getattr(tool, "args_schema", None),
                payload=context.normalized_input,
            )
            pre_policy_outputs = await self._apply_stage("pre_policy", tool=tool, context=context)
            self._raise_for_stage_rejection("pre_policy", pre_policy_outputs)

            result = await tool._execute(**context.validated_input)
            if not isinstance(result, ToolResult):
                raise ToolContractViolation(
                    message="工具必须返回 ToolResult",
                    error_code="output_contract_violation",
                    diagnostics=["tool_result_type_invalid"],
                )

            payload_after_execute = self._clone_payload(getattr(result, "data", None))
            post_execute_outputs = await self._apply_stage("post_execute", tool=tool, context=context, result=result)
            self._raise_for_stage_rejection("post_execute", post_execute_outputs)
            self._enforce_payload_stability("post_execute", payload_after_execute, result)
            if not result.success:
                result = await self._reflect_failed_result(tool=tool, context=context, result=result)
                result.duration_ms = int((time.time() - started_at) * 1000)
                return result
            ToolOutputContractRegistry.validate(tool_name=context.tool_name, result=result)
            payload_after_validate = self._clone_payload(getattr(result, "data", None))
            post_validate_outputs = await self._apply_stage("post_validate", tool=tool, context=context, result=result)
            self._raise_for_stage_rejection("post_validate", post_validate_outputs)
            self._enforce_payload_stability("post_validate", payload_after_validate, result)
            payload_after_format = self._clone_payload(getattr(result, "data", None))
            post_format_outputs = await self._apply_stage("post_format", tool=tool, context=context, result=result)
            self._raise_for_stage_rejection("post_format", post_format_outputs)
            self._enforce_payload_stability("post_format", payload_after_format, result)

            result.error_code = None if result.success else (result.error_code or "internal_error")
            result.diagnostics = list(getattr(result, "diagnostics", []) or [])
            metadata = dict(getattr(result, "metadata", {}) or {})
            metadata.setdefault("reasoning_preflight", context.runtime_policy.get("reason_before_tool"))
            result.metadata = metadata
            result.duration_ms = int((time.time() - started_at) * 1000)
            return result
        except Exception as exc:
            logger.debug("tool runtime failure: %s", exc, exc_info=True)
            on_error_outputs = await self._apply_stage("on_error", tool=tool, context=context, error=exc)
            error_code = "internal_error"
            error_text = str(exc)
            diagnostics: list[str] = []
            for item in on_error_outputs:
                if item.error_code:
                    error_code = item.error_code
                if item.error:
                    error_text = item.error
                diagnostics.extend(item.diagnostics_additions)
            context.failure_state = ToolFailureState(
                error=error_text,
                error_code=error_code,
                diagnostics=diagnostics,
            )
            await self._apply_stage("on_reflect", tool=tool, context=context)
            reflection = (
                dict(context.failure_state.reflection)
                if context.failure_state and isinstance(context.failure_state.reflection, dict)
                else {}
            )
            metadata = {
                "reflection": reflection,
                "runtime_trace": {
                    "tool_name": context.tool_name,
                    "requested_tool_name": context.requested_tool_name,
                    "phase": context.phase,
                    "agent_type": context.agent_type,
                },
            }
            expected = self._expected_args(tool)
            data = {"message": error_text}
            if expected is not None and error_code in {"unknown_field", "invalid_input"}:
                data["expected_args"] = expected
            if error_code == "output_contract_violation":
                return self._failure_result(
                    tool=tool,
                    started_at=started_at,
                    error="输出校验失败",
                    error_code=error_code,
                    diagnostics=diagnostics,
                    data=data,
                    metadata=metadata,
                )
            return self._failure_result(
                tool=tool,
                started_at=started_at,
                error="参数校验失败" if error_code in {"unknown_field", "invalid_input"} else error_text,
                error_code=error_code,
                diagnostics=diagnostics,
                data=data,
                metadata=metadata,
            )
