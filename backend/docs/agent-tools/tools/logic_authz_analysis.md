# Tool: `logic_authz_analysis`

## Tool Purpose
逻辑漏洞图规则分析：检查 route/handler 到资源访问路径上的认证、授权、对象级权限(IDOR)与作用域一致性。

## Goal
判断漏洞是否可达、是否受逻辑/授权路径约束。

## Task List
- 分析源到汇的数据流链路。
- 计算控制流可达路径与关键条件。
- 验证授权边界和业务逻辑约束。


## Inputs
- `file_path` (any, optional): 目标文件路径
- `line_start` (any, optional): 目标行号
- `vulnerability_type` (any, optional): 漏洞类型


### Example Input
```json
{
  "file_path": null,
  "line_start": null,
  "vulnerability_type": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“判断漏洞是否可达、是否受逻辑/授权路径约束。”时触发。
- 常见阶段: `analysis, verification`。
- 分类: `可达性与逻辑分析`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
