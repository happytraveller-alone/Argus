# Tool: `rag_query`

## Tool Purpose
在代码库中进行语义搜索。
使用场景:
- 查找特定功能的实现代码
- 查找调用某个函数的代码
- 查找处理用户输入的代码
- 查找数据库操作相关代码
- 查找认证/授权相关代码

输入: 
- query: 描述你要查找的代码，例如 "处理用户登录的函数"、"SQL查询执行"、"文件上传处理"
- top_k: 返回结果数量（默认10）
- file_path: 可选，限定在某个文件中搜索
- language: 可选，限定编程语言

输出: 相关的代码片段列表，包含文件路径、行号、代码内容和相似度分数

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `query` (string, required): 搜索查询，描述你要找的代码功能或特征
- `top_k` (integer, optional): 返回结果数量
- `file_path` (any, optional): 限定搜索的文件路径
- `language` (any, optional): 限定编程语言


### Example Input
```json
{
  "query": "<text>",
  "top_k": 10,
  "file_path": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“快速发现候选漏洞与高风险模式。”时触发。
- 常见阶段: `analysis`。
- 分类: `候选发现与模式扫描`。
- 可选工具: `是`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
