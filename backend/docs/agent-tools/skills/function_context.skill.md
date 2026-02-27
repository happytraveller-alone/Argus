# Skill: function_context

## 目标
- 保留函数上下文技能规范，执行时改用标准 MCP 工具名。

## 输入契约
- 兼容参数: `file_path`, `line_start`, `function_name`。
- 建议路径: `locate_enclosing_function + extract_function`。

## 推荐调用链
1. 先定位函数归属。
2. 再提取函数体。
3. 最后窗口化补证据。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"function_context","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
