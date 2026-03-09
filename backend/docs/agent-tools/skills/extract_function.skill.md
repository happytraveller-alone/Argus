# Skill: extract_function

## 目标
- 通过本地轻量函数提取能力拿到函数体，支撑漏洞根因与修复分析。

## 输入契约
- 必填: `file_path`, `function_name`。

## 推荐调用链
1. `search_code` 定位函数符号。
2. `locate_enclosing_function` 确认范围。
3. `extract_function` 提取函数体。
4. 必要时退回 `read_file` 做人工窗口校验。

## 使用建议
- 先有 `file_path` 再提取，不要拿模糊关键词直接调用。
- 提取失败时，优先回退到 `read_file`，不要重复同参重试。

## 最小示例
```json
{"tool":"extract_function","note":"请按项目实际参数替换"}
```
