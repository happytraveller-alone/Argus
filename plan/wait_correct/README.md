# Wait-Correct Migration Control Surface

用于 Rust 迁移期间的最小控制面，集中管理三类工件：

- `route-inventory/`：Python 端点盘点与迁移桶归类（`migrate/retire/defer/proxy`）
- `api-contract/`：Python vs Rust 合同对比结果与差异记录
- `non-api-python/`：`backend_old` 非 API Python 内核迁移总账
- `waves/`：每一波迁移的范围、门禁、完成状态

执行顺序建议：

1. 先运行 `scripts/migration/generate_python_route_inventory.py`
2. 再运行 `scripts/migration/api_contract_diff.py`
3. 把结果和结论落到当前 wave 文件中

执行纪律补充：

1. 每次只推进一个可验证的小迁移任务
2. 每个小任务完成后立刻单独提交
3. Rust 已接管的能力，要同步删除 Python live entry、失效 endpoint 或专属旧测试
4. 不能删除的 Python 代码，必须在对应 wave 中登记为 bridge，而不是默认保留
