"""Built-in prompt skill templates and custom prompt-skill merge helpers."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

PROMPT_SKILL_AGENT_KEYS: list[str] = [
    "recon",
    "business_logic_recon",
    "analysis",
    "business_logic_analysis",
    "verification",
]

DEFAULT_PROMPT_SKILL_TEMPLATES: dict[str, str] = {
    "recon": (
        "优先快速建立项目画像：先识别入口、认证边界、外部输入面，再按风险优先级推进目录扫描。"
        "所有风险点必须基于真实代码证据，并尽量附带触发条件。"
    ),
    "business_logic_recon": (
        "优先枚举业务对象与敏感动作，重点关注对象所有权、状态跃迁、金额计算、权限边界。"
        "若项目缺少业务入口，应尽早给出终止依据。"
    ),
    "analysis": (
        "围绕单风险点做证据闭环：先定位代码，再追踪输入到敏感操作的数据流与控制流，"
        "结论必须可复核并明确漏洞成立条件。"
    ),
    "business_logic_analysis": (
        "优先验证授权与状态机约束，必须检查全局补偿逻辑（中间件、依赖注入、service guard、repository filter），"
        "避免将已补偿场景误报为漏洞。"
    ),
    "verification": (
        "验证阶段必须坚持可复现证据优先：先读取上下文，再最小化构造触发路径。"
        "无法稳定触发时，应明确记录阻断条件并谨慎降级结论。"
    ),
}

PROMPT_SKILL_SCOPE_GLOBAL = "global"
PROMPT_SKILL_SCOPE_AGENT_SPECIFIC = "agent_specific"
PROMPT_SKILL_SCOPES: tuple[str, str] = (
    PROMPT_SKILL_SCOPE_GLOBAL,
    PROMPT_SKILL_SCOPE_AGENT_SPECIFIC,
)

PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY = "promptSkillBuiltinState"


def _coerce_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def build_prompt_skill_builtin_state(raw_state: Any = None) -> dict[str, bool]:
    """Return normalized built-in prompt-skill enabled state for all agent keys."""
    candidate = raw_state if isinstance(raw_state, Mapping) else {}
    return {
        key: _coerce_bool(candidate.get(key), default=True)
        for key in PROMPT_SKILL_AGENT_KEYS
    }


def apply_prompt_skill_builtin_state(
    *,
    base_prompt_skills: Mapping[str, str],
    builtin_state: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Filter built-in prompt skills by per-agent enabled state."""
    normalized_state = build_prompt_skill_builtin_state(builtin_state)
    filtered: dict[str, str] = {}
    for key in PROMPT_SKILL_AGENT_KEYS:
        if not normalized_state.get(key, True):
            continue
        value = str(base_prompt_skills.get(key) or "").strip()
        if value:
            filtered[key] = value
    return filtered


def build_effective_prompt_skills(use_prompt_skills: bool) -> dict[str, str]:
    """Return enabled prompt skills; disabled mode returns an empty mapping."""
    if not use_prompt_skills:
        return {}
    return dict(DEFAULT_PROMPT_SKILL_TEMPLATES)


def resolve_prompt_skill_scope_agent_key(
    scope: Any,
    agent_key: Any,
) -> tuple[str, str | None]:
    """Normalize and validate prompt-skill scope + agent binding."""
    normalized_scope = str(scope or PROMPT_SKILL_SCOPE_GLOBAL).strip().lower()
    if normalized_scope not in PROMPT_SKILL_SCOPES:
        raise ValueError(f"Invalid prompt skill scope: {scope}")

    normalized_agent_key = str(agent_key or "").strip() or None
    if normalized_scope == PROMPT_SKILL_SCOPE_AGENT_SPECIFIC:
        if normalized_agent_key not in PROMPT_SKILL_AGENT_KEYS:
            raise ValueError(
                f"agent_key is required when scope=agent_specific and must be one of {PROMPT_SKILL_AGENT_KEYS}"
            )
    else:
        normalized_agent_key = None
    return normalized_scope, normalized_agent_key


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def merge_prompt_skills_with_custom(
    *,
    base_prompt_skills: Mapping[str, str],
    custom_prompt_skills: Sequence[Any],
) -> dict[str, str]:
    """
    Merge built-in prompt skills with user-defined custom skills.

    Rules:
    - `global` scope applies to all agent keys.
    - `agent_specific` scope only applies to the selected agent key.
    - Inactive/empty custom rows are ignored.
    """
    merged: dict[str, str] = {}
    for key in PROMPT_SKILL_AGENT_KEYS:
        merged[key] = str(base_prompt_skills.get(key) or "").strip()

    global_blocks: list[str] = []
    agent_blocks: dict[str, list[str]] = {key: [] for key in PROMPT_SKILL_AGENT_KEYS}

    for row in custom_prompt_skills:
        is_active = _row_value(row, "is_active")
        if is_active is False:
            continue

        content = str(_row_value(row, "content") or "").strip()
        if not content:
            continue

        name = str(_row_value(row, "name") or "").strip()
        rendered_content = f"[{name}] {content}" if name else content

        try:
            scope, agent_key = resolve_prompt_skill_scope_agent_key(
                _row_value(row, "scope"),
                _row_value(row, "agent_key"),
            )
        except ValueError:
            continue

        if scope == PROMPT_SKILL_SCOPE_GLOBAL:
            global_blocks.append(rendered_content)
            continue

        if agent_key in agent_blocks:
            agent_blocks[agent_key].append(rendered_content)

    global_block = "\n".join(global_blocks).strip()
    for key in PROMPT_SKILL_AGENT_KEYS:
        fragments: list[str] = []
        base_text = str(merged.get(key) or "").strip()
        if base_text:
            fragments.append(base_text)
        if global_block:
            fragments.append(global_block)
        scoped_block = "\n".join(agent_blocks.get(key, [])).strip()
        if scoped_block:
            fragments.append(scoped_block)
        merged[key] = "\n\n".join(fragment for fragment in fragments if fragment.strip())

    return merged


__all__ = [
    "PROMPT_SKILL_AGENT_KEYS",
    "DEFAULT_PROMPT_SKILL_TEMPLATES",
    "PROMPT_SKILL_SCOPE_GLOBAL",
    "PROMPT_SKILL_SCOPE_AGENT_SPECIFIC",
    "PROMPT_SKILL_SCOPES",
    "PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY",
    "build_prompt_skill_builtin_state",
    "apply_prompt_skill_builtin_state",
    "build_effective_prompt_skills",
    "resolve_prompt_skill_scope_agent_key",
    "merge_prompt_skills_with_custom",
]
