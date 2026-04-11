from types import SimpleNamespace

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


def _make_agent(tool_timeout=60):
    llm_service = SimpleNamespace(
        get_agent_timeout_config=lambda: {
            "tool_timeout": tool_timeout,
            "llm_first_token_timeout": 90,
            "llm_stream_timeout": 60,
            "agent_timeout": 1800,
            "sub_agent_timeout": 600,
        }
    )
    return _DummyAgent(
        config=AgentConfig(name="timeout-agent", agent_type=AgentType.ANALYSIS),
        llm_service=llm_service,
        tools={},
        event_emitter=SimpleNamespace(emit=None),
    )


def test_resolve_tool_timeout_keeps_default_for_normal_tools():
    agent = _make_agent(tool_timeout=42)

    assert agent._resolve_tool_timeout("search_code") == 42


def test_resolve_tool_timeout_extends_dataflow_analysis_budget():
    agent = _make_agent(tool_timeout=60)

    assert agent._resolve_tool_timeout("dataflow_analysis") == 150


def test_resolve_tool_timeout_keeps_default_for_unknown_verifier():
    agent = _make_agent(tool_timeout=60)

    assert agent._resolve_tool_timeout("legacy_deep_verifier") == 60
