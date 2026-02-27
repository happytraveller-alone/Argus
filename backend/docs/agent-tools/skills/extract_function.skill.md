# Skill: extract_function

## 目标
- 提取函数体，支撑漏洞根因与修复分析。

## 输入契约
- 必填: `file_path`, `function_name`。

## 推荐调用链
1. `search_code` 定位函数符号。
2. `locate_enclosing_function` 确认范围。
3. `extract_function` 提取函数体。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"extract_function","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
