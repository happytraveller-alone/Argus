# Skill: list_files

## 目标
- 确认目录结构与候选路径，不做大范围遍历。

## 输入契约
- 推荐: `directory`。
- 可选: `pattern`, `recursive`, `max_files`。

## 推荐调用链
1. `list_files` 确认路径存在。
2. `search_code` 精确定位关键词。
3. `read_file` 读取局部窗口。

## 禁止用法
- 不要在无有效输入时重复调用。
- 不要跳过定位步骤直接下结论。

## 最小示例
```json
{"tool":"list_files","note":"请按项目实际参数替换"}
```

## 失败恢复
- 先核对输入参数与路径范围。
- 必要时回到 `search_code -> read_file` 重新建立证据链。
