from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import skills as skills_module
from app.models.user import User
from app.utils.security import get_password_hash


@pytest.mark.asyncio
async def test_skill_catalog_endpoint_returns_scan_core_items():
    response = await skills_module.get_skill_catalog(
        q="scan",
        namespace="scan-core",
        limit=50,
        offset=0,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.total >= 1
    skill_ids = {item.skill_id for item in response.items}
    assert "smart_scan" in skill_ids or "quick_audit" in skill_ids
    assert all(item.namespace == "scan-core" for item in response.items)


@pytest.mark.asyncio
async def test_skill_detail_endpoint_returns_static_scan_core_detail():
    response = await skills_module.get_skill_detail(
        skill_id="smart_scan",
        include_workflow=True,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.skill_id == "smart_scan"
    assert response.namespace == "scan-core"
    assert response.workflow_error == "scan_core_static_catalog"
    assert response.workflow_content is None


@pytest.mark.asyncio
async def test_skill_detail_endpoint_exposes_supported_test_metadata():
    response = await skills_module.get_skill_detail(
        skill_id="get_code_window",
        include_workflow=False,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.test_supported is True
    assert response.test_mode == "single_skill_strict"
    assert response.test_reason in (None, "")
    assert response.default_test_project_name == "libplist"

@pytest.mark.asyncio
async def test_skill_detail_endpoint_exposes_disabled_test_metadata():
    response = await skills_module.get_skill_detail(
        skill_id="dataflow_analysis",
        include_workflow=False,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.test_supported is True
    assert response.test_mode == "structured_tool"
    assert response.default_test_project_name == "libplist"
    assert response.test_reason in (None, "")
    assert response.tool_test_preset is not None
    assert response.tool_test_preset.project_name == "libplist"
    assert response.tool_test_preset.file_path == "src/xplist.c"
    assert response.tool_test_preset.function_name == "plist_from_xml"
    assert response.tool_test_preset.tool_input["variable_name"] == "plist_xml"


@pytest.mark.asyncio
async def test_skill_detail_endpoint_exposes_controlflow_structured_test_metadata():
    response = await skills_module.get_skill_detail(
        skill_id="controlflow_analysis_light",
        include_workflow=False,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.test_supported is True
    assert response.test_mode == "structured_tool"
    assert response.test_reason in (None, "")
    assert response.tool_test_preset is not None
    assert response.tool_test_preset.project_name == "libplist"
    assert response.tool_test_preset.file_path == "src/xplist.c"
    assert response.tool_test_preset.function_name == "plist_from_xml"
    assert response.tool_test_preset.tool_input["vulnerability_type"] == "xxe"


@pytest.mark.asyncio
async def test_skill_detail_endpoint_returns_404_for_missing_skill():
    with pytest.raises(HTTPException) as exc_info:
        await skills_module.get_skill_detail(
            skill_id="missing-skill",
            include_workflow=False,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404
    assert "missing-skill" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_skill_catalog_external_tools_mode_returns_scan_core_and_prompt_resources(
    db,
    test_user,
):
    created = await skills_module.create_prompt_skill(
        request=skills_module.PromptSkillCreateRequest(
            name="analysis custom",
            content="analysis custom content",
            scope="agent_specific",
            agent_key="analysis",
            is_active=True,
        ),
        db=db,
        current_user=test_user,
    )
    await skills_module.update_builtin_prompt_skill(
        agent_key="analysis",
        request=skills_module.PromptSkillBuiltinUpdateRequest(is_active=False),
        db=db,
        current_user=test_user,
    )

    response = await skills_module.get_skill_catalog(
        q="",
        namespace=None,
        resource_mode="external_tools",
        limit=200,
        offset=0,
        db=db,
        current_user=test_user,
    )

    assert response.total >= 3
    rows = {(item.tool_type, item.tool_id): item for item in response.items}

    scan_core = rows[("skill", "search_code")]
    assert scan_core.resource_kind_label == "Scan Core"
    assert scan_core.is_enabled is True
    assert scan_core.is_available is True
    assert scan_core.entrypoint == "scan-core/search_code"
    assert scan_core.agent_key is None
    assert scan_core.scope is None

    builtin_prompt = rows[("prompt-builtin", "analysis")]
    assert builtin_prompt.resource_kind_label == "Builtin Prompt Skill"
    assert builtin_prompt.is_enabled is False
    assert builtin_prompt.status_label == "停用"
    assert builtin_prompt.is_available is True
    assert builtin_prompt.entrypoint is None
    assert builtin_prompt.agent_key == "analysis"
    assert builtin_prompt.scope is None

    custom_prompt = rows[("prompt-custom", created.id)]
    assert custom_prompt.resource_kind_label == "Custom Prompt Skill"
    assert custom_prompt.is_enabled is True
    assert custom_prompt.is_available is True
    assert custom_prompt.entrypoint is None
    assert custom_prompt.agent_key == "analysis"
    assert custom_prompt.scope == "agent_specific"


@pytest.mark.asyncio
async def test_prompt_builtin_resource_detail_returns_read_only_prompt_skill_metadata(
    db,
    test_user,
):
    await skills_module.update_builtin_prompt_skill(
        agent_key="analysis",
        request=skills_module.PromptSkillBuiltinUpdateRequest(is_active=False),
        db=db,
        current_user=test_user,
    )

    response = await skills_module.get_skill_resource_detail(
        tool_type="prompt-builtin",
        tool_id="analysis",
        db=db,
        current_user=test_user,
    )

    assert response.tool_type == "prompt-builtin"
    assert response.tool_id == "analysis"
    assert response.agent_key == "analysis"
    assert response.is_builtin is True
    assert response.can_toggle is True
    assert response.can_edit is False
    assert response.can_delete is False
    assert response.is_enabled is False
    assert response.status_label == "停用"
    assert response.content


@pytest.mark.asyncio
async def test_prompt_custom_resource_detail_respects_user_scope(db, test_user):
    created = await skills_module.create_prompt_skill(
        request=skills_module.PromptSkillCreateRequest(
            name="custom detail",
            content="custom detail content",
            scope="agent_specific",
            agent_key="verification",
            is_active=False,
        ),
        db=db,
        current_user=test_user,
    )

    response = await skills_module.get_skill_resource_detail(
        tool_type="prompt-custom",
        tool_id=created.id,
        db=db,
        current_user=test_user,
    )

    assert response.tool_type == "prompt-custom"
    assert response.tool_id == created.id
    assert response.agent_key == "verification"
    assert response.scope == "agent_specific"
    assert response.is_builtin is False
    assert response.can_toggle is True
    assert response.can_edit is True
    assert response.can_delete is True
    assert response.is_enabled is False
    assert response.status_label == "停用"
    assert response.content == "custom detail content"

    other_user = User(
        email="other@example.com",
        full_name="Other User",
        hashed_password=get_password_hash("password123"),
        is_active=True,
        role="admin",
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    with pytest.raises(HTTPException) as exc_info:
        await skills_module.get_skill_resource_detail(
            tool_type="prompt-custom",
            tool_id=created.id,
            db=db,
            current_user=other_user,
        )

    assert exc_info.value.status_code in {403, 404}
