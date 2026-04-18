from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUST_SCAN_RULE_ASSETS_ROOT = _REPO_ROOT / "backend" / "assets" / "scan_rule_assets"

PMD_RULESET_ALIASES = {
    "security": "category/java/security.xml,category/java/errorprone.xml,category/apex/security.xml",
    "quickstart": "category/java/security.xml,category/jsp/security.xml,category/javascript/security.xml",
    "all": (
        "category/java/security.xml,"
        "category/jsp/security.xml,"
        "category/javascript/security.xml,"
        "category/html/security.xml,"
        "category/xml/security.xml,"
        "category/plsql/security.xml,"
        "category/apex/security.xml,"
        "category/visualforce/security.xml"
    ),
}

PMD_PRESET_SUMMARIES = {
    "security": {
        "alias": PMD_RULESET_ALIASES["security"],
        "name": "安全优先",
        "description": "覆盖 Java/Apex 安全与高价值错误规则，贴近 PMDTool 的默认执行语义。",
        "categories": ["java", "errorprone", "apex"],
    },
    "quickstart": {
        "alias": PMD_RULESET_ALIASES["quickstart"],
        "name": "快速起步",
        "description": "提供适合多语言仓库快速接入的安全规则组合。",
        "categories": ["java", "jsp", "javascript"],
    },
    "all": {
        "alias": PMD_RULESET_ALIASES["all"],
        "name": "全量安全分类",
        "description": "展示 PMD 内置安全分类全集，便于页面内检索与对照。",
        "categories": [
            "java",
            "jsp",
            "javascript",
            "html",
            "xml",
            "plsql",
            "apex",
            "visualforce",
        ],
    },
}


def get_pmd_builtin_ruleset_dir() -> Path:
    return _RUST_SCAN_RULE_ASSETS_ROOT / "rules_pmd"


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def _to_optional_int(value: str | None) -> int | None:
    text = _normalize_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _build_rule_payload(rule_node: ElementTree.Element) -> dict[str, Any]:
    description = _normalize_text(rule_node.findtext("./{*}description"))
    priority = _to_optional_int(rule_node.findtext("./{*}priority"))
    return {
        "name": _normalize_text(rule_node.get("name")),
        "ref": _normalize_text(rule_node.get("ref")),
        "language": _normalize_text(rule_node.get("language")),
        "message": _normalize_text(rule_node.get("message")),
        "class_name": _normalize_text(rule_node.get("class")),
        "priority": priority,
        "since": _normalize_text(rule_node.get("since")),
        "external_info_url": _normalize_text(rule_node.get("externalInfoUrl")),
        "description": description,
    }


def parse_pmd_ruleset_xml(raw_xml: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError as exc:
        raise ValueError(f"PMD XML 解析失败: {exc}") from exc

    rule_nodes = root.findall(".//{*}rule")
    if not rule_nodes:
        raise ValueError("PMD ruleset 至少包含一个 <rule>")

    rules = [_build_rule_payload(rule_node) for rule_node in rule_nodes]
    languages = _ordered_unique(
        [language for language in (rule["language"] for rule in rules) if language]
    )
    priorities = sorted(
        {priority for priority in (rule["priority"] for rule in rules) if priority is not None}
    )
    external_info_urls = _ordered_unique(
        [url for url in (rule["external_info_url"] for rule in rules) if url]
    )

    return {
        "ruleset_name": _normalize_text(root.get("name")) or "Unnamed PMD Ruleset",
        "description": _normalize_text(root.findtext("./{*}description")),
        "rule_count": len(rules),
        "languages": languages,
        "priorities": priorities,
        "external_info_urls": external_info_urls,
        "rules": rules,
        "raw_xml": raw_xml,
    }


_RULESET_NAME_PATTERN = re.compile(r'<ruleset\b[^>]*\bname="([^"]+)"', re.DOTALL)
_RULE_START_PATTERN = re.compile(r"<rule\b(?P<attrs>[^>]*)>", re.DOTALL)
_DESCRIPTION_PATTERN = re.compile(r"<description(?:\s[^>]*)?>(?P<body>.*)", re.DOTALL)
_PRIORITY_PATTERN = re.compile(r"<priority>\s*(\d+)\s*</priority>", re.DOTALL)


def _strip_example_fence(value: str | None) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    if text.startswith("<![CDATA["):
        text = text[len("<![CDATA["):].strip()
    if "```xml" in text:
        text = text.split("```xml", 1)[0].strip()
    return _normalize_text(text)


def _parse_builtin_pmd_ruleset_xml_fallback(raw_xml: str) -> dict[str, Any]:
    first_rule_match = _RULE_START_PATTERN.search(raw_xml)
    if first_rule_match is None:
        raise ValueError("PMD ruleset 至少包含一个 <rule>")

    next_rule_match = _RULE_START_PATTERN.search(raw_xml, first_rule_match.end())
    chunk_end = next_rule_match.start() if next_rule_match else len(raw_xml)
    rule_chunk = raw_xml[first_rule_match.start():chunk_end]

    rule_node = ElementTree.fromstring(f"<rule{first_rule_match.group('attrs')} />")
    rule_payload = _build_rule_payload(rule_node)

    description_match = _DESCRIPTION_PATTERN.search(rule_chunk)
    if description_match is not None:
        rule_payload["description"] = _strip_example_fence(description_match.group("body"))

    priority_match = _PRIORITY_PATTERN.search(rule_chunk)
    if priority_match is not None:
        rule_payload["priority"] = int(priority_match.group(1))

    prefix = raw_xml[:first_rule_match.start()]
    root_description_match = re.search(r"<description>(?P<body>.*?)</description>", prefix, re.DOTALL)
    ruleset_name_match = _RULESET_NAME_PATTERN.search(raw_xml)

    languages = [rule_payload["language"]] if rule_payload["language"] else []
    priorities = [rule_payload["priority"]] if rule_payload["priority"] is not None else []
    external_info_urls = (
        [rule_payload["external_info_url"]] if rule_payload["external_info_url"] else []
    )

    return {
        "ruleset_name": (
            _normalize_text(ruleset_name_match.group(1))
            if ruleset_name_match is not None
            else "Unnamed PMD Ruleset"
        ),
        "description": (
            _normalize_text(root_description_match.group("body"))
            if root_description_match is not None
            else None
        ),
        "rule_count": 1,
        "languages": languages,
        "priorities": priorities,
        "external_info_urls": external_info_urls,
        "rules": [rule_payload],
        "raw_xml": raw_xml,
    }


def _matches_keyword(payload: dict[str, Any], keyword: str | None) -> bool:
    if not keyword:
        return True
    needle = keyword.strip().lower()
    if not needle:
        return True

    haystacks = [
        payload.get("id"),
        payload.get("ruleset_name"),
        payload.get("description"),
        payload.get("filename"),
    ]
    for rule in payload.get("rules", []):
        haystacks.extend(
            [
                rule.get("name"),
                rule.get("ref"),
                rule.get("language"),
                rule.get("message"),
                rule.get("class_name"),
                rule.get("since"),
                rule.get("external_info_url"),
                rule.get("description"),
            ]
        )

    return any(needle in str(item).lower() for item in haystacks if item)


def _matches_language(payload: dict[str, Any], language: str | None) -> bool:
    if not language:
        return True
    needle = language.strip().lower()
    if not needle:
        return True
    return any(str(item).lower() == needle for item in payload.get("languages", []))


@lru_cache(maxsize=1)
def _load_builtin_pmd_rulesets() -> tuple[dict[str, Any], ...]:
    builtin_dir = get_pmd_builtin_ruleset_dir()
    payloads: list[dict[str, Any]] = []

    for ruleset_path in sorted(builtin_dir.glob("*.xml")):
        raw_xml = ruleset_path.read_text(encoding="utf-8")
        try:
            payload = parse_pmd_ruleset_xml(raw_xml)
        except ValueError:
            payload = _parse_builtin_pmd_ruleset_xml_fallback(raw_xml)
        payloads.append(
            {
                "id": ruleset_path.name,
                "filename": ruleset_path.name,
                "source": "builtin",
                **payload,
            }
        )

    return tuple(payloads)


def list_builtin_pmd_rulesets(
    *,
    keyword: str | None = None,
    language: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = [
        deepcopy(item)
        for item in _load_builtin_pmd_rulesets()
        if _matches_keyword(item, keyword) and _matches_language(item, language)
    ]

    if limit is not None and limit >= 0:
        return rows[:limit]
    return rows


def get_builtin_pmd_ruleset_detail(ruleset_id: str) -> dict[str, Any]:
    normalized_id = str(ruleset_id or "").strip()
    for payload in _load_builtin_pmd_rulesets():
        if payload["id"] == normalized_id:
            return deepcopy(payload)
    raise FileNotFoundError(f"PMD builtin ruleset 不存在: {normalized_id}")
