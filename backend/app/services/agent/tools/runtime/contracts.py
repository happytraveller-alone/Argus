from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import ValidationError


@dataclass
class ToolContractViolation(Exception):
    message: str
    error_code: str
    diagnostics: list[str]

    def __str__(self) -> str:
        return self.message


class ToolInputContractRegistry:
    @staticmethod
    def allowed_fields(schema: Any) -> set[str]:
        if schema is None:
            return set()
        model_fields = getattr(schema, "model_fields", None)
        if isinstance(model_fields, dict):
            return {str(name) for name in model_fields.keys()}
        legacy_fields = getattr(schema, "__fields__", None)
        if isinstance(legacy_fields, dict):
            return {str(name) for name in legacy_fields.keys()}
        return set()

    @classmethod
    def validate_unknown_fields(cls, *, schema: Any, payload: Dict[str, Any]) -> None:
        allowed = cls.allowed_fields(schema)
        if not allowed:
            return
        unknown = sorted(str(key) for key in dict(payload or {}).keys() if str(key) not in allowed)
        if unknown:
            raise ToolContractViolation(
                message=f"发现未知字段: {', '.join(unknown)}",
                error_code="unknown_field",
                diagnostics=[f"unknown_fields:{','.join(unknown)}"],
            )

    @classmethod
    def validate_and_dump(cls, *, schema: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        if schema is None:
            return dict(payload or {})
        try:
            validated = schema(**dict(payload or {}))
        except ValidationError as exc:
            raise ToolContractViolation(
                message=str(exc),
                error_code="invalid_input",
                diagnostics=["pydantic_validation_failed"],
            ) from exc

        model_fields = getattr(type(validated), "model_fields", None)
        if isinstance(model_fields, dict):
            return {field_name: getattr(validated, field_name) for field_name in model_fields.keys()}

        legacy_fields = getattr(validated, "__fields__", None)
        if isinstance(legacy_fields, dict):
            return {field_name: getattr(validated, field_name) for field_name in legacy_fields.keys()}
        return dict(payload or {})


class ToolOutputContractRegistry:
    @staticmethod
    def _require_keys(payload: Dict[str, Any], keys: list[str]) -> None:
        missing = [key for key in keys if key not in payload]
        if missing:
            raise ToolContractViolation(
                message=f"缺少输出字段: {', '.join(missing)}",
                error_code="output_contract_violation",
                diagnostics=[f"missing_output_keys:{','.join(missing)}"],
            )

    @classmethod
    def validate(cls, *, tool_name: str, result: Any) -> None:
        if not getattr(result, "success", False):
            return
        if str(tool_name or "").strip().lower() != "locate_enclosing_function":
            return
        payload = getattr(result, "data", None)
        if not isinstance(payload, dict):
            raise ToolContractViolation(
                message="locate_enclosing_function 必须返回结构化对象",
                error_code="output_contract_violation",
                diagnostics=["locator_payload_not_dict"],
            )

        cls._require_keys(payload, ["file_path", "line", "language", "symbol", "resolution", "diagnostics"])
        symbol = payload.get("symbol")
        resolution = payload.get("resolution")
        if not isinstance(symbol, dict):
            raise ToolContractViolation(
                message="symbol 字段必须为对象",
                error_code="output_contract_violation",
                diagnostics=["locator_symbol_not_dict"],
            )
        if not isinstance(resolution, dict):
            raise ToolContractViolation(
                message="resolution 字段必须为对象",
                error_code="output_contract_violation",
                diagnostics=["locator_resolution_not_dict"],
            )
        cls._require_keys(
            symbol,
            ["kind", "name", "start_line", "end_line", "signature", "parameters", "return_type"],
        )
        cls._require_keys(resolution, ["method", "engine", "confidence", "degraded"])
        if not isinstance(payload.get("diagnostics"), list):
            raise ToolContractViolation(
                message="diagnostics 字段必须为数组",
                error_code="output_contract_violation",
                diagnostics=["locator_diagnostics_not_list"],
            )
        if not isinstance(symbol.get("parameters"), list):
            raise ToolContractViolation(
                message="symbol.parameters 字段必须为数组",
                error_code="output_contract_violation",
                diagnostics=["locator_parameters_not_list"],
            )
