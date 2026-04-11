from app.services.agent.skills.prompt_skills import (
    DEFAULT_PROMPT_SKILL_TEMPLATES,
    PROMPT_SKILL_AGENT_KEYS,
    PROMPT_SKILL_SCOPE_AGENT_SPECIFIC,
    PROMPT_SKILL_SCOPE_GLOBAL,
    apply_prompt_skill_builtin_state,
    build_effective_prompt_skills,
    build_prompt_skill_builtin_state,
    merge_prompt_skills_with_custom,
    resolve_prompt_skill_scope_agent_key,
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


def test_build_prompt_skill_builtin_state_defaults_all_enabled():
    state = build_prompt_skill_builtin_state(None)
    assert set(state.keys()) == set(PROMPT_SKILL_AGENT_KEYS)
    assert all(state[key] is True for key in PROMPT_SKILL_AGENT_KEYS)



def test_apply_prompt_skill_builtin_state_filters_disabled_keys():
    base = build_effective_prompt_skills(True)
    filtered = apply_prompt_skill_builtin_state(
        base_prompt_skills=base,
        builtin_state={"analysis": False, "verification": True},
    )
    assert "analysis" not in filtered
    assert "recon" in filtered
    assert "verification" in filtered


def test_resolve_prompt_skill_scope_agent_key():
    scope, agent_key = resolve_prompt_skill_scope_agent_key("global", "analysis")
    assert scope == PROMPT_SKILL_SCOPE_GLOBAL
    assert agent_key is None

    scope, agent_key = resolve_prompt_skill_scope_agent_key("agent_specific", "analysis")
    assert scope == PROMPT_SKILL_SCOPE_AGENT_SPECIFIC
    assert agent_key == "analysis"



def test_merge_prompt_skills_with_custom_applies_global_and_agent_specific():
    base = build_effective_prompt_skills(True)
    merged = merge_prompt_skills_with_custom(
        base_prompt_skills=base,
        custom_prompt_skills=[
            {
                "name": "global-context",
                "content": "all agents should output code evidence first.",
                "scope": "global",
                "agent_key": None,
                "is_active": True,
            },
            {
                "name": "analysis-context",
                "content": "analysis phase must locate source input first.",
                "scope": "agent_specific",
                "agent_key": "analysis",
                "is_active": True,
            },
        ],
    )

    assert "[global-context] all agents should output code evidence first." in merged["recon"]
    assert "[global-context] all agents should output code evidence first." in merged["analysis"]
    assert "[analysis-context] analysis phase must locate source input first." in merged["analysis"]
    assert "[analysis-context] analysis phase must locate source input first." not in merged["verification"]
