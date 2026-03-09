# Skill: list_files

## 目标
- 用本地轻量列举快速确认目录结构与候选路径，不做全文搜索。

## 输入契约
- 推荐: `directory`。
- 可选: `pattern`, `recursive`, `max_files`。

## 推荐调用链
1. `list_files` 确认路径存在。
2. `search_code` 精确定位关键词。
3. `read_file` 读取局部窗口。

## 使用建议
- 优先用它缩小路径范围，而不是替代 `search_code`。
- 大范围目录优先给 `pattern`，避免无意义遍历。

## 最小示例
```json
{"tool":"list_files","note":"请按项目实际参数替换"}
```
