"""
VulHunter Agent 服务模块

对外保持原有导出名，但改为懒加载，避免轻量模块在导入时触发整条
agent/runtime/docker 依赖链。
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "EventManager": ".event_manager",
    "AgentEventEmitter": ".event_manager",
    "BaseAgent": ".agents",
    "AgentConfig": ".agents",
    "AgentResult": ".agents",
    "OrchestratorAgent": ".agents",
    "ReconAgent": ".agents",
    "AnalysisAgent": ".agents",
    "VerificationAgent": ".agents",
    "AgentState": ".core",
    "AgentStatus": ".core",
    "AgentRegistry": ".core",
    "agent_registry": ".core",
    "AgentMessage": ".core",
    "MessageType": ".core",
    "MessagePriority": ".core",
    "MessageBus": ".core",
    "KnowledgeLoader": ".knowledge",
    "knowledge_loader": ".knowledge",
    "get_available_modules": ".knowledge",
    "get_module_content": ".knowledge",
    "SecurityKnowledgeRAG": ".knowledge",
    "security_knowledge_rag": ".knowledge",
    "SecurityKnowledgeQueryTool": ".knowledge",
    "GetVulnerabilityKnowledgeTool": ".knowledge",
    "CreateVulnerabilityReportTool": ".tools",
    "FinishScanTool": ".tools",
    "CreateSubAgentTool": ".tools",
    "SendMessageTool": ".tools",
    "ViewAgentGraphTool": ".tools",
    "WaitForMessageTool": ".tools",
    "AgentFinishTool": ".tools",
    "Tracer": ".telemetry",
    "get_global_tracer": ".telemetry",
    "set_global_tracer": ".telemetry",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value

