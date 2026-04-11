import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import skills as skills_module
from app.services.agent.skills.prompt_skills import PROMPT_SKILL_AGENT_KEYS


@pytest.mark.asyncio
async def test_prompt_skills_crud_and_scope_filter(db, test_user):
    created_global = await skills_module.create_prompt_skill(
        request=skills_module.PromptSkillCreateRequest(
            name="global-skill",
            content="global content",
            scope="global",
            is_active=True,
        ),
        db=db,
        current_user=test_user,
    )
    created_agent = await skills_module.create_prompt_skill(
        request=skills_module.PromptSkillCreateRequest(
            name="analysis-only",
            content="analysis content",
            scope="agent_specific",
            agent_key="analysis",
            is_active=True,
        ),
        db=db,
        current_user=test_user,
    )

    all_rows = await skills_module.list_prompt_skills(
        scope=None,
        agent_key=None,
        is_active=None,
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )
    assert all_rows.total == 2
    assert {item.id for item in all_rows.items} == {created_global.id, created_agent.id}

    agent_rows = await skills_module.list_prompt_skills(
        scope="agent_specific",
        agent_key="analysis",
        is_active=None,
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )
    assert agent_rows.total == 1
    assert agent_rows.items[0].id == created_agent.id
    assert agent_rows.items[0].scope == "agent_specific"
    assert agent_rows.items[0].agent_key == "analysis"

    updated = await skills_module.update_prompt_skill(
        prompt_skill_id=created_agent.id,
        request=skills_module.PromptSkillUpdateRequest(
            scope="global",
            is_active=False,
        ),
        db=db,
        current_user=test_user,
    )
    assert updated.scope == "global"
    assert updated.agent_key is None
    assert updated.is_active is False

    deleted = await skills_module.delete_prompt_skill(
        prompt_skill_id=created_global.id,
        db=db,
        current_user=test_user,
    )
    assert deleted["id"] == created_global.id

    remaining = await skills_module.list_prompt_skills(
        scope=None,
        agent_key=None,
        is_active=None,
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )
    assert remaining.total == 1
    assert remaining.items[0].id == created_agent.id


@pytest.mark.asyncio
async def test_prompt_skills_builtin_toggle_and_list(db, test_user):
    initial = await skills_module.list_prompt_skills(
        scope=None,
        agent_key=None,
        is_active=None,
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )
    assert len(initial.builtin_items) == len(PROMPT_SKILL_AGENT_KEYS)
    assert all(item.is_active is True for item in initial.builtin_items)

    updated = await skills_module.update_builtin_prompt_skill(
        agent_key="analysis",
        request=skills_module.PromptSkillBuiltinUpdateRequest(is_active=False),
        db=db,
        current_user=test_user,
    )
    assert updated.agent_key == "analysis"
    assert updated.is_active is False

    refreshed = await skills_module.list_prompt_skills(
        scope=None,
        agent_key=None,
        is_active=None,
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )
    builtins = {item.agent_key: item for item in refreshed.builtin_items}
    assert builtins["analysis"].is_active is False
    assert builtins["recon"].is_active is True


@pytest.mark.asyncio
async def test_prompt_skills_reject_invalid_or_empty_payload(db, test_user):
    with pytest.raises(HTTPException) as invalid_scope:
        await skills_module.create_prompt_skill(
            request=skills_module.PromptSkillCreateRequest(
                name="bad",
                content="bad",
                scope="agent_specific",
                agent_key=None,
            ),
            db=db,
            current_user=test_user,
        )
    assert invalid_scope.value.status_code == 400

    with pytest.raises(HTTPException) as invalid_builtin_agent_key:
        await skills_module.update_builtin_prompt_skill(
            agent_key="unknown",
            request=skills_module.PromptSkillBuiltinUpdateRequest(is_active=False),
            db=db,
            current_user=test_user,
        )
    assert invalid_builtin_agent_key.value.status_code == 400

    with pytest.raises(HTTPException) as blank_name:
        await skills_module.create_prompt_skill(
            request=skills_module.PromptSkillCreateRequest(
                name="   ",
                content="has content",
                scope="global",
            ),
            db=db,
            current_user=test_user,
        )
    assert blank_name.value.status_code == 400
    assert "name" in str(blank_name.value.detail)

    created = await skills_module.create_prompt_skill(
        request=skills_module.PromptSkillCreateRequest(
            name="normal",
            content="normal",
            scope="global",
        ),
        db=db,
        current_user=test_user,
    )

    with pytest.raises(HTTPException) as blank_content:
        await skills_module.update_prompt_skill(
            prompt_skill_id=created.id,
            request=skills_module.PromptSkillUpdateRequest(content="   "),
            db=db,
            current_user=test_user,
        )
    assert blank_content.value.status_code == 400
    assert "content" in str(blank_content.value.detail)
