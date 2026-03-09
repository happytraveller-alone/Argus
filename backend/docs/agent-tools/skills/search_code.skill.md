# Skill: search_code

## 目标
- 快速定位证据行，作为 `read_file` 锚点来源。
- 为 `controlflow_analysis_light` 提供 `file_path:line` 级输入。

## 路由关键事实
- `search_code` 现在优先走 `filesystem/search_files`。
- 公共 `action_input` 仍使用 `keyword`，不要发明额外字段名。
- `search_code` 只负责定位，不负责自动展开文件上下文。

## 输入契约
- 必填: `keyword`。
- 可选: `directory`, `file_pattern`, `is_regex`, `max_results`。
- 推荐总是携带窄范围约束，减少无效命中和 token 消耗。

## 推荐调用链
1. `search_code` 获取 `file:line`。
2. `read_file` 做窗口化验证。
3. `controlflow_analysis_light` 使用 `file_path:line` 或显式 `line_start`。
4. 必要时补 `locate_enclosing_function`。

## 精确工作流
1. 关键词优先级：函数名/常量名 > 漏洞 sink > 泛词。
2. 优先缩小范围：总是尽量携带 `directory` + `file_pattern`。
3. 命中后立即提取首个可信 `file_path:line`，用于后续 `read_file`。
4. 若无命中，先缩小范围重试一次；连续失败则切换到 `list_files -> read_file`。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。
- 不要把 `search_code` 当作自动读文件工具。

## 最小示例
```json
{
  "tool": "search_code",
  "action_input": {
    "keyword": "TM64_ASCTIME_FORMAT",
    "directory": "src",
    "file_pattern": "time64*",
    "max_results": 8
  }
}
```
