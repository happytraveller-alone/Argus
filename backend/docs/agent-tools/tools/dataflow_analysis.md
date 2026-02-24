# Tool: `dataflow_analysis`

## Tool Purpose
分析变量从 Source 到 Sink 的传播链路，输出可复用的数据流证据。

## Goal
为验证阶段提供稳定的流证据：`source_nodes/sink_nodes/sanitizers/taint_steps/risk_level`。

## Inputs
- `source_code` (string, optional): 要分析的源码片段。
- `sink_code` (string, optional): 候选汇点代码片段。
- `variable_name` (string, optional): 追踪变量名，默认 `user_input`。
- `file_path` (string, optional): 源码文件路径（`source_code` 为空时可自动读取）。
- `start_line` (integer, optional): 文件片段起始行。
- `end_line` (integer, optional): 文件片段结束行。
- `source_hints` (array[string], optional): Source 语义提示。
- `sink_hints` (array[string], optional): Sink 语义提示。
- `language` (string, optional): 编程语言提示。
- `max_hops` (integer, optional): 传播步数上限（1-20，默认 5）。

## Example Input
```json
{
  "file_path": "src/time64.c",
  "start_line": 120,
  "end_line": 220,
  "variable_name": "result",
  "sink_hints": ["sprintf", "strcpy"],
  "max_hops": 6
}
```

## Outputs
- `metadata.analysis.source_nodes` (array[string])
- `metadata.analysis.sink_nodes` (array[string])
- `metadata.analysis.sanitizers` (array[string])
- `metadata.analysis.taint_steps` (array[string])
- `metadata.analysis.risk_level` (high|medium|low|none)
- `metadata.analysis.confidence` (float, 0-1)
- `metadata.analysis.evidence_lines` (array[int])
- `metadata.analysis.next_actions` (array[string])

## Trigger Guidance
- 已定位到函数/代码片段，需要验证 Source->Sink 是否成立。
- 发现内存相关敏感调用（如 `strcpy/sprintf/memcpy`）需要补充边界风险证据。

## Pitfalls
- `source_code` 为空且 `file_path` 不可读会直接失败。
- 仅凭该工具结论不能直接落库，仍需结合 `read_file` 与验证证据。
- 同一输入重复失败时应改参数或切换 `controlflow_analysis_light`。
