"""
Agent 工具基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from dataclasses import dataclass, field
import copy
import inspect
import json
from pydantic import BaseModel, ValidationError
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "diagnostics": self.diagnostics,
        }
    
    def to_string(self, max_length: int = 5000) -> str:
        """转换为字符串（用于 LLM 输出）"""
        if not self.success:
            return f"Error: {self.error}"
        
        if isinstance(self.data, str):
            result = self.data
        elif isinstance(self.data, (dict, list)):
            result = json.dumps(self.data, ensure_ascii=False, indent=2)
        else:
            result = str(self.data)
        
        if len(result) > max_length:
            result = result[:max_length] + f"\n... (truncated, total {len(result)} chars)"
        
        return result


class AgentTool(ABC):
    """
    Agent 工具基类
    所有工具需要继承此类并实现必要的方法
    """
    
    def __init__(self):
        self._call_count = 0
        self._total_duration_ms = 0
        self._runtime_context: Dict[str, Any] = {}
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（用于 Agent 理解工具功能）"""
        pass
    
    @property
    def args_schema(self) -> Optional[Type[BaseModel]]:
        """参数 Schema（Pydantic 模型）"""
        return None
    
    @abstractmethod
    async def _execute(self, **kwargs) -> ToolResult:
        """执行工具（子类实现）"""
        pass

    def _filter_execute_kwargs(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Filter kwargs according to concrete _execute signature for defensive compatibility."""
        try:
            signature = inspect.signature(self._execute)
        except Exception:
            return dict(payload or {}), {}

        parameters = list(signature.parameters.values())
        accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters)
        if accepts_var_kwargs:
            return dict(payload or {}), {}

        allowed_keys = {
            str(param.name)
            for param in parameters
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            and str(param.name) != "self"
        }
        if not allowed_keys:
            return {}, dict(payload or {})

        filtered: Dict[str, Any] = {}
        dropped: Dict[str, Any] = {}
        for key, value in dict(payload or {}).items():
            if str(key) in allowed_keys:
                filtered[str(key)] = value
            else:
                dropped[str(key)] = value
        return filtered, dropped
    
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具（统一交给运行时协调器处理）"""
        from .runtime import ToolExecutionCoordinator

        payload = dict(kwargs or {})
        logger.debug("Tool '%s' executing with args: %s", self.name, payload)
        coordinator = ToolExecutionCoordinator()
        result = await coordinator.execute(self, payload)
        self._call_count += 1
        self._total_duration_ms += int(result.duration_ms or 0)
        logger.debug("Tool '%s' completed in %sms, success=%s", self.name, result.duration_ms, result.success)
        return result

    def set_runtime_context(self, **kwargs) -> None:
        self._runtime_context = dict(kwargs or {})

    def clear_runtime_context(self) -> None:
        self._runtime_context = {}

    def clone_for_worker(self) -> "AgentTool":
        """
        生成 worker 专用工具实例，避免并发任务共享同一可变状态。

        默认策略使用浅拷贝并重置运行时计数/上下文；
        具体工具可按需覆写该方法补充自定义状态重置。
        """
        cloned = copy.copy(self)
        cloned._call_count = 0
        cloned._total_duration_ms = 0
        cloned._runtime_context = {}
        return cloned

    def _build_expected_args(self) -> Optional[Dict[str, Any]]:
        """构建预期参数字典，兼容 Pydantic v1 和 v2"""
        schema = self.args_schema
        if not schema:
            return None
        expected: Dict[str, Any] = {}
        
        # 尝试 Pydantic v2 的 model_fields
        model_fields = getattr(schema, "model_fields", None)
        if isinstance(model_fields, dict):
            # 导入 PydanticUndefined 来检查字段是否有默认值
            try:
                from pydantic_core import PydanticUndefined
            except ImportError:
                PydanticUndefined = None
            
            for name, field_info in model_fields.items():
                # 检查是否为必填字段（Pydantic v2）
                is_required = False
                checker = getattr(field_info, "is_required", None)
                if callable(checker):
                    try:
                        is_required = bool(checker())
                    except Exception:
                        is_required = False
                elif isinstance(checker, bool):
                    is_required = checker
                
                # 获取默认值
                default_val = getattr(field_info, "default", None)
                default_factory = getattr(field_info, "default_factory", None)
                
                # 检查 default_val 是否为 PydanticUndefined
                has_default = True
                if PydanticUndefined is not None and default_val is PydanticUndefined:
                    has_default = False
                    default_val = None
                elif default_val is None and default_factory is None:
                    has_default = False
                
                if is_required and not has_default:
                    # 必填字段且无默认值
                    annotation = getattr(field_info, "annotation", None)
                    type_name = getattr(annotation, "__name__", None) or str(annotation)
                    expected[name] = f"<{type_name}>"
                elif default_factory is not None:
                    try:
                        expected[name] = default_factory()
                    except Exception:
                        expected[name] = None
                else:
                    expected[name] = default_val
            return expected
        
        # 回退到 Pydantic v1 的 __fields__
        legacy_fields = getattr(schema, "__fields__", None)
        if isinstance(legacy_fields, dict):
            for name, field in legacy_fields.items():
                is_required = bool(getattr(field, "required", False))
                default_val = getattr(field, "default", None)
                default_factory = getattr(field, "default_factory", None)
                
                if is_required and default_val is None and default_factory is None:
                    type_name = getattr(field.outer_type_, "__name__", "value")
                    expected[name] = f"<{type_name}>"
                elif default_factory is not None:
                    try:
                        expected[name] = default_factory()
                    except Exception:
                        expected[name] = None
                else:
                    expected[name] = default_val
        
        return expected
    
    def get_langchain_tool(self):
        """转换为 LangChain Tool"""
        from langchain.tools import Tool, StructuredTool
        import asyncio
        
        def sync_wrapper(**kwargs):
            """同步包装器"""
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.execute(**kwargs))
                    result = future.result()
            else:
                result = asyncio.run(self.execute(**kwargs))
            return result.to_string()
        
        async def async_wrapper(**kwargs):
            """异步包装器"""
            result = await self.execute(**kwargs)
            return result.to_string()
        
        if self.args_schema:
            return StructuredTool(
                name=self.name,
                description=self.description,
                func=sync_wrapper,
                coroutine=async_wrapper,
                args_schema=self.args_schema,
            )
        else:
            return Tool(
                name=self.name,
                description=self.description,
                func=lambda x: sync_wrapper(query=x),
                coroutine=lambda x: async_wrapper(query=x),
            )
    
    @property
    def stats(self) -> Dict[str, Any]:
        """工具使用统计"""
        return {
            "name": self.name,
            "call_count": self._call_count,
            "total_duration_ms": self._total_duration_ms,
            "avg_duration_ms": self._total_duration_ms // max(1, self._call_count),
        }
