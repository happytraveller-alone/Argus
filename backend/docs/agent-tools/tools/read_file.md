# Tool: `read_file`

## Tool Purpose
读取项目中的文件内容。

使用场景:
- 查看完整的源代码文件
- 查看特定行范围的代码
- 获取配置文件内容

输入:
- file_path: 文件路径（相对于项目根目录）
- start_line: 可选，起始行号
- end_line: 可选，结束行号
- max_lines: 最大返回行数（默认500）
- reason_paths: 可选，基于前序分析得到的优先目录/文件线索
- project_scope: 可选，是否启用全项目路径补全（默认 true）

执行要点:
- 先尝试原路径读取，再做全项目 suffix/basename 匹配。
- 对命中的候选按 `reason_paths` 优先级评分，自动选最可能文件。
- 有明确行号时优先 `sed -n`，头部读取优先 `head -n`，失败自动回退 Python 读取。

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `file_path` (string, required): 文件路径（相对于项目根目录）
- `start_line` (any, optional): 起始行号（从1开始）
- `end_line` (any, optional): 结束行号
- `max_lines` (integer, optional): 最大返回行数
- `reason_paths` (array, optional): 前序分析得到的候选目录/路径
- `project_scope` (boolean, optional): 是否启用全项目补全（默认 true）


### Example Input
```json
{
  "file_path": "<text>",
  "start_line": null,
  "end_line": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“定位目标代码、函数上下文与证据位置。”时触发。
- 常见阶段: `analysis, recon, verification`。
- 分类: `代码读取与定位`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
- 不要将项目外绝对路径作为有效输入；工具会按安全策略拒绝。
