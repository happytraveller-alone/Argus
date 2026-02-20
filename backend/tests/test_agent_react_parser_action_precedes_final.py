from types import SimpleNamespace

import pytest

from app.services.agent.agents.analysis import AnalysisAgent
from app.services.agent.agents.recon import ReconAgent
from app.services.agent.agents.verification import VerificationAgent


def _make_recon_agent() -> ReconAgent:
    return ReconAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": object(), "search_code": object()},
        event_emitter=None,
    )


def _make_analysis_agent() -> AnalysisAgent:
    return AnalysisAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": object(), "search_code": object()},
        event_emitter=None,
    )


def _make_verification_agent() -> VerificationAgent:
    return VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": object(), "search_code": object()},
        event_emitter=None,
    )


@pytest.mark.parametrize(
    "agent_factory",
    [_make_recon_agent, _make_analysis_agent, _make_verification_agent],
)
def test_react_parser_action_precedes_final_answer(agent_factory):
    agent = agent_factory()
    response = """Thought: need evidence
Action: read_file
Action Input: {"file_path": "src/a.py", "start_line": 1, "end_line": 10}
Final Answer: {"findings": [], "summary": "should be ignored this round"}"""

    step = agent._parse_llm_response(response)

    assert step.action == "read_file"
    assert step.is_final is False
    assert isinstance(step.action_input, dict)
    assert step.action_input.get("file_path") == "src/a.py"


def test_react_parser_final_answer_when_no_action_present():
    agent = _make_analysis_agent()
    response = """Thought: done
Final Answer: {"findings": [], "summary": "ok"}"""

    step = agent._parse_llm_response(response)

    assert step.action is None
    assert step.is_final is True
    assert isinstance(step.final_answer, dict)
    assert step.final_answer.get("findings") == []


@pytest.mark.parametrize(
    "agent_factory",
    [_make_recon_agent, _make_analysis_agent, _make_verification_agent],
)
def test_react_parser_supports_markdown_action_sections(agent_factory):
    agent = agent_factory()
    response = """## Thought
need evidence

## Action
read_file

## Action Input
```json
{"file_path":"src/demo.py","start_line":1,"end_line":10}
```
"""
    step = agent._parse_llm_response(response)

    assert step.action == "read_file"
    assert isinstance(step.action_input, dict)
    assert step.action_input.get("file_path") == "src/demo.py"
    assert step.is_final is False
