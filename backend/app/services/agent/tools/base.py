"""
Agent 工具基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from dataclasses import dataclass, field
import inspect
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
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
    
    def to_string(self, max_length: int = 5000) -> str:
        """转换为字符串（用于 LLM 输出）"""
        if not self.success:
            return f"Error: {self.error}"
        
        if isinstance(self.data, str):
            result = self.data
        elif isinstance(self.data, (dict, list)):
            import json
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
        """执行工具（带计时和日志）"""
        start_time = time.time()
        payload = dict(kwargs or {})
        filtered_kwargs, dropped_kwargs = self._filter_execute_kwargs(payload)
        
        try:
            logger.debug(f"Tool '{self.name}' executing with args: {filtered_kwargs}")
            result = await self._execute(**filtered_kwargs)
            
        except ValidationError as e:
            logger.warning(f"Tool '{self.name}' validation error: {e}")
            expected = self._build_expected_args()
            result = ToolResult(
                success=False,
                error="参数校验失败",
                data={
                    "message": str(e),
                    "expected_args": expected,
                },
            )
        except Exception as e:
            logger.error(f"Tool '{self.name}' error: {e}", exc_info=True)
            error_msg = str(e)
            result = ToolResult(
                success=False,
                data=f"工具执行异常: {error_msg}",  # 🔥 修复：设置 data 字段避免 None
                error=error_msg,
            )

        if dropped_kwargs:
            metadata = dict(result.metadata or {})
            metadata["dropped_kwargs"] = sorted(dropped_kwargs.keys())
            result.metadata = metadata
        
        duration_ms = int((time.time() - start_time) * 1000)
        result.duration_ms = duration_ms
        
        self._call_count += 1
        self._total_duration_ms += duration_ms
        
        logger.debug(f"Tool '{self.name}' completed in {duration_ms}ms, success={result.success}")
        
        return result

    def _build_expected_args(self) -> Optional[Dict[str, Any]]:
        schema = self.args_schema
        if not schema:
            return None
        expected: Dict[str, Any] = {}
        for name, field in schema.__fields__.items():
            if field.required and field.default is None and field.default_factory is None:
                type_name = getattr(field.outer_type_, "__name__", "value")
                expected[name] = f"<{type_name}>"
            elif field.default_factory is not None:
                try:
                    expected[name] = field.default_factory()
                except Exception:
                    expected[name] = None
            else:
                expected[name] = field.default
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
