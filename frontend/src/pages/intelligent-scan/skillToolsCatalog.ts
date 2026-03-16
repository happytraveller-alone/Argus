export type SkillToolCategory =
  | "模型基础增强类"
  | "代码读取与定位"
  | "候选发现与模式扫描"
  | "可达性与逻辑分析"
  | "漏洞验证与 PoC 规划"
  | "报告与协作编排";

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
  "模型基础增强类",
  "代码读取与定位",
  "候选发现与模式扫描",
  "可达性与逻辑分析",
  "漏洞验证与 PoC 规划",
  "报告与协作编排",
];

export const SKILL_TOOLS_CATALOG: SkillToolCatalogItem[] = [
  {
    id: "smart_scan",
    category: "模型基础增强类",
    summary: "智能扫描入口，快速定位高风险代码区域。",
    goal: "建立高价值候选集合，缩小后续分析范围。",
    taskList: ["执行整体扫描", "输出高风险区域", "给出下一步建议"],
    inputChecklist: ["`target_path` (string, required): 扫描根路径"],
    exampleInput: "```json\n{\n  \"target_path\": \".\"\n}\n```",
    pitfalls: ["不要把 smart_scan 结果直接当成最终漏洞结论。"],
  },
  {
    id: "quick_audit",
    category: "模型基础增强类",
    summary: "轻量快速审计，优先输出高信号检查点。",
    goal: "在较短时间内建立初步风险画像。",
    taskList: ["执行快速审计", "输出关键候选", "标记优先级"],
    inputChecklist: ["`target_path` (string, optional): 目标路径"],
    exampleInput: "```json\n{\n  \"target_path\": \".\"\n}\n```",
    pitfalls: ["不要在需要完整证据链时只停留在 quick_audit。"],
  },
  {
    id: "read_file",
    category: "代码读取与定位",
    summary: "窗口化读取代码并返回按行结构化证据。",
    goal: "获取真实代码窗口、焦点行和附近逻辑，供前端代码证据卡片渲染。",
    taskList: ["读取目标片段", "返回行号窗口", "高亮焦点行"],
    inputChecklist: [
      "`file_path` (string, required): 目标文件路径",
      "`start_line` / `end_line` (number, optional): 窗口范围",
    ],
    exampleInput: "```json\n{\n  \"file_path\": \"src/app.py\"\n}\n```",
    pitfalls: ["不要无锚点大段读取整个项目。", "优先传入窗口范围，避免生成超长代码块。"],
  },
  {
    id: "list_files",
    category: "代码读取与定位",
    summary: "列出候选目录和文件。",
    goal: "缩小扫描范围并定位相关代码。",
    taskList: ["列出目录", "筛选候选文件", "返回相对路径"],
    inputChecklist: ["`directory` (string, optional): 目录", "`pattern` (string, optional): 匹配模式"],
    exampleInput: "```json\n{\n  \"directory\": \"src\",\n  \"pattern\": \"*.py\"\n}\n```",
    pitfalls: ["不要把 list_files 当作全文代码搜索。"],
  },
  {
    id: "search_code",
    category: "代码读取与定位",
    summary: "通过 `rg/grep/python fallback` 检索代码并返回按行命中证据。",
    goal: "快速定位证据点、调用链入口和可继续阅读的命中窗口。",
    taskList: ["检索关键字", "返回命中窗口", "标注 file_path:line 证据锚点"],
    inputChecklist: [
      "`keyword` (string, required): 搜索内容",
      "`directory` (string, optional): 搜索目录",
      "`file_pattern` (string, optional): 文件模式",
    ],
    exampleInput:
      "```json\n{\n  \"keyword\": \"dangerous_call\",\n  \"directory\": \"src\",\n  \"file_pattern\": \"*.ts\"\n}\n```",
    pitfalls: ["不要只凭搜索命中就下结论。", "命中后应继续使用 read_file 读取完整窗口。"],
  },
  {
    id: "extract_function",
    category: "代码读取与定位",
    summary: "提取函数/符号主体，并返回可渲染的函数级代码证据。",
    goal: "围绕目标函数建立完整分析上下文，并沉淀函数窗口证据。",
    taskList: ["定位函数", "提取函数体", "返回函数级代码窗口", "标注符号名与行号"],
    inputChecklist: ["`file_path` (string, required): 文件路径", "`function_name` (string, optional): 函数名"],
    exampleInput: "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"function_name\": \"asctime64_r\"\n}\n```",
    pitfalls: ["缺少函数定位信息时，优先先用 search_code/read_file 补证。"],
  },
  {
    id: "pattern_match",
    category: "候选发现与模式扫描",
    summary: "基于规则/模式快速筛查危险代码。",
    goal: "补充发现高风险候选与交叉验证。",
    taskList: ["匹配危险模式", "输出命中位置", "给出风险说明"],
    inputChecklist: ["`pattern` (string, required): 模式或规则"],
    exampleInput: "```json\n{\n  \"pattern\": \"eval\\(\"\n}\n```",
    pitfalls: ["不要让模式匹配替代可达性或动态验证。"],
  },
  {
    id: "dataflow_analysis",
    category: "可达性与逻辑分析",
    summary: "分析 Source -> Sink 的传播链。",
    goal: "沉淀结构化流证据，支撑真实性判断。",
    taskList: ["识别 source/sink", "输出传播步骤", "标记风险等级"],
    inputChecklist: ["`file_path` (string, required): 文件路径", "`start_line` (number, optional): 起始行"],
    exampleInput: "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"start_line\": 120\n}\n```",
    pitfalls: ["不要把数据流结果直接当成最终确认。"],
  },
  {
    id: "controlflow_analysis_light",
    category: "可达性与逻辑分析",
    summary: "分析控制流、条件分支与可达性。",
    goal: "验证候选漏洞是否真实可触达。",
    taskList: ["定位目标函数", "分析调用链", "输出 blocked reasons"],
    inputChecklist: ["`file_path` (string, required): 文件路径", "`function_name` (string, optional): 函数名"],
    exampleInput: "```json\n{\n  \"file_path\": \"src/time64.c\",\n  \"function_name\": \"asctime64_r\"\n}\n```",
    pitfalls: ["path_found=false 不等于漏洞不存在。"],
  },
  {
    id: "logic_authz_analysis",
    category: "可达性与逻辑分析",
    summary: "分析认证、授权与业务逻辑约束。",
    goal: "识别鉴权漏洞、越权与边界失效。",
    taskList: ["识别鉴权点", "分析边界条件", "输出授权风险"],
    inputChecklist: ["`file_path` (string, required): 文件路径"],
    exampleInput: "```json\n{\n  \"file_path\": \"src/auth/controller.py\"\n}\n```",
    pitfalls: ["不要忽略业务前置条件和角色边界。"],
  },
  {
    id: "run_code",
    category: "漏洞验证与 PoC 规划",
    summary: "运行 Harness/PoC，返回结构化执行证据。",
    goal: "用非武器化方式验证候选漏洞，并保留执行命令、退出码、输出摘要与执行代码。",
    taskList: ["编写 Harness", "执行验证", "输出执行摘要", "保留可回看的代码与输出证据"],
    inputChecklist: ["`code` (string, required): 待执行代码", "`language` (string, optional): 语言"],
    exampleInput: "```json\n{\n  \"language\": \"python\",\n  \"code\": \"print(1)\"\n}\n```",
    pitfalls: ["不要在缺少隔离前提时执行高风险 payload。"],
  },
  {
    id: "sandbox_exec",
    category: "漏洞验证与 PoC 规划",
    summary: "在隔离沙箱中执行命令，并返回结构化执行证据。",
    goal: "验证运行时行为、环境差异与命令执行证据，直观展示命令、退出码与输出结果。",
    taskList: ["执行命令", "采集输出", "记录实验条件", "返回执行摘要与输出证据"],
    inputChecklist: ["`command` (string, required): 命令文本"],
    exampleInput: "```json\n{\n  \"command\": \"echo hello\"\n}\n```",
    pitfalls: ["不要把沙箱输出脱离代码证据单独解读。"],
  },
  {
    id: "verify_vulnerability",
    category: "漏洞验证与 PoC 规划",
    summary: "编排漏洞验证步骤并输出收敛结论。",
    goal: "统一管理验证过程与最终 verdict。",
    taskList: ["制定验证路径", "整合实验结果", "输出 verdict"],
    inputChecklist: ["`finding` (object, required): 待验证漏洞对象"],
    exampleInput: "```json\n{\n  \"finding\": {\n    \"file_path\": \"src/app.py\",\n    \"line_start\": 42\n  }\n}\n```",
    pitfalls: ["不要在证据不足时给出 confirmed。"],
  },
  {
    id: "create_vulnerability_report",
    category: "报告与协作编排",
    summary: "创建正式漏洞报告。",
    goal: "沉淀可交付结果与可追溯证据。",
    taskList: ["整理结论", "结构化报告", "输出修复建议"],
    inputChecklist: ["`title` (string, required): 标题", "`file_path` (string, required): 文件路径"],
    exampleInput: "```json\n{\n  \"title\": \"src/time64.c中asctime64_r栈溢出漏洞\",\n  \"file_path\": \"src/time64.c\"\n}\n```",
    pitfalls: ["不要在未完成验证时创建正式报告。"],
  },
  {
    id: "think",
    category: "报告与协作编排",
    summary: "分析、规划与决策工具。",
    goal: "帮助 Agent 明确下一步动作与取舍。",
    taskList: ["分析现状", "规划下一步", "输出决策理由"],
    inputChecklist: ["`thought` (string, required): 思考内容"],
    exampleInput: "```json\n{\n  \"thought\": \"先补代码证据，再做动态验证\"\n}\n```",
    pitfalls: ["不要把 think 输出当成最终证据。"],
  },
  {
    id: "reflect",
    category: "报告与协作编排",
    summary: "复盘、校验与策略调整工具。",
    goal: "避免无效重试并及时纠偏。",
    taskList: ["复盘失败原因", "校验当前假设", "调整执行策略"],
    inputChecklist: ["`thought` (string, required): 复盘内容"],
    exampleInput: "```json\n{\n  \"thought\": \"当前证据不足，需要先定位函数范围\"\n}\n```",
    pitfalls: ["不要在未回看错误信息时机械重试。"],
  },
];

export function buildSkillToolPrompt(tool: SkillToolCatalogItem): string {
  const taskLines = tool.taskList.map((item) => `- ${item}`).join("\n");
  const inputLines = tool.inputChecklist.map((item) => `- ${item}`).join("\n");
  return [
    `你是智能扫描 Agent，请调用工具 \`${tool.id}\` 完成分析。`,
    `扫描目标：${tool.goal}`,
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
