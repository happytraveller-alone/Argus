from __future__ import annotations

from typing import Any, Dict, List, Optional


_SCAN_CORE_SKILLS: List[Dict[str, Any]] = [
    {"skill_id": "search_code", "name": "search_code", "summary": "在项目中检索代码片段、关键字与命中位置。"},
    {"skill_id": "list_files", "name": "list_files", "summary": "按目录或模式列出候选文件，快速缩小分析范围。"},
    {"skill_id": "get_code_window", "name": "get_code_window", "summary": "围绕锚点返回极小代码窗口，作为唯一代码取证来源。"},
    {"skill_id": "get_file_outline", "name": "get_file_outline", "summary": "返回文件整体职责、关键符号与入口点概览。"},
    {"skill_id": "get_function_summary", "name": "get_function_summary", "summary": "解释单个函数的职责、输入输出、关键调用与风险点。"},
    {"skill_id": "get_symbol_body", "name": "get_symbol_body", "summary": "提取目标函数/符号主体源码，不承担语义解释。"},
    {"skill_id": "locate_enclosing_function", "name": "locate_enclosing_function", "summary": "根据文件与行号定位所属函数及其范围，辅助补全函数级证据。"},
    {"skill_id": "smart_scan", "name": "smart_scan", "summary": "执行智能扫描，快速定位高风险区域。"},
    {"skill_id": "quick_audit", "name": "quick_audit", "summary": "执行轻量快速审计，输出优先检查点。"},
    {"skill_id": "pattern_match", "name": "pattern_match", "summary": "用规则/模式快速筛查危险调用与脆弱代码模式。"},
    {"skill_id": "dataflow_analysis", "name": "dataflow_analysis", "summary": "分析 Source 到 Sink 的传播链与污点证据。"},
    {"skill_id": "controlflow_analysis_light", "name": "controlflow_analysis_light", "summary": "分析控制流、可达性与关键条件分支。"},
    {"skill_id": "logic_authz_analysis", "name": "logic_authz_analysis", "summary": "分析认证、授权与业务逻辑边界。"},
    {"skill_id": "run_code", "name": "run_code", "summary": "运行验证 Harness/PoC，收集动态执行证据。"},
    {"skill_id": "sandbox_exec", "name": "sandbox_exec", "summary": "在隔离沙箱中执行命令，验证运行时行为。"},
    {"skill_id": "verify_vulnerability", "name": "verify_vulnerability", "summary": "编排漏洞验证步骤并收敛最终验证结论。"},
    {"skill_id": "create_vulnerability_report", "name": "create_vulnerability_report", "summary": "生成正式漏洞报告并沉淀证据。"},
    {"skill_id": "think", "name": "think", "summary": "用于分析、规划和决策的思考工具。"},
    {"skill_id": "reflect", "name": "reflect", "summary": "用于复盘、校验和调整策略的反思工具。"},
]

SCAN_CORE_SKILL_IDS = tuple(item["skill_id"] for item in _SCAN_CORE_SKILLS)
_SCAN_CORE_BY_ID = {item["skill_id"]: item for item in _SCAN_CORE_SKILLS}
SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS = frozenset()
SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS = frozenset()
SCAN_CORE_MCP_BOUND_SKILL_IDS = (
    SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS | SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS
)
SCAN_CORE_LOCAL_SKILL_IDS = frozenset(
    skill_id for skill_id in SCAN_CORE_SKILL_IDS if skill_id not in SCAN_CORE_MCP_BOUND_SKILL_IDS
)
SCAN_CORE_DEFAULT_TEST_PROJECT_NAME = "libplist"
SCAN_CORE_SKILL_TEST_SUPPORTED_IDS = frozenset(
    {
        "list_files",
        "search_code",
        "get_code_window",
        "get_file_outline",
        "get_function_summary",
        "get_symbol_body",
        "pattern_match",
        "smart_scan",
        "quick_audit",
        "think",
        "reflect",
    }
)
SCAN_CORE_SKILL_TEST_DISABLED_REASONS: Dict[str, str] = {
    "dataflow_analysis": "首版仅开放可直接基于 libplist 自然语言提问的 skill；数据流分析依赖更复杂的上下文建模。",
    "controlflow_analysis_light": "首版仅开放可直接基于 libplist 自然语言提问的 skill；控制流分析依赖更复杂的上下文建模。",
    "logic_authz_analysis": "首版仅开放可直接基于 libplist 自然语言提问的 skill；鉴权/业务逻辑分析依赖更复杂的上下文建模。",
    "run_code": "首版详情页暂不开放动态执行类 skill，避免引入额外运行时依赖。",
    "sandbox_exec": "首版详情页暂不开放动态执行类 skill，避免引入额外运行时依赖。",
    "verify_vulnerability": "首版详情页暂不开放多步骤编排型验证 skill。",
    "create_vulnerability_report": "首版详情页暂不开放报告生成型 skill。",
}


def get_scan_core_skill_test_policy(skill_id: str) -> Dict[str, Any]:
    normalized = str(skill_id or "").strip()
    if normalized in SCAN_CORE_SKILL_TEST_SUPPORTED_IDS:
        return {
            "test_supported": True,
            "test_mode": "single_skill_strict",
            "test_reason": None,
            "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
        }

    disabled_reason = SCAN_CORE_SKILL_TEST_DISABLED_REASONS.get(
        normalized,
        "首版仅开放直接可在 libplist 上进行自然语言提问测试的单技能集合。",
    )
    return {
        "test_supported": False,
        "test_mode": "disabled",
        "test_reason": disabled_reason,
        "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
    }


def _base_detail(item: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = str(item["skill_id"])
    return {
        "skill_id": skill_id,
        "name": str(item.get("name") or skill_id),
        "namespace": "scan-core",
        "summary": str(item.get("summary") or ""),
        "entrypoint": f"scan-core/{skill_id}",
        "aliases": [],
        "has_scripts": False,
        "has_bin": False,
        "has_assets": False,
        "mirror_dir": "",
        "source_root": "",
        "source_dir": "",
        "source_skill_md": "",
        "files_count": 0,
        "workflow_content": None,
        "workflow_truncated": False,
        "workflow_error": "scan_core_static_catalog",
        **get_scan_core_skill_test_policy(skill_id),
    }


def get_scan_core_skill_detail(skill_id: str) -> Optional[Dict[str, Any]]:
    item = _SCAN_CORE_BY_ID.get(str(skill_id or "").strip())
    if item is None:
        return None
    return _base_detail(item)


def search_scan_core_skills(
    *,
    query: str = "",
    namespace: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    namespace_filter = str(namespace or "").strip().lower()
    if namespace_filter and namespace_filter != "scan-core":
        return {"enabled": True, "total": 0, "limit": limit, "offset": offset, "items": []}

    terms = [part for part in str(query or "").strip().lower().split() if part]
    items = []
    for raw in _SCAN_CORE_SKILLS:
        detail = _base_detail(raw)
        haystack = " ".join(
            [detail["skill_id"], detail["name"], detail["summary"], detail["namespace"]]
        ).lower()
        if terms and not all(term in haystack for term in terms):
            continue
        items.append({
            "skill_id": detail["skill_id"],
            "name": detail["name"],
            "namespace": detail["namespace"],
            "summary": detail["summary"],
            "entrypoint": detail["entrypoint"],
            "aliases": detail["aliases"],
            "has_scripts": detail["has_scripts"],
            "has_bin": detail["has_bin"],
            "has_assets": detail["has_assets"],
        })

    total = len(items)
    paged = items[offset : offset + limit]
    return {"enabled": True, "total": total, "limit": limit, "offset": offset, "items": paged}


def build_scan_core_skill_availability(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    availability: Dict[str, Dict[str, Any]] = {}
    for skill_id in SCAN_CORE_SKILL_IDS:
        availability[skill_id] = {
            "enabled": True,
            "startup_ready": True,
            "runtime_ready": True,
            "reason": "ready",
            "source": "local",
        }

    return availability
