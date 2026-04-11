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
