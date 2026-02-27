# Skill: search_code

## 目标
- 快速定位证据行，作为 `read_file` 锚点来源。

## 输入契约
- 必填: `keyword`。
- 可选: `directory`, `file_pattern`, `is_regex`, `max_results`。

## 推荐调用链
1. `search_code` 获取 `file:line`。
2. `read_file` 做窗口化验证。
3. 必要时补 `locate_enclosing_function`。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"search_code","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
