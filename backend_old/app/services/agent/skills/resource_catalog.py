from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from app.models.prompt_skill import PromptSkill

RESOURCE_MODE_SCAN_CORE_ONLY = "scan_core_only"
RESOURCE_MODE_EXTERNAL_TOOLS = "external_tools"

RESOURCE_TOOL_TYPE_SKILL = "skill"
RESOURCE_TOOL_TYPE_PROMPT_BUILTIN = "prompt-builtin"
RESOURCE_TOOL_TYPE_PROMPT_CUSTOM = "prompt-custom"

RESOURCE_NAMESPACE_SCAN_CORE = "scan-core"
RESOURCE_NAMESPACE_PROMPT_SKILL = "prompt-skill"


def build_status_label(*, is_enabled: bool, is_available: bool = True) -> str:
    if not is_available:
        return "不可用"
    return "启用" if is_enabled else "停用"


def build_prompt_summary(content: Any, *, limit: int = 120) -> str:
    normalized = " ".join(str(content or "").split()).strip()
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def split_query_terms(query: str) -> list[str]:
    return [part for part in str(query or "").strip().lower().split() if part]


def match_catalog_item(
    item: Mapping[str, Any],
    *,
    terms: Sequence[str],
    namespace: Optional[str] = None,
) -> bool:
    namespace_filter = str(namespace or "").strip().lower()
    item_namespace = str(item.get("namespace") or "").strip().lower()
    if namespace_filter and item_namespace != namespace_filter:
        return False

    if not terms:
        return True

    haystack = " ".join(
        str(item.get(key) or "")
        for key in (
            "skill_id",
            "tool_type",
            "tool_id",
            "name",
            "summary",
            "namespace",
            "resource_kind_label",
            "agent_key",
            "scope",
            "entrypoint",
            "content",
        )
    ).lower()
    return all(term in haystack for term in terms)


def paginate_catalog_items(
    items: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    total = len(items)
    paged = [dict(item) for item in items[offset : offset + limit]]
    return {
        "enabled": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": paged,
    }


def build_scan_core_catalog_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    tool_id = str(item.get("skill_id") or "").strip()
    return {
        "skill_id": tool_id,
        "tool_type": RESOURCE_TOOL_TYPE_SKILL,
        "tool_id": tool_id,
        "name": str(item.get("name") or tool_id),
        "namespace": RESOURCE_NAMESPACE_SCAN_CORE,
        "summary": str(item.get("summary") or ""),
        "category": str(item.get("category") or ""),
        "capabilities": list(item.get("capabilities") or []),
        "status_label": build_status_label(is_enabled=True),
        "is_enabled": True,
        "is_available": True,
        "resource_kind_label": "Scan Core",
        "detail_supported": True,
        "entrypoint": str(item.get("entrypoint") or f"{RESOURCE_NAMESPACE_SCAN_CORE}/{tool_id}"),
        "agent_key": None,
        "scope": None,
        "aliases": list(item.get("aliases") or []),
        "has_scripts": bool(item.get("has_scripts")),
        "has_bin": bool(item.get("has_bin")),
        "has_assets": bool(item.get("has_assets")),
    }


def build_prompt_builtin_catalog_item(*, agent_key: str, content: str, is_active: bool) -> Dict[str, Any]:
    tool_id = str(agent_key or "").strip()
    return {
        "skill_id": f"{RESOURCE_TOOL_TYPE_PROMPT_BUILTIN}:{tool_id}",
        "tool_type": RESOURCE_TOOL_TYPE_PROMPT_BUILTIN,
        "tool_id": tool_id,
        "name": tool_id,
        "namespace": RESOURCE_NAMESPACE_PROMPT_SKILL,
        "summary": build_prompt_summary(content),
        "status_label": build_status_label(is_enabled=is_active),
        "is_enabled": bool(is_active),
        "is_available": True,
        "resource_kind_label": "Builtin Prompt Skill",
        "detail_supported": True,
        "entrypoint": None,
        "agent_key": tool_id or None,
        "scope": None,
        "aliases": [],
        "has_scripts": False,
        "has_bin": False,
        "has_assets": False,
        "content": str(content or "").strip(),
    }


def build_prompt_custom_catalog_item(item: PromptSkill) -> Dict[str, Any]:
    prompt_id = str(getattr(item, "id", "") or "").strip()
    agent_key = str(getattr(item, "agent_key", "") or "").strip() or None
    scope = str(getattr(item, "scope", "") or "").strip() or None
    content = str(getattr(item, "content", "") or "").strip()
    return {
        "skill_id": f"{RESOURCE_TOOL_TYPE_PROMPT_CUSTOM}:{prompt_id}",
        "tool_type": RESOURCE_TOOL_TYPE_PROMPT_CUSTOM,
        "tool_id": prompt_id,
        "name": str(getattr(item, "name", "") or prompt_id),
        "namespace": RESOURCE_NAMESPACE_PROMPT_SKILL,
        "summary": build_prompt_summary(content),
        "status_label": build_status_label(is_enabled=bool(getattr(item, "is_active", False))),
        "is_enabled": bool(getattr(item, "is_active", False)),
        "is_available": True,
        "resource_kind_label": "Custom Prompt Skill",
        "detail_supported": True,
        "entrypoint": None,
        "agent_key": agent_key,
        "scope": scope,
        "aliases": [],
        "has_scripts": False,
        "has_bin": False,
        "has_assets": False,
        "content": content,
    }


def filter_catalog_items(
    items: Iterable[Mapping[str, Any]],
    *,
    query: str,
    namespace: Optional[str] = None,
) -> list[Dict[str, Any]]:
    terms = split_query_terms(query)
    filtered: list[Dict[str, Any]] = []
    for item in items:
        if match_catalog_item(item, terms=terms, namespace=namespace):
            filtered.append(dict(item))
    return filtered
