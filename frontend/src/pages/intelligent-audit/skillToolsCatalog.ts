export type SkillToolCategory =
  "代码读取与定位" |
  "候选发现与模式扫描" |
  "可达性与逻辑分析" |
  "漏洞验证与 PoC 规划" |
  "报告与协作编排";

export interface SkillToolCatalogItem {
  id: string;
  category: SkillToolCategory;
  summary: string;
  goal: string;
  taskList: string[];
  inputChecklist: string[];
  exampleInput: string;
  pitfalls: string[];
}

export const SKILL_TOOL_CATEGORY_ORDER: SkillToolCategory[] = [
  "代码读取与定位",
  "候选发现与模式扫描",
  "可达性与逻辑分析",
  "报告与协作编排",
];

const SKILL_TOOLS_CATALOG_RAW: SkillToolCatalogItem[] = [
  {
    id: "controlflow_analysis_light",
    category: "可达性与逻辑分析",
    summary: `轻量控制流/可达性分析：基于 tree-sitter + code2flow 推断调用链、控制条件和路径分值，支持 file_path:line 简写与函数定位补偿。`,
    goal: "为高危候选提供可解释的 reachability 证据，支撑验证结论。",
    taskList: [
      "根据 file_path:line 或 function_name 定位目标函数。",
      "计算 path_found/path_score/call_chain/control_conditions。",
      "输出可操作 blocked_reasons，指导下一步改参或换策略。",
    ],
    inputChecklist: [
      "`file_path` (string, required): 目标文件路径，支持 file_path:line",
      "`line_start` (integer, optional): 目标起始行",
      "`line_end` (any, optional): 目标结束行",
      "`function_name` (any, optional): 缺少 line_start 时用于定位函数",
      "`severity` (any, optional): 漏洞严重度",
      "`confidence` (any, optional): 漏洞置信度 0-1",
      "`entry_points` (any, optional): 候选入口函数",
      "`entry_points_hint` (any, optional): 入口提示",
      "`call_chain_hint` (any, optional): 调用链提示",
      "`control_conditions_hint` (any, optional): 控制条件提示",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "src/time64.c:168",
  "function_name": "asctime64_r",
  "severity": "high",
  "confidence": 0.88,
  "entry_points_hint": ["main"]
}
\`\`\``,
    pitfalls: [
      "缺少 line_start 且 function_name 无法定位时会失败。",
      "path_found=false 不等于漏洞不存在，需结合代码证据复核。",
      "同一失败输入连续重试会被执行层抑制，应改参数。",
    ],
  },
  {
    id: "create_vulnerability_report",
    category: "报告与协作编排",
    summary: `创建正式的漏洞报告。这是记录已确认漏洞的唯一方式。`,
    goal: "在 verification 阶段支撑审计编排和结果产出。",
    taskList: [
      "协助 Agent 制定下一步行动。",
      "沉淀中间结论与可追溯信息。",
      "保障任务收敛与结果可交付性。",
    ],
    inputChecklist: [
      "`title` (string, required): 漏洞标题",
      "`vulnerability_type` (string, required): 漏洞类型: sql_injection, xss, ssrf, command_injection, path_traversal, idor, auth_bypass, etc.",
      "`severity` (string, required): 严重程度: critical, high, medium, low, info",
      "`description` (string, required): 漏洞详细描述",
      "`file_path` (string, required): 漏洞所在文件路径",
      "`line_start` (any, optional): 起始行号",
      "`line_end` (any, optional): 结束行号",
      "`code_snippet` (any, optional): 相关代码片段",
      "`source` (any, optional): 污点来源（用户输入点）",
      "`sink` (any, optional): 危险函数（漏洞触发点）",
      "`poc` (any, optional): 概念验证/利用方法",
      "`impact` (any, optional): 影响分析",
      "`recommendation` (any, optional): 修复建议",
      "`confidence` (number, optional): 置信度 0.0-1.0",
      "`cwe_id` (any, optional): CWE编号",
      "`cvss_score` (any, optional): CVSS评分",
    ],
    exampleInput: `\`\`\`json
{
  "title": "<text>",
  "vulnerability_type": "<text>",
  "severity": "<text>",
  "description": "<text>",
  "file_path": "<text>"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "dataflow_analysis",
    category: "可达性与逻辑分析",
    summary: `分析 Source -> Sink 传播链路，输出结构化流证据（source_nodes/sink_nodes/sanitizers/taint_steps/risk_level）。支持 source_code 或 file_path 自动读取。`,
    goal: "沉淀可复用的数据流证据，支撑 verification 对真实性与可达性的判断。",
    taskList: [
      "识别 Source 节点、Sink 节点与净化节点。",
      "生成 taint_steps/evidence_lines/confidence。",
      "对 C/C++ 内存类风险（strcpy/sprintf/memcpy）给出明确提示。",
    ],
    inputChecklist: [
      "`source_code` (string, optional): 包含数据源的代码",
      "`sink_code` (any, optional): 包含数据汇的代码（如危险函数）",
      "`variable_name` (string, optional): 要追踪的变量名，默认 user_input",
      "`file_path` (string, optional): 文件路径",
      "`start_line` (any, optional): 起始行（file_path 模式）",
      "`end_line` (any, optional): 结束行（file_path 模式）",
      "`source_hints` (any, optional): Source 提示",
      "`sink_hints` (any, optional): Sink 提示",
      "`language` (any, optional): 语言提示",
      "`max_hops` (integer, optional): 污点传播步数上限",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "src/time64.c",
  "start_line": 120,
  "end_line": 220,
  "variable_name": "result",
  "sink_hints": ["sprintf", "strcpy"],
  "max_hops": 6
}
\`\`\``,
    pitfalls: [
      "source_code 为空时，file_path 不可读会直接失败。",
      "仅凭该工具输出不能直接落库，需结合 read_file 和验证证据。",
      "遇到同一输入重复失败，应改参数或切换 controlflow_analysis_light。",
    ],
  },
  {
    id: "extract_function",
    category: "代码读取与定位",
    summary: `从源文件中提取指定函数的代码`,
    goal: "定位目标代码、函数上下文与证据位置。",
    taskList: [
      "读取代码文件并定位行号上下文。",
      "快速检索关键词并筛选有效命中。",
      "提取函数级上下文供后续验证链路使用。",
    ],
    inputChecklist: [
      "`file_path` (string, required): 源文件路径",
      "`function_name` (string, required): 要提取的函数名",
      "`include_imports` (boolean, optional): 是否包含 import 语句",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "<text>",
  "function_name": "<text>",
  "include_imports": true
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "function_context",
    category: "代码读取与定位",
    summary: `查找函数的上下文信息，包括定义、调用者和被调用的函数。
用于追踪数据流和理解函数的使用方式。`,
    goal: "定位目标代码、函数上下文与证据位置。",
    taskList: [
      "读取代码文件并定位行号上下文。",
      "快速检索关键词并筛选有效命中。",
      "提取函数级上下文供后续验证链路使用。",
    ],
    inputChecklist: [
      "`function_name` (string, required): 函数名称",
      "`file_path` (any, optional): 文件路径",
      "`include_callers` (boolean, optional): 是否包含调用者",
      "`include_callees` (boolean, optional): 是否包含被调用的函数",
    ],
    exampleInput: `\`\`\`json
{
  "function_name": "<text>",
  "file_path": null,
  "include_callers": true
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "get_vulnerability_knowledge",
    category: "候选发现与模式扫描",
    summary: `获取特定漏洞类型的完整专业知识。`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`vulnerability_type` (string, required): 漏洞类型，如: sql_injection, xss, command_injection, path_traversal, ssrf, deserialization, hardcoded_secrets, auth_bypass",
      "`project_language` (any, optional): 目标项目的主要编程语言（如 python, php, javascript, rust, go），用于过滤相关示例",
    ],
    exampleInput: `\`\`\`json
{
  "vulnerability_type": "<text>",
  "project_language": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "joern_reachability_verify",
    category: "可达性与逻辑分析",
    summary: `使用 Joern 对高危候选执行深度可达性复核，输出控制流/数据流证据。`,
    goal: "判断漏洞是否可达、是否受逻辑/授权路径约束。",
    taskList: [
      "分析源到汇的数据流链路。",
      "计算控制流可达路径与关键条件。",
      "验证授权边界和业务逻辑约束。",
    ],
    inputChecklist: [
      "`file_path` (string, required): 目标文件路径",
      "`line_start` (integer, required): 目标起始行",
      "`call_chain` (any, optional): 已有调用链",
      "`control_conditions` (any, optional): 已有控制条件",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "<text>",
  "line_start": 1,
  "call_chain": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "list_files",
    category: "代码读取与定位",
    summary: `列出目录中的文件。`,
    goal: "定位目标代码、函数上下文与证据位置。",
    taskList: [
      "读取代码文件并定位行号上下文。",
      "快速检索关键词并筛选有效命中。",
      "提取函数级上下文供后续验证链路使用。",
    ],
    inputChecklist: [
      "`directory` (string, optional): 目录路径（相对于项目根目录）",
      "`pattern` (any, optional): 文件名模式，如 *.py",
      "`recursive` (boolean, optional): 是否递归列出子目录",
      "`max_files` (integer, optional): 最大文件数",
    ],
    exampleInput: `\`\`\`json
{
  "directory": ".",
  "pattern": null,
  "recursive": false
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "logic_authz_analysis",
    category: "可达性与逻辑分析",
    summary: `逻辑漏洞图规则分析：检查 route/handler 到资源访问路径上的认证、授权、对象级权限(IDOR)与作用域一致性。`,
    goal: "判断漏洞是否可达、是否受逻辑/授权路径约束。",
    taskList: [
      "分析源到汇的数据流链路。",
      "计算控制流可达路径与关键条件。",
      "验证授权边界和业务逻辑约束。",
    ],
    inputChecklist: [
      "`file_path` (any, optional): 目标文件路径",
      "`line_start` (any, optional): 目标行号",
      "`vulnerability_type` (any, optional): 漏洞类型",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": null,
  "line_start": null,
  "vulnerability_type": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "pattern_match",
    category: "候选发现与模式扫描",
    summary: `🔍 快速扫描代码中的危险模式和常见漏洞。`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`code` (any, optional): 要扫描的代码内容（与 scan_file 二选一）",
      "`scan_file` (any, optional): 要扫描的文件路径（相对于项目根目录，与 code 二选一）",
      "`file_path` (string, optional): 文件路径（用于上下文）",
      "`pattern_types` (any, optional): 要检测的漏洞类型列表，如 ['sql_injection', 'xss']。为空则检测所有类型",
      "`language` (any, optional): 编程语言，用于选择特定模式",
    ],
    exampleInput: `\`\`\`json
{
  "code": null,
  "scan_file": null,
  "file_path": "unknown"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "query_security_knowledge",
    category: "候选发现与模式扫描",
    summary: `查询安全知识库，获取漏洞类型、检测方法、修复建议等专业知识。`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`query` (string, required): 搜索查询，如漏洞类型、技术名称、安全概念等",
      "`category` (any, optional): 知识类别过滤: vulnerability, best_practice, remediation, code_pattern, compliance",
      "`top_k` (integer, optional): 返回结果数量",
    ],
    exampleInput: `\`\`\`json
{
  "query": "<text>",
  "category": null,
  "top_k": 3
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "quick_audit",
    category: "候选发现与模式扫描",
    summary: `快速文件审计工具 - 对单个文件进行全面安全分析`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`file_path` (string, required): 要审计的文件路径",
      "`deep_analysis` (boolean, optional): 是否进行深度分析（包括上下文和数据流分析）",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "<text>",
  "deep_analysis": true
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "rag_query",
    category: "候选发现与模式扫描",
    summary: `在代码库中进行语义搜索。
使用场景:
- 查找特定功能的实现代码
- 查找调用某个函数的代码
- 查找处理用户输入的代码
- 查找数据库操作相关代码
- 查找认证/授权相关代码`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`query` (string, required): 搜索查询，描述你要找的代码功能或特征",
      "`top_k` (integer, optional): 返回结果数量",
      "`file_path` (any, optional): 限定搜索的文件路径",
      "`language` (any, optional): 限定编程语言",
    ],
    exampleInput: `\`\`\`json
{
  "query": "<text>",
  "top_k": 10,
  "file_path": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "read_file",
    category: "代码读取与定位",
    summary: `读取项目中的文件内容。`,
    goal: "定位目标代码、函数上下文与证据位置。",
    taskList: [
      "读取代码文件并定位行号上下文。",
      "快速检索关键词并筛选有效命中。",
      "提取函数级上下文供后续验证链路使用。",
    ],
    inputChecklist: [
      "`file_path` (string, required): 文件路径（相对于项目根目录）",
      "`start_line` (any, optional): 起始行号（从1开始）",
      "`end_line` (any, optional): 结束行号",
      "`max_lines` (integer, optional): 最大返回行数",
    ],
    exampleInput: `\`\`\`json
{
  "file_path": "<text>",
  "start_line": null,
  "end_line": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "reflect",
    category: "报告与协作编排",
    summary: `反思工具。用于回顾当前的分析进展：
1. 总结已经发现的问题
2. 评估当前分析的覆盖度
3. 识别可能遗漏的方向
4. 决定是否需要调整策略`,
    goal: "在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。",
    taskList: [
      "协助 Agent 制定下一步行动。",
      "沉淀中间结论与可追溯信息。",
      "保障任务收敛与结果可交付性。",
    ],
    inputChecklist: [
      "无显式参数（工具内部处理）。",
    ],
    exampleInput: `\`\`\`json
{}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "search_code",
    category: "代码读取与定位",
    summary: `在项目代码中搜索关键字或模式。`,
    goal: "定位目标代码、函数上下文与证据位置。",
    taskList: [
      "读取代码文件并定位行号上下文。",
      "快速检索关键词并筛选有效命中。",
      "提取函数级上下文供后续验证链路使用。",
    ],
    inputChecklist: [
      "`keyword` (string, required): 搜索关键字或正则表达式",
      "`file_pattern` (any, optional): 文件名模式，如 *.py, *.js",
      "`directory` (any, optional): 搜索目录（相对路径）",
      "`case_sensitive` (boolean, optional): 是否区分大小写",
      "`max_results` (integer, optional): 最大结果数",
      "`is_regex` (boolean, optional): 是否使用正则表达式",
    ],
    exampleInput: `\`\`\`json
{
  "keyword": "<text>",
  "file_pattern": null,
  "directory": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "security_search",
    category: "候选发现与模式扫描",
    summary: `搜索可能存在安全漏洞的代码。
专门针对特定漏洞类型进行搜索。`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`vulnerability_type` (string, required): 漏洞类型: sql_injection, xss, command_injection, path_traversal, ssrf, deserialization, auth_bypass, hardcoded_secret",
      "`top_k` (integer, optional): 返回结果数量",
    ],
    exampleInput: `\`\`\`json
{
  "vulnerability_type": "<text>",
  "top_k": 20
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "smart_scan",
    category: "候选发现与模式扫描",
    summary: `🚀 智能批量安全扫描工具 - 一次调用完成多项检查`,
    goal: "快速发现候选漏洞与高风险模式。",
    taskList: [
      "批量扫描候选风险点。",
      "按漏洞类型或语义检索相关代码。",
      "为后续验证阶段提供优先级线索。",
    ],
    inputChecklist: [
      "`target` (string, optional): 扫描目标：可以是目录路径、文件路径或文件模式（如 '*.py'）",
      "`scan_types` (any, optional): 扫描类型列表。可选: pattern, secret, dependency, all。默认为 all",
      "`focus_vulnerabilities` (any, optional): 重点关注的漏洞类型，如 ['sql_injection', 'xss', 'command_injection']",
      "`max_files` (integer, optional): 最大扫描文件数",
      "`quick_mode` (boolean, optional): 快速模式：只扫描高风险文件",
    ],
    exampleInput: `\`\`\`json
{
  "target": ".",
  "scan_types": null,
  "focus_vulnerabilities": null
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_command_injection",
    category: "漏洞验证与 PoC 规划",
    summary: `专门测试命令注入漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`param_name` (string, optional): 注入参数名",
      "`test_command` (string, optional): 测试命令: id, whoami, echo test, cat /etc/passwd",
      "`language` (string, optional): 语言: auto, php, python, javascript, java, go, ruby, shell",
      "`injection_point` (any, optional): 注入点描述，如 'shell_exec($_GET[cmd])'",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "param_name": "cmd",
  "test_command": "id"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_deserialization",
    category: "漏洞验证与 PoC 规划",
    summary: `测试不安全反序列化漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`language` (string, optional): 语言: auto, php, python, java, ruby",
      "`payload_type` (string, optional): payload 类型: detect, pickle, yaml, php_serialize",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "language": "auto",
  "payload_type": "detect"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_path_traversal",
    category: "漏洞验证与 PoC 规划",
    summary: `专门测试路径遍历/LFI/RFI 漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`param_name` (string, optional): 文件参数名",
      "`payload` (string, optional): 路径遍历 payload",
      "`language` (string, optional): 语言",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "param_name": "file",
  "payload": "../../../etc/passwd"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_sql_injection",
    category: "漏洞验证与 PoC 规划",
    summary: `专门测试 SQL 注入漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`param_name` (string, optional): 注入参数名",
      "`payload` (string, optional): SQL 注入 payload",
      "`language` (string, optional): 语言: auto, php, python, javascript, java, go, ruby",
      "`db_type` (string, optional): 数据库类型: mysql, postgresql, sqlite, oracle, mssql",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "param_name": "id",
  "payload": "1' OR '1'='1"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_ssti",
    category: "漏洞验证与 PoC 规划",
    summary: `专门测试 SSTI (服务端模板注入) 漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`param_name` (string, optional): 注入参数名",
      "`payload` (string, optional): SSTI payload",
      "`template_engine` (string, optional): 模板引擎: auto, jinja2, twig, freemarker, velocity, smarty",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "param_name": "name",
  "payload": "{{7*7}}"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "test_xss",
    category: "漏洞验证与 PoC 规划",
    summary: `专门测试 XSS (跨站脚本) 漏洞的工具。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`param_name` (string, optional): 注入参数名",
      "`payload` (string, optional): XSS payload",
      "`xss_type` (string, optional): XSS 类型: reflected, stored, dom",
      "`language` (string, optional): 语言: auto, php, python, javascript",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "param_name": "input",
  "payload": "<script>alert('XSS')</script>"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "think",
    category: "报告与协作编排",
    summary: `深度思考工具。用于：
1. 分析复杂的代码逻辑或安全问题
2. 规划下一步的分析策略
3. 评估发现的漏洞是否真实存在
4. 决定是否需要深入调查某个方向`,
    goal: "在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。",
    taskList: [
      "协助 Agent 制定下一步行动。",
      "沉淀中间结论与可追溯信息。",
      "保障任务收敛与结果可交付性。",
    ],
    inputChecklist: [
      "`thought` (string, required): 思考内容，可以是分析、规划、评估等",
      "`category` (any, optional): 思考类别: analysis(分析), planning(规划), evaluation(评估), decision(决策)",
    ],
    exampleInput: `\`\`\`json
{
  "thought": "<text>",
  "category": "general"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
  {
    id: "universal_vuln_test",
    category: "漏洞验证与 PoC 规划",
    summary: `通用漏洞测试工具，支持多种漏洞类型的自动化测试。`,
    goal: "执行非武器化验证步骤并收集可复现实验信号。",
    taskList: [
      "构造安全可控的测试输入。",
      "观察返回、日志与行为差异。",
      "输出验证结果与证据摘要。",
    ],
    inputChecklist: [
      "`target_file` (string, required): 目标文件路径",
      "`vuln_type` (string, required): 漏洞类型: command_injection, sql_injection, xss, path_traversal, ssti, deserialization",
      "`param_name` (string, optional): 参数名",
      "`payload` (any, optional): 自定义 payload",
      "`language` (string, optional): 语言",
    ],
    exampleInput: `\`\`\`json
{
  "target_file": "<text>",
  "vuln_type": "<text>",
  "param_name": "input"
}
\`\`\``,
    pitfalls: [
      "不要在输入缺失关键参数时盲目调用。",
      "不要将该工具输出直接当作最终结论，必须结合上下文复核。",
      "不要在权限不足或路径不合法时重复重试同一输入。",
    ],
  },
];

const REMOVED_SKILL_IDS = new Set<string>([
  "test_command_injection",
  "test_deserialization",
  "test_path_traversal",
  "test_sql_injection",
  "test_ssti",
  "test_xss",
  "universal_vuln_test",
]);

export const SKILL_TOOLS_CATALOG: SkillToolCatalogItem[] =
  SKILL_TOOLS_CATALOG_RAW.filter((item) => !REMOVED_SKILL_IDS.has(item.id));

export function buildSkillToolPrompt(tool: SkillToolCatalogItem): string {
  const taskLines = tool.taskList.map((item) => `- ${item}`).join("\n");
  const inputLines = tool.inputChecklist.map((item) => `- ${item}`).join("\n");
  return [
    `你是智能审计 Agent，请调用工具 \`${tool.id}\` 完成分析。`,
    `审计目标：${tool.goal}`,
    "适用任务：",
    taskLines,
    "调用前准备参数：",
    inputLines,
    "输出要求：",
    "1) 给出本次调用的证据位置（文件/函数/行号）。",
    "2) 输出结构化结论（风险等级、可利用性、影响范围）。",
    "3) 说明下一步动作（继续验证/补充证据/转入报告）。",
    "4) 调用失败时，返回可重试参数或替代工具建议。",
  ].join("\n");
}
