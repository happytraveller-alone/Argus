from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Dict

from ...push_finding_payload import normalize_push_finding_payload
from .context import ToolCallContext, ToolFailureState
from .contracts import ToolContractViolation


@dataclass
class ToolHookResult:
    continue_execution: bool = True
    normalized_input: Dict[str, Any] | None = None
    diagnostics_additions: list[str] = field(default_factory=list)
    error: str = ""
    error_code: str = ""
    reflection_request: Dict[str, Any] = field(default_factory=dict)


class ToolHook:
    async def pre_normalize(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        return ToolHookResult()

    async def pre_validate(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        return ToolHookResult()

    async def pre_policy(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        return ToolHookResult()

    async def post_execute(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        return ToolHookResult()

    async def post_validate(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        return ToolHookResult()

    async def post_format(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        return ToolHookResult()

    async def on_error(self, *, tool: Any, context: ToolCallContext, error: Exception) -> ToolHookResult:
        return ToolHookResult()

    async def on_reflect(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        return ToolHookResult()


class StrictUnknownFieldHook(ToolHook):
    async def on_error(self, *, tool: Any, context: ToolCallContext, error: Exception) -> ToolHookResult:
        if isinstance(error, ToolContractViolation) and error.error_code == "unknown_field":
            return ToolHookResult(
                continue_execution=False,
                error=str(error),
                error_code=error.error_code,
                diagnostics_additions=list(error.diagnostics),
            )
        return ToolHookResult()


class StableErrorCodeHook(ToolHook):
    @staticmethod
    def classify_message(error_text: str, existing_code: str = "") -> str:
        normalized_existing = str(existing_code or "").strip()
        if normalized_existing:
            return normalized_existing

        text = str(error_text or "").strip().lower()
        if any(token in text for token in ("未知字段", "unknown field")):
            return "unknown_field"
        if any(token in text for token in ("参数", "validation", "必填", "缺少")):
            return "invalid_input"
        if any(token in text for token in ("安全错误", "项目目录外", "越权", "不允许访问", "不在审计范围")):
            return "path_out_of_scope"
        if any(token in text for token in ("不支持", "unsupported", "language_disabled")):
            return "unsupported_language"
        if any(token in text for token in ("不存在", "无法定位", "not found", "missing_enclosing_function")):
            return "not_found"
        return "internal_error"

    async def on_error(self, *, tool: Any, context: ToolCallContext, error: Exception) -> ToolHookResult:
        if isinstance(error, ToolContractViolation):
            return ToolHookResult(
                continue_execution=False,
                error=str(error),
                error_code=error.error_code,
                diagnostics_additions=list(error.diagnostics),
            )
        return ToolHookResult(
            continue_execution=False,
            error=str(error),
            error_code="internal_error",
            diagnostics_additions=[f"internal_error:{type(error).__name__}"],
        )


class DiagnosticsEnvelopeHook(ToolHook):
    async def post_execute(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        metadata = dict(getattr(result, "metadata", {}) or {})
        diagnostics = list(getattr(result, "diagnostics", []) or [])
        metadata.setdefault("runtime_trace", {})
        metadata["runtime_trace"].update(
            {
                "tool_name": context.tool_name,
                "requested_tool_name": context.requested_tool_name,
                "phase": context.phase,
                "agent_type": context.agent_type,
            }
        )
        result.metadata = metadata
        result.diagnostics = diagnostics
        return ToolHookResult()


class ToolPresentationHook(ToolHook):
    async def post_format(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        if not getattr(result, "success", False):
            return ToolHookResult()
        metadata = dict(getattr(result, "metadata", {}) or {})
        metadata.setdefault("rendered_by_runtime", True)
        result.metadata = metadata
        return ToolHookResult()


class ProjectPathNormalizeHook(ToolHook):
    async def pre_normalize(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        payload = dict(context.normalized_input or context.raw_input or {})
        for key in ("file_path", "path", "directory"):
            value = payload.get(key)
            if isinstance(value, str):
                payload[key] = value.replace("\\", "/").strip()
        return ToolHookResult(normalized_input=payload)


class ProjectScopeGuardHook(ToolHook):
    async def pre_policy(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        payload = dict(context.validated_input or context.normalized_input or context.raw_input or {})
        project_root = str(getattr(tool, "project_root", "") or "").strip()
        if not project_root:
            return ToolHookResult()

        project_root = os.path.normpath(project_root)
        for key in ("file_path", "path", "directory"):
            raw_value = payload.get(key)
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            candidate = raw_value.replace("\\", "/").strip()
            if ":" in candidate and key in {"file_path", "path"}:
                head, tail = candidate.rsplit(":", 1)
                if tail.isdigit():
                    candidate = head
            full_path = (
                os.path.normpath(candidate)
                if os.path.isabs(candidate)
                else os.path.normpath(os.path.join(project_root, candidate))
            )
            try:
                within_scope = os.path.commonpath([full_path, project_root]) == project_root
            except Exception:
                within_scope = False
            if not within_scope:
                raise ToolContractViolation(
                    message="安全错误：不允许访问项目目录外的文件",
                    error_code="path_out_of_scope",
                    diagnostics=[f"path_out_of_scope:{key}"],
                )
        return ToolHookResult()


class EvidenceMetadataHook(ToolHook):
    async def post_execute(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        metadata = dict(getattr(result, "metadata", {}) or {})
        metadata.setdefault("tool_contract_version", "v2")
        result.metadata = metadata
        return ToolHookResult()


class AtomicReadPolicyHook(ToolHook):
    async def pre_policy(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        return ToolHookResult()


class ReasoningPreflightHook(ToolHook):
    async def pre_policy(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        policy = dict(context.runtime_policy or {})
        policy["reason_before_tool"] = {
            "tool_name": context.tool_name,
            "phase": context.phase,
            "candidate_input": dict(context.validated_input or context.normalized_input or context.raw_input or {}),
        }
        context.runtime_policy = policy
        return ToolHookResult()


class FailureReflectionHook(ToolHook):
    async def on_reflect(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        failure = context.failure_state or ToolFailureState()
        reflection = {
            "failure_class": "input_contract_violation"
            if failure.error_code in {"unknown_field", "invalid_input"}
            else "output_contract_violation"
            if failure.error_code == "output_contract_violation"
            else "tool_execution_failure",
            "root_cause": failure.error or "unknown",
            "retryable": failure.error_code == "internal_error",
            "retry_with": context.normalized_input or context.raw_input,
            "fallback_tool": None,
            "stop_reason": failure.error_code,
        }
        failure.reflection = reflection
        context.failure_state = failure
        return ToolHookResult(reflection_request=reflection)


class LocatorInputCanonicalizationHook(ToolHook):
    async def pre_normalize(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        payload = dict(context.normalized_input or context.raw_input or {})
        raw_path = payload.get("file_path") or payload.get("path")
        raw_line = payload.get("line")
        line_start = payload.get("line_start")
        if isinstance(raw_path, str) and ":" in raw_path:
            head, tail = raw_path.rsplit(":", 1)
            if tail.isdigit():
                payload["file_path"] = head
                if raw_line is None and line_start is None:
                    payload["line"] = int(tail)
        elif raw_path:
            payload["file_path"] = raw_path
        if line_start is not None:
            payload["line"] = line_start
        payload.pop("path", None)
        payload.pop("line_start", None)
        return ToolHookResult(normalized_input=payload)


class PushFindingInputCanonicalizationHook(ToolHook):
    async def pre_normalize(self, *, tool: Any, context: ToolCallContext) -> ToolHookResult:
        payload = dict(context.normalized_input or context.raw_input or {})
        normalized, _repair_map = normalize_push_finding_payload(payload)
        return ToolHookResult(normalized_input=normalized)


class LocatorOutputContractHook(ToolHook):
    async def post_validate(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        payload = getattr(result, "data", None)
        if not isinstance(payload, dict):
            return ToolHookResult()
        symbol = payload.get("symbol")
        if isinstance(symbol, dict) and symbol.get("return_type", "__missing__") == "__missing__":
            raise ToolContractViolation(
                message="symbol.return_type 字段缺失",
                error_code="output_contract_violation",
                diagnostics=["locator_return_type_missing"],
            )
        return ToolHookResult()


class LocatorConfidenceHook(ToolHook):
    async def post_validate(self, *, tool: Any, context: ToolCallContext, result: Any) -> ToolHookResult:
        payload = getattr(result, "data", None)
        if not isinstance(payload, dict):
            return ToolHookResult()
        resolution = payload.get("resolution")
        if not isinstance(resolution, dict):
            return ToolHookResult()
        confidence = resolution.get("confidence")
        try:
            numeric = float(confidence)
        except Exception as exc:
            raise ToolContractViolation(
                message=f"resolution.confidence 非法: {confidence!r}",
                error_code="output_contract_violation",
                diagnostics=["locator_confidence_not_numeric"],
            ) from exc
        if numeric < 0 or numeric > 1:
            raise ToolContractViolation(
                message=f"resolution.confidence 超出范围: {numeric}",
                error_code="output_contract_violation",
                diagnostics=["locator_confidence_out_of_range"],
            )
        return ToolHookResult()
