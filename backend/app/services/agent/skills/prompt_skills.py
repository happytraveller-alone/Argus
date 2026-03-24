"""Built-in prompt skills templates for core audit sub-agents."""

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


def build_effective_prompt_skills(use_prompt_skills: bool) -> dict[str, str]:
    """Return enabled prompt skills; disabled mode returns an empty mapping."""
    if not use_prompt_skills:
        return {}
    return dict(DEFAULT_PROMPT_SKILL_TEMPLATES)


__all__ = [
    "PROMPT_SKILL_AGENT_KEYS",
    "DEFAULT_PROMPT_SKILL_TEMPLATES",
    "build_effective_prompt_skills",
]
