# Validation And Gates

## Slice 规则

1. 先做 caller 盘点，再删文件。
2. 先写或更新 guard，再删除目标。
3. 每次 slice 结束后必须补 ledger。
4. 未验证，不得宣称完成。

## Rust Backend Gate

如果改动触及 `backend/`：

```bash
cd /home/xyf/audittool_personal/backend
cargo test
cargo build --bin backend-rust
```

## Python Retained Gate

如果改动触及 `backend_old/`：

```bash
cd /home/xyf/audittool_personal/backend_old
uv run --project . pytest -s ...
```

优先跑最小 guard：

- `test_api_router_rust_owned_routes_removed.py`
- `test_config_internal_callers_use_service_layer.py`

## 文档回写门

每次 slice 后，至少同步：

- [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
- [04-slices-and-progress-log.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-slices-and-progress-log.md)
- raw ledger：
  - [wait_correct/non-api-python/non-api-python-summary.md](/home/xyf/audittool_personal/plan/wait_correct/non-api-python/non-api-python-summary.md)
  - [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
