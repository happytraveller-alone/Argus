# Tool: `controlflow_analysis_light`

## Tool Purpose
轻量控制流/可达性分析：基于 tree-sitter + code2flow 推断调用链、控制条件和路径分值。

## Goal
给出可解释的可达性结论，作为验证阶段的 flow 证据门禁。

## Inputs
- `file_path` (string, required): 目标文件路径，支持 `file_path:line` 简写。
- `line_start` (integer, optional): 目标起始行。
- `line_end` (integer, optional): 目标结束行。
- `function_name` (string, optional): 缺少行号时用于函数定位。
- `severity` (string, optional): 漏洞严重度。
- `confidence` (float, optional): 置信度 0-1。
- `vulnerability_type` (string, optional): 漏洞类型。
- `entry_points` (array[string], optional): 入口函数候选。
- `entry_points_hint` (array[string], optional): 入口提示。
- `call_chain_hint` (array[string], optional): 调用链提示。
- `control_conditions_hint` (array[string], optional): 控制条件提示。

## Example Input
```json
{
  "file_path": "src/time64.c:168",
  "function_name": "asctime64_r",
  "severity": "high",
  "confidence": 0.88,
  "entry_points_hint": ["main"]
}
```

## Outputs
- `data.flow`: 路径证据（`path_found/path_score/call_chain/control_conditions/blocked_reasons`）
- `data.logic_authz`: 鉴权逻辑证据
- `metadata.summary`: `path_found/path_score/blocked_reasons/entry_inferred` 摘要

## Trigger Guidance
- 已有候选漏洞定位点，需要确认是否从入口可达。
- 高危候选准备进入 `confirmed` 前，补齐 flow 证据。

## Pitfalls
- 缺少 `line_start` 且无法由 `function_name` 定位时会失败。
- `path_found=false` 不等于漏洞不存在，需要结合代码证据与逻辑证据复核。
- 同一失败输入不应重复重试，需调整定位参数。
