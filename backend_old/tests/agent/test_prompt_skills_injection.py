import pytest

from app.services.agent.agents.analysis import AnalysisAgent
from app.services.agent.agents.business_logic_analysis import BusinessLogicAnalysisAgent
from app.services.agent.agents.business_logic_recon import BusinessLogicReconAgent
from app.services.agent.agents.recon import ReconAgent
from app.services.agent.agents.verification import VerificationAgent


PROMPT_SKILLS_FIXTURE = {
    "recon": "fixture recon prompt skill",
    "business_logic_recon": "fixture business logic recon prompt skill",
    "analysis": "fixture analysis prompt skill",
    "business_logic_analysis": "fixture business logic analysis prompt skill",
    "verification": "fixture verification prompt skill",
}


def _build_config(enabled: bool) -> dict:
    return {
        "use_prompt_skills": enabled,
        "prompt_skills": dict(PROMPT_SKILLS_FIXTURE) if enabled else {},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_key", "enabled"),
    [
        ("recon", True),
        ("recon", False),
        ("business_logic_recon", True),
        ("business_logic_recon", False),
        ("analysis", True),
        ("analysis", False),
        ("business_logic_analysis", True),
        ("business_logic_analysis", False),
        ("verification", True),
        ("verification", False),
    ],
)
async def test_agents_inject_prompt_skill_section_toggle(
    agent_key,
    enabled,
    mock_llm_service,
    mock_event_emitter,
    temp_project_dir,
):
    config = _build_config(enabled)

    if agent_key == "recon":
        agent = ReconAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)
        await agent.run(
            {
                "project_info": {"name": "demo", "root": temp_project_dir, "file_count": 1},
                "config": config,
            }
        )
    elif agent_key == "business_logic_recon":
        agent = BusinessLogicReconAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)
        await agent.run(
            {
                "project_info": {"name": "demo", "root": temp_project_dir, "file_count": 1},
                "project_root": temp_project_dir,
                "config": config,
            }
        )
    elif agent_key == "analysis":
        agent = AnalysisAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)
        analysis_config = dict(config)
        analysis_config["single_risk_mode"] = False
        await agent.run(
            {
                "project_info": {"name": "demo", "root": temp_project_dir, "file_count": 1},
                "config": analysis_config,
                "previous_results": {"recon": {"data": {"high_risk_areas": []}}},
            }
        )
    elif agent_key == "business_logic_analysis":
        agent = BusinessLogicAnalysisAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)
        await agent.run(
            {
                "risk_point": {
                    "file_path": "src/demo.py",
                    "line_start": 10,
                    "description": "demo",
                    "vulnerability_type": "idor",
                    "severity": "high",
                },
                "config": config,
            }
        )
    elif agent_key == "verification":
        agent = VerificationAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)
        await agent.run(
            {
                "config": config,
                "previous_results": {
                    "findings": [
                        {
                            "title": "demo finding",
                            "vulnerability_type": "sql_injection",
                            "severity": "high",
                            "file_path": "src/demo.py",
                            "line_start": 12,
                            "description": "demo",
                        }
                    ]
                },
            }
        )
    else:
        raise AssertionError(f"Unexpected agent key: {agent_key}")

    assert agent._conversation_history
    initial_message = str(agent._conversation_history[1].get("content") or "")
    prompt_section_header = f"## Prompt Skill（{agent_key}）"
    if enabled:
        assert prompt_section_header in initial_message
        assert config["prompt_skills"][agent_key] in initial_message
    else:
        assert prompt_section_header not in initial_message


@pytest.mark.asyncio
async def test_recon_initial_prompt_includes_queue_and_coverage_requirements(
    mock_llm_service,
    mock_event_emitter,
    temp_project_dir,
):
    agent = ReconAgent(mock_llm_service, tools={}, event_emitter=mock_event_emitter)

    await agent.run(
        {
            "project_info": {"name": "demo", "root": temp_project_dir, "file_count": 1},
            "config": _build_config(False),
        }
    )

    assert agent._conversation_history
    initial_message = str(agent._conversation_history[1].get("content") or "")

    assert "## 本轮侦查硬性目标" in initial_message
    assert "如果当前还没有任何风险点入队，继续扩大覆盖面，而不是直接结束" in initial_message
    assert "## 最低覆盖清单" in initial_message
    assert "Webhook/Callback/OAuth/第三方集成" in initial_message
    assert "## 结束前自检" in initial_message
    assert "Final Answer 里除了总结，还要明确列出高风险区域、初步发现、风险点、coverage_summary" in initial_message
