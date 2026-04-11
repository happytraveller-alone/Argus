# Rust 迁移控制工件（Worker A）

本次新增控制面位于 `plan/wait_correct/`，配套脚本位于 `scripts/migration/`。

## 1) 生成 Python 路由清单与分桶

在仓库根目录执行：

```bash
python3 scripts/migration/generate_python_route_inventory.py
```

输出：

- `plan/wait_correct/route-inventory/python-endpoints-inventory.csv`
- `plan/wait_correct/route-inventory/python-endpoints-summary.md`

## 2) 对比 Python 与 Rust 合同差异（默认 migrate 桶 + 只读方法）

```bash
python3 scripts/migration/api_contract_diff.py \
  --python-base http://127.0.0.1:8001 \
  --rust-base http://127.0.0.1:8000
```

输出：

- `plan/wait_correct/api-contract/api-contract-diff-<timestamp>.json`
- `plan/wait_correct/api-contract/api-contract-diff-<timestamp>.md`

可选参数：

- `--bucket migrate|retire|defer|proxy`
- `--include-unsafe-methods`（包含 POST/PUT/PATCH/DELETE）
- `--path-param key=value`（覆盖路径变量）
- `--query key=value`（附加查询参数）
