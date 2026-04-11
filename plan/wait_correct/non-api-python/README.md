# Non-API Python Wait-Correct

这里记录 Rust 迁移期间，`backend_old` 非 API Python 存量的总账和阶段状态。

和 `route-inventory/` 的区别：

- `route-inventory/` 关心公开 HTTP 路由
- `non-api-python/` 关心后端内核 ownership

更新规则：

1. 先更新迁移计划文件：
   - `plan/backend_old_python_migration/2026-04-11-rust-backend-non-api-migration.md`
2. 再更新这里的 summary
3. 最后把该次迁移留下的 bridge / 未删项补进对应 `waves/*.md`

额外硬规则：

- 每个迁移小任务结束时，必须同步回答三个问题：
  - Rust 现在具体接管了什么
  - 对应 Python 哪些执行入口已经删除
  - 还有哪些 Python 代码仍然只是 bridge
- 如果回答不出第二条，就不算完成迁移，只算“增加了一份 Rust 实现”
