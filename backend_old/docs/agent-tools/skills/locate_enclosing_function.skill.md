# Skill: locate_enclosing_function

## 目标
- 将命中行绑定到所属函数，补齐函数级证据。

## 输入契约
- 至少提供其一: `file_path` 或 `path`。
- 行号优先级: `line_start` > `line` > `file_path:line` / `path:line`。
- 稳定输出: `enclosing_function`, `symbols`, `resolution_method`, `resolution_engine`, `diagnostics`。

## 推荐调用链
1. `search_code` 找到命中行。
2. `locate_enclosing_function` 获取函数名与范围。
3. `read_file`/`extract_function` 深入验证。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"locate_enclosing_function","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
