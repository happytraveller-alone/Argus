# Skill: locate_enclosing_function

## 目标
- 通过本地轻量函数定位能力，将命中行绑定到所属函数，补齐函数级证据。

## 输入契约
- 必填: `file_path`。
- 推荐: `line_start`（或 `line`）。

## 推荐调用链
1. `search_code` 找到命中行。
2. `locate_enclosing_function` 获取函数名与范围。
3. `read_file` 或 `extract_function` 深入验证。

## 使用建议
- 只在已有 `file_path:line` 时调用，避免无锚点定位。
- 定位不到函数时，直接回退 `read_file`，不要反复盲试。

## 最小示例
```json
{"tool":"locate_enclosing_function","note":"请按项目实际参数替换"}
```
