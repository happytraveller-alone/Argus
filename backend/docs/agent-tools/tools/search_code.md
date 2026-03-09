# Tool: `search_code`

## Tool Purpose
在项目代码中搜索关键字或模式，并返回可继续阅读的命中位置。

使用场景:
- 查找特定函数的调用位置
- 搜索特定 API 的使用点
- 建立 `file_path:line` 级证据锚点

输入:
- keyword: 搜索关键字或正则表达式
- file_pattern: 可选，文件名模式（如 *.py）
- directory: 可选，搜索目录（相对于项目根目录）
- case_sensitive: 是否区分大小写
- is_regex: 是否使用正则表达式

## Execution Notes
- `search_code` 优先通过本地内容检索执行；不要绑定 `filesystem.search_files`，因为后者只支持路径 glob，不搜索文件内容。
- 它只负责定位，不负责自动展开文件窗口；命中后应立即调用 `read_file`。
- 想减少 token 消耗时，优先收窄 `directory` 与 `file_pattern`。

## Typical Triggers
- 当 Agent 需要快速建立 `file_path:line` 锚点时触发。
- 常见阶段: `analysis`, `recon`, `verification`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合 `read_file` 复核。
- 不要把它当作自动函数提取工具。
