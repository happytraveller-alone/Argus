from app.services.agent.skills.prompt_skills import (
    DEFAULT_PROMPT_SKILL_TEMPLATES,
    PROMPT_SKILL_AGENT_KEYS,
    build_effective_prompt_skills,
)


def test_prompt_skill_templates_cover_all_five_agents():
    assert len(PROMPT_SKILL_AGENT_KEYS) == 5
    assert set(PROMPT_SKILL_AGENT_KEYS) == {
        "recon",
        "business_logic_recon",
        "analysis",
        "business_logic_analysis",
        "verification",
    }
    assert set(DEFAULT_PROMPT_SKILL_TEMPLATES.keys()) == set(PROMPT_SKILL_AGENT_KEYS)


def test_build_effective_prompt_skills_toggle():
    assert build_effective_prompt_skills(False) == {}

    enabled = build_effective_prompt_skills(True)
    assert set(enabled.keys()) == set(PROMPT_SKILL_AGENT_KEYS)
    for value in enabled.values():
        assert isinstance(value, str)
        assert value.strip()
