from __future__ import annotations

from typing import Any, Dict, List, Optional


_SCAN_CORE_SKILLS: List[Dict[str, Any]] = [
    {"skill_id": "read_file", "name": "read_file", "summary": "读取项目文件内容并返回证据上下文。"},
    {"skill_id": "search_code", "name": "search_code", "summary": "在项目中检索代码片段、关键字与命中位置。"},
    {"skill_id": "list_files", "name": "list_files", "summary": "按目录或模式列出候选文件，快速缩小分析范围。"},
    {"skill_id": "extract_function", "name": "extract_function", "summary": "提取目标函数/符号主体，辅助漏洞分析与验证。"},
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
SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS = frozenset({"read_file"})
SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS = frozenset({"search_code", "list_files", "extract_function"})
SCAN_CORE_MCP_BOUND_SKILL_IDS = (
    SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS | SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS
)
SCAN_CORE_LOCAL_SKILL_IDS = frozenset(
    skill_id for skill_id in SCAN_CORE_SKILL_IDS if skill_id not in SCAN_CORE_MCP_BOUND_SKILL_IDS
)


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
    catalog_by_id = {
        str(item.get("id") or "").strip(): item
        for item in catalog
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }

    def _mcp_ready(mcp_id: str) -> bool:
        item = catalog_by_id.get(mcp_id, {})
        return bool(item.get("enabled")) and bool(item.get("startup_ready", True))

    filesystem_ready = _mcp_ready("filesystem")
    code_index_ready = _mcp_ready("code_index")

    availability: Dict[str, Dict[str, Any]] = {}
    for skill_id in SCAN_CORE_SKILL_IDS:
        if skill_id in SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS:
            enabled = filesystem_ready
            source = "mcp"
            reason = "ready" if enabled else "mcp_not_ready:filesystem"
        elif skill_id in SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS:
            enabled = code_index_ready
            source = "mcp"
            reason = "ready" if enabled else "mcp_not_ready:code_index"
        else:
            enabled = True
            source = "local"
            reason = "ready"

        availability[skill_id] = {
            "enabled": enabled,
            "startup_ready": enabled,
            "runtime_ready": enabled,
            "reason": reason,
            "source": source,
        }

    return availability
