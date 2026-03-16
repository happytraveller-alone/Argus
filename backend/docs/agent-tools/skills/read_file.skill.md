# Skill: read_file

## 目标
- 在已定位代码行附近读取最小必要上下文，形成可复核证据。
- 避免路径污染（如 `"(和其他多处)"`）导致 ENOENT 和误熔断。
- 当前由本地 `FileReadTool` 执行，不再依赖 filesystem MCP。

## 输入契约
- 标准: `file_path`, `start_line`, `end_line`（推荐同时传 `max_lines<=200`）。
- 兼容: `file_path` 可为 `path/to/file.py:123`，运行时会自动拆分行号。
- 严格模式: 禁止无锚点读取；必须先定位再读取。

## 推荐调用链
1. `search_code` 定位 `file_path:line`。
2. `read_file` 读取窗口 (`line-60` 到 `line+99`)。
3. 必要时补 `locate_enclosing_function`。

## 精确工作流
1. 先使用 `search_code` 找到首个可信命中。
2. 用命中行号构造窗口：`start_line=max(1,line-60)`、`end_line=min(line+99,start_line+199)`。
3. 若仅提供了 `file_path` 且无锚点，只允许头部窗口 `1..120` 做最小探测。
4. 若路径中出现附加说明（如 `src/a.c(和其他多处)`），只保留首个合法路径后再读取。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要把自然语言说明拼进 `file_path`。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{
  "tool": "read_file",
  "action_input": {
    "file_path": "src/time64.c",
    "start_line": 760,
    "end_line": 840,
    "max_lines": 120
  }
}
```

## 失败恢复
- `ENOENT/文件不存在`：优先视为业务输入错误，修正路径后重试，不做适配器熔断判断。
- `adapter unavailable/disconnect/timeout`：视为基础设施故障，触发熔断计数。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
