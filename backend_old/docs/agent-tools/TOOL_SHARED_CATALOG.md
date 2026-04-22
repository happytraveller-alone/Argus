# TOOL_SHARED_CATALOG

> 2026-04-18 更新：本文提到的 `business_logic_recon` / `business_logic_analysis` Python agent 阶段说明已退役，仅保留为历史工具目录参考；当前 authoritative 迁移状态以 `plan/rust_full_takeover/*` 为准。

该目录按“目标 -> 推荐工具 -> 可完成任务 -> 反例/误用”汇总运行时工具能力。

## 代码读取与定位
- 工具: `get_symbol_body`
  - 目标: 定位目标代码、函数上下文与证据位置。
  - 推荐任务: 读取代码文件并定位行号上下文。；快速检索关键词并筛选有效命中。；提取函数级上下文供后续验证链路使用。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `list_files`
  - 目标: 定位目标代码、函数上下文与证据位置。
  - 推荐任务: 读取代码文件并定位行号上下文。；快速检索关键词并筛选有效命中。；提取函数级上下文供后续验证链路使用。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `search_code`
  - 目标: 定位目标代码、函数上下文与证据位置。
  - 推荐任务: 读取代码文件并定位行号上下文。；快速检索关键词并筛选有效命中。；提取函数级上下文供后续验证链路使用。
  - 反例/误用: 在无有效输入或无证据时直接下结论。

## 候选发现与模式扫描
- 工具: `pattern_match`
  - 目标: 快速发现候选漏洞与高风险模式。
  - 推荐任务: 批量扫描候选风险点。；按漏洞类型或语义检索相关代码。；为后续验证阶段提供优先级线索。
  - 反例/误用: 在无有效输入或无证据时直接下结论。

## 可达性与逻辑分析
- 工具: `controlflow_analysis_light`
  - 目标: 基于文件与定位点分析控制流可达性、分支条件与入口约束。
  - 推荐任务: 计算入口到目标点的调用链与 path_score。；识别阻断原因（如路径不可达、依赖缺失）。；验证权限分支/状态机分支是否可绕过。
  - 关键输入: `file_path` + `line_start/line_end`（可选 `function_name/entry_points/call_chain_hint`）。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `dataflow_analysis`
  - 目标: 追踪污点从 Source 到 Sink 的传播链路，评估净化与污染路径。
  - 推荐任务: 识别 source/sink 节点与 taint_steps。；判断是否存在净化器与绕过路径。；输出数据流证据供后续验证/报告使用。
  - 关键输入: `source_code`（或 `file_path`）+ `variable_name`（可选 `sink_code/start_line/end_line/source_hints/sink_hints`）。
  - 反例/误用: 在无有效输入或无证据时直接下结论。

## 漏洞验证与 PoC 规划
- 暂无工具映射。

## 报告与协作编排
- 工具: `get_code_window`
  - 目标: 在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `get_file_outline`
  - 目标: 在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `get_function_summary`
  - 目标: 在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `locate_enclosing_function`
  - 目标: 在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `run_code`
  - 目标: 在 verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `sandbox_exec`
  - 目标: 在 verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。
- 工具: `verify_vulnerability`
  - 目标: 在 verification 阶段支撑审计编排和结果产出。
  - 推荐任务: 协助 Agent 制定下一步行动。；沉淀中间结论与可追溯信息。；保障任务收敛与结果可交付性。
  - 反例/误用: 在无有效输入或无证据时直接下结论。

## 工具全量索引
- `controlflow_analysis_light`
- `dataflow_analysis`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `list_files`
- `locate_enclosing_function`
- `pattern_match`
- `run_code`
- `sandbox_exec`
- `search_code`
- `verify_vulnerability`
