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
