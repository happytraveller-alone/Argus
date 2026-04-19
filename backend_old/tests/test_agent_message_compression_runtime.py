from types import SimpleNamespace

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


def _build_agent():
    return _DummyAgent(
        config=AgentConfig(name="CompressionAgent", agent_type=AgentType.RECON),
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=None,
    )


def _long_messages() -> list[dict[str, str]]:
    messages = [{"role": "system", "content": "系统提示" * 20}]
    for index in range(18):
        role = "user" if index % 2 == 0 else "assistant"
        messages.append({"role": role, "content": chr(65 + (index % 3)) * 120})
    return messages


def test_agent_token_estimate_uses_internal_heuristic():
    messages = [{"role": "user", "content": "hello world"}]
    assert BaseAgent._estimate_conversation_tokens(messages) > 0


def test_agent_compress_messages_if_needed_preserves_live_behavior():
    agent = _build_agent()
    messages = _long_messages()

    compressed = agent.compress_messages_if_needed(messages, max_tokens=40)

    assert compressed
    assert len(compressed) < len(messages)
    assert any(
        "<context_summary" in msg.get("content", "")
        for msg in compressed
        if msg.get("role") == "assistant"
    )
