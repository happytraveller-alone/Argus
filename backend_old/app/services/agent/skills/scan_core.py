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
    {"skill_id": "pattern_match", "name": "pattern_match", "summary": "用规则/模式快速筛查危险调用与脆弱代码模式。"},
    {"skill_id": "dataflow_analysis", "name": "dataflow_analysis", "summary": "分析 Source 到 Sink 的传播链与污点证据。"},
    {"skill_id": "controlflow_analysis_light", "name": "controlflow_analysis_light", "summary": "分析控制流、可达性与关键条件分支。"},
    {"skill_id": "run_code", "name": "run_code", "summary": "运行验证 Harness/PoC，收集动态执行证据。"},
    {"skill_id": "sandbox_exec", "name": "sandbox_exec", "summary": "在隔离沙箱中执行命令，验证运行时行为。"},
    {"skill_id": "verify_vulnerability", "name": "verify_vulnerability", "summary": "编排漏洞验证步骤并收敛最终验证结论。"},
    {"skill_id": "create_vulnerability_report", "name": "create_vulnerability_report", "summary": "生成正式漏洞报告并沉淀证据。"},
]

_SCAN_CORE_DISPLAY_METADATA: Dict[str, Dict[str, Any]] = {
    "get_code_window": {
        "category": "代码读取与定位",
        "goal": "在完成定位后提取最小证据窗口，避免大段盲读源码。",
        "task_list": ["围绕锚点取证", "返回最小代码窗口", "高亮焦点行"],
        "input_checklist": [
            "`file_path` (string, required): 目标文件路径",
            "`anchor_line` (number, required): 证据锚点行",
            "`before_lines` / `after_lines` (number, optional): 极小上下文范围",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/app.py\",\n  \"anchor_line\": 42,\n  \"before_lines\": 2,\n  \"after_lines\": 2\n}\n```",
        "pitfalls": ["不要无锚点取窗口。", "不要把代码窗口当作函数语义解释工具。"],
        "sample_prompts": [
            "读取 plist 解析入口附近的最小代码窗口",
            "请围绕 src/main.c 第 12 行取证",
        ],
    },
    "list_files": {
        "category": "代码读取与定位",
        "goal": "缩小扫描范围并定位相关代码。",
        "task_list": ["列出目录", "筛选候选文件", "返回相对路径"],
        "input_checklist": [
            "`directory` (string, optional): 目录",
            "`pattern` (string, optional): 匹配模式",
        ],
        "example_input": "```json\n{\n  \"directory\": \"src\",\n  \"pattern\": \"*.py\"\n}\n```",
        "pitfalls": ["不要把 list_files 当作全文代码搜索。"],
        "sample_prompts": [
            "列出和 plist 解析最相关的源文件",
            "列出 src 目录下的核心 C 文件",
        ],
    },
    "search_code": {
        "category": "代码读取与定位",
        "goal": "快速定位证据点、调用链入口和下一步应取证的位置。",
        "task_list": ["检索关键字", "返回 file_path:line 定位摘要", "提示继续收敛或取证"],
        "input_checklist": [
            "`keyword` (string, required): 搜索内容",
            "`directory` (string, optional): 搜索目录",
            "`file_pattern` (string, optional): 文件模式",
        ],
        "example_input": "```json\n{\n  \"keyword\": \"dangerous_call\",\n  \"directory\": \"src\",\n  \"file_pattern\": \"*.ts\"\n}\n```",
        "pitfalls": ["不要期待 search_code 返回上下文窗口。", "命中后应继续使用 get_code_window 或 get_function_summary。"],
        "sample_prompts": [
            "搜索 plist_from_memory 的调用位置",
            "帮我定位 XML 解析相关函数",
        ],
    },
    "get_file_outline": {
        "category": "代码读取与定位",
        "goal": "先理解文件在系统里的角色，再决定是否继续进入函数级分析。",
        "task_list": ["提炼文件职责", "枚举关键符号", "标记入口点和风险标记"],
        "input_checklist": ["`file_path` (string, required): 文件路径"],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c\"\n}\n```",
        "pitfalls": ["不要用文件概览代替函数级逻辑解释。"],
        "sample_prompts": [
            "概览 src/main.c 的整体职责",
            "这个文件在 plist 解析流程里扮演什么角色？",
        ],
    },
    "get_function_summary": {
        "category": "代码读取与定位",
        "goal": "在不输出大段源码的前提下快速理解函数语义。",
        "task_list": ["定位函数", "解释职责", "提取关键调用与风险点"],
        "input_checklist": [
            "`file_path` (string, required): 文件路径",
            "`function_name` (string, optional): 函数名",
            "`line` (number, optional): 函数内任意锚点行",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"function_name\": \"asctime64_r\"\n}\n```",
        "pitfalls": ["不要期待返回大段源码。", "如果需要源码主体，改用 get_symbol_body。"],
        "sample_prompts": [
            "总结 plist_from_memory 函数做什么",
            "帮我理解主解析入口函数的风险点",
        ],
    },
    "locate_enclosing_function": {
        "category": "代码读取与定位",
        "goal": "在只有文件锚点时快速回到函数边界，避免手动猜测函数范围。",
        "task_list": ["定位所属函数", "返回函数范围", "补全函数级证据锚点"],
        "input_checklist": [
            "`file_path` (string, required): 文件路径",
            "`line` (number, required): 函数内任意锚点行",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"line\": 132\n}\n```",
        "pitfalls": ["不要在没有明确锚点行时调用。", "定位到函数后仍应继续结合语义分析工具完成验证。"],
        "sample_prompts": [
            "src/xplist.c 第 120 行属于哪个函数？",
            "帮我确认 XML 解析锚点落在哪个函数里",
        ],
    },
    "get_symbol_body": {
        "category": "代码读取与定位",
        "goal": "在已经明确目标符号后，拿到完整函数体用于进一步验证。",
        "task_list": ["定位符号", "提取源码主体", "返回可渲染代码证据"],
        "input_checklist": [
            "`file_path` (string, required): 文件路径",
            "`symbol_name` (string, required): 符号名",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"symbol_name\": \"asctime64_r\"\n}\n```",
        "pitfalls": ["不要用源码提取替代函数语义总结。"],
        "sample_prompts": [
            "提取 plist_from_memory 函数源码",
            "提取主解析入口函数代码",
        ],
    },
    "pattern_match": {
        "category": "候选发现与模式扫描",
        "goal": "补充发现高风险候选与交叉验证。",
        "task_list": ["匹配危险模式", "输出命中位置", "给出风险说明"],
        "input_checklist": ["`pattern` (string, required): 模式或规则"],
        "example_input": "```json\n{\n  \"pattern\": \"eval\\\\(\"\n}\n```",
        "pitfalls": ["不要让模式匹配替代可达性或动态验证。"],
        "sample_prompts": [
            "搜索是否存在 XML_PARSE_NOENT 风险模式",
            "帮我匹配危险解析选项",
        ],
    },
    "dataflow_analysis": {
        "category": "可达性与逻辑分析",
        "goal": "沉淀结构化流证据，支撑真实性判断。",
        "task_list": ["识别 source/sink", "输出传播步骤", "标记风险等级"],
        "input_checklist": [
            "`source_code` (string, optional): 包含 source 的代码片段（与 variable_name 配合）",
            "`file_path` (string, optional): 直接从文件读取源码（source_code 为空时推荐）",
            "`start_line` / `end_line` (number, optional): 限定 file_path 读取的行范围",
            "`variable_name` (string, optional): 要追踪的变量名（默认 user_input）",
            "`source_hints` / `sink_hints` (string[], optional): Source/Sink 语义提示（可选）",
            "`sink_code` (string, optional): 包含 sink 的代码片段（可选）",
            "`language` (string, optional): 语言标记",
            "`max_hops` (number, optional): 最大传播步数",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"start_line\": 120,\n  \"end_line\": 180,\n  \"variable_name\": \"result\",\n  \"sink_hints\": [\"sprintf\"],\n  \"max_hops\": 8\n}\n```",
        "pitfalls": [
            "必须提供 source_code，或提供可读取的 file_path（可选 start_line/end_line）。",
            "不要把数据流结果直接当成最终确认，通常需要结合 controlflow_analysis_light 复核可达性。",
        ],
        "sample_prompts": [
            "检查 plist_xml 是否流向 xmlReadMemory",
            "追踪 plist_xml 到 xml_to_node 的传播链",
        ],
    },
    "controlflow_analysis_light": {
        "category": "可达性与逻辑分析",
        "goal": "验证候选漏洞是否真实可触达。",
        "task_list": ["定位目标函数", "分析调用链", "输出 blocked reasons"],
        "input_checklist": [
            "`file_path` (string, required): 目标文件路径；推荐使用 `path/to/file:line` 形式内嵌行号",
            "`line_start` / `line_end` (number, optional): 目标行范围（缺失时可从 file_path:line 推断）",
            "`function_name` (string, optional): 目标函数名（无行号时用于回退定位）",
            "`vulnerability_type` (string, optional): 漏洞类型（用于辅助评分）",
            "`entry_points` / `entry_points_hint` (string[], optional): 候选入口函数（或回退提示）",
            "`call_chain_hint` (string[], optional): 已知调用链提示",
            "`control_conditions_hint` (string[], optional): 已知控制条件提示",
        ],
        "example_input": "```json\n{\n  \"file_path\": \"src/time64.c:120\",\n  \"vulnerability_type\": \"buffer_overflow\",\n  \"call_chain_hint\": [\"main\"]\n}\n```",
        "pitfalls": [
            "优先提供 file_path:line 或 line_start 以确保可定位；缺少行号时可提供 function_name 作为回退。",
            "path_found=false 不等于漏洞不存在，可能是入口点不足或解析不完整导致。",
        ],
        "sample_prompts": [
            "验证 src/xplist.c:120 是否从 main 可达",
            "分析 plist_from_xml 的入口与阻断条件",
        ],
    },
    "run_code": {
        "category": "漏洞验证与 PoC 规划",
        "goal": "用非武器化方式验证候选漏洞，并保留执行命令、退出码、输出摘要与执行代码。",
        "task_list": ["编写 Harness", "执行验证", "输出执行摘要", "保留可回看的代码与输出证据"],
        "input_checklist": [
            "`code` (string, required): 待执行代码",
            "`language` (string, optional): 语言",
        ],
        "example_input": "```json\n{\n  \"language\": \"python\",\n  \"code\": \"print(1)\"\n}\n```",
        "pitfalls": ["不要在缺少隔离前提时执行高风险 payload。"],
        "sample_prompts": [
            "运行一个最小 Python Harness 验证输出",
            "帮我写并执行一个安全的最小验证脚本",
        ],
    },
    "sandbox_exec": {
        "category": "漏洞验证与 PoC 规划",
        "goal": "验证运行时行为、环境差异与命令执行证据，直观展示命令、退出码与输出结果。",
        "task_list": ["执行命令", "采集输出", "记录实验条件", "返回执行摘要与输出证据"],
        "input_checklist": ["`command` (string, required): 命令文本"],
        "example_input": "```json\n{\n  \"command\": \"echo hello\"\n}\n```",
        "pitfalls": ["不要把沙箱输出脱离代码证据单独解读。"],
        "sample_prompts": [
            "在沙箱里执行 `echo hello` 并返回结果",
            "验证运行时命令输出和退出码",
        ],
    },
    "verify_vulnerability": {
        "category": "漏洞验证与 PoC 规划",
        "goal": "统一管理验证过程与最终 verdict。",
        "task_list": ["制定验证路径", "整合实验结果", "输出 verdict"],
        "input_checklist": ["`finding` (object, required): 待验证漏洞对象"],
        "example_input": "```json\n{\n  \"finding\": {\n    \"file_path\": \"src/app.py\",\n    \"line_start\": 42\n  }\n}\n```",
        "pitfalls": ["不要在证据不足时给出 confirmed。"],
        "sample_prompts": [
            "为 src/app.py:42 的候选问题设计验证路径",
            "基于当前 finding 给出最终验证结论",
        ],
    },
    "create_vulnerability_report": {
        "category": "报告与协作编排",
        "goal": "沉淀可交付结果与可追溯证据。",
        "task_list": ["整理结论", "结构化报告", "输出修复建议"],
        "input_checklist": [
            "`title` (string, required): 标题",
            "`file_path` (string, required): 文件路径",
        ],
        "example_input": "```json\n{\n  \"title\": \"src/time64.c中asctime64_r栈溢出漏洞\",\n  \"file_path\": \"src/time64.c\"\n}\n```",
        "pitfalls": ["不要在未完成验证时创建正式报告。"],
        "sample_prompts": [
            "为 src/time64.c 的问题生成正式漏洞报告",
            "整理当前证据并输出修复建议",
        ],
    },
}

SCAN_CORE_SKILL_IDS = tuple(item["skill_id"] for item in _SCAN_CORE_SKILLS)
_SCAN_CORE_BY_ID = {item["skill_id"]: item for item in _SCAN_CORE_SKILLS}
SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS = frozenset()
SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS = frozenset()
SCAN_CORE_RUNTIME_BOUND_SKILL_IDS = (
    SCAN_CORE_FILESYSTEM_BOUND_SKILL_IDS | SCAN_CORE_CODE_INDEX_BOUND_SKILL_IDS
)
SCAN_CORE_LOCAL_SKILL_IDS = frozenset(
    skill_id for skill_id in SCAN_CORE_SKILL_IDS if skill_id not in SCAN_CORE_RUNTIME_BOUND_SKILL_IDS
)
SCAN_CORE_DEFAULT_TEST_PROJECT_NAME = "libplist"
SCAN_CORE_STRUCTURED_TOOL_PRESETS: Dict[str, Dict[str, Any]] = {
    "dataflow_analysis": {
        "project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
        "file_path": "src/xplist.c",
        "function_name": "plist_from_xml",
        "line_start": None,
        "line_end": None,
        "tool_input": {
            "variable_name": "plist_xml",
            "sink_hints": ["xmlReadMemory", "xmlParseMemory", "xml_to_node"],
        },
    },
    "controlflow_analysis_light": {
        "project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
        "file_path": "src/xplist.c",
        "function_name": "plist_from_xml",
        "line_start": None,
        "line_end": None,
        "tool_input": {
            "entry_points": ["plist_from_xml"],
            "vulnerability_type": "xxe",
        },
    },
}
SCAN_CORE_SKILL_TEST_SUPPORTED_IDS = frozenset(
    {
        "list_files",
        "search_code",
        "get_code_window",
        "get_file_outline",
        "get_function_summary",
        "get_symbol_body",
        "pattern_match",
    }
)
SCAN_CORE_SKILL_TEST_DISABLED_REASONS: Dict[str, str] = {
    "dataflow_analysis": "首版仅开放可直接基于 libplist 自然语言提问的 skill；数据流分析依赖更复杂的上下文建模。",
    "controlflow_analysis_light": "首版仅开放可直接基于 libplist 自然语言提问的 skill；控制流分析依赖更复杂的上下文建模。",
    "run_code": "首版详情页暂不开放动态执行类 skill，避免引入额外运行时依赖。",
    "sandbox_exec": "首版详情页暂不开放动态执行类 skill，避免引入额外运行时依赖。",
    "verify_vulnerability": "首版详情页暂不开放多步骤编排型验证 skill。",
    "create_vulnerability_report": "首版详情页暂不开放报告生成型 skill。",
}


def get_scan_core_skill_test_policy(skill_id: str) -> Dict[str, Any]:
    normalized = str(skill_id or "").strip()
    structured_preset = SCAN_CORE_STRUCTURED_TOOL_PRESETS.get(normalized)
    if structured_preset is not None:
        return {
            "test_supported": True,
            "test_mode": "structured_tool",
            "test_reason": None,
            "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
            "tool_test_preset": structured_preset,
        }
    if normalized in SCAN_CORE_SKILL_TEST_SUPPORTED_IDS:
        return {
            "test_supported": True,
            "test_mode": "single_skill_strict",
            "test_reason": None,
            "default_test_project_name": SCAN_CORE_DEFAULT_TEST_PROJECT_NAME,
            "tool_test_preset": None,
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
        "tool_test_preset": None,
    }


def _base_detail(item: Dict[str, Any]) -> Dict[str, Any]:
    skill_id = str(item["skill_id"])
    display_metadata = _SCAN_CORE_DISPLAY_METADATA.get(skill_id, {})
    return {
        "skill_id": skill_id,
        "name": str(item.get("name") or skill_id),
        "namespace": "scan-core",
        "summary": str(item.get("summary") or ""),
        "category": str(display_metadata.get("category") or ""),
        "goal": str(display_metadata.get("goal") or ""),
        "task_list": list(display_metadata.get("task_list") or []),
        "input_checklist": list(display_metadata.get("input_checklist") or []),
        "example_input": str(display_metadata.get("example_input") or ""),
        "pitfalls": list(display_metadata.get("pitfalls") or []),
        "sample_prompts": list(display_metadata.get("sample_prompts") or []),
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
            "category": detail["category"],
            "capabilities": list(detail["task_list"]),
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
