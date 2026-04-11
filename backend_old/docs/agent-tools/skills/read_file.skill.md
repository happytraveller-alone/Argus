# Skill: read_file

## 目标
- 在已定位代码行附近读取最小必要上下文，形成可复核证据。

## 输入契约
- 必填: `file_path`, `start_line`, `end_line`。
- 严格模式: 禁止无锚点读取；必须先定位再读取。

## 推荐调用链
1. `search_code` 定位 `file_path:line`。
2. `read_file` 读取窗口 (`line-60` 到 `line+99`)。
3. 必要时补 `locate_enclosing_function`。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"read_file","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
