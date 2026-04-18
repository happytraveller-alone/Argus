# Tool: `get_code_window`

> 2026-04-18 更新：本文中 `business_logic_recon` / `business_logic_analysis` 阶段标签属于历史 Python agent 文档语境，不再表示当前 live runtime ownership。当前 authoritative 迁移状态以 `plan/rust_full_takeover/*` 为准。

## Tool Purpose
围绕锚点返回极小代码窗口，用于取证和前端代码展示。

输入:
- file_path: 文件路径（相对于项目根目录）
- anchor_line: 锚点行号（从1开始）
- before_lines: 可选，向前读取的行数（默认2）
- after_lines: 可选，向后读取的行数（默认2）

## Goal
在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `file_path` (string, required): 文件路径（相对于项目根目录）
- `anchor_line` (integer, required): 锚点行号（从1开始）
- `before_lines` (integer, optional): 向前读取的行数
- `after_lines` (integer, optional): 向后读取的行数


### Example Input
```json
{
  "file_path": "<text>",
  "anchor_line": 1,
  "before_lines": 2
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。”时触发。
- 常见阶段: `analysis, business_logic_analysis, business_logic_recon, orchestrator, recon, report, verification`。
- 分类: `报告与协作编排`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
