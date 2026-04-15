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

## Frontend / API Stability Gate

如果改动触及 Rust-owned route、contract、payload 或 Python route retire 判断，至少确认下面几点：

1. `/api/v1` base path 不变。
2. 受影响接口的方法、路径、query 参数名、下载行为、header 与字段命名保持兼容。
3. SSE 接口继续保持 `text/event-stream` 与 `data: <json>\n\n` framing。
4. 把某条 route 标成 `retire` 之前，必须证明没有剩余 frontend / TS caller，或者已明确提供 compat stub。
5. 若 Rust 侧故意做 contract narrowing，必须同步把 frontend 变更写进计划和验证记录。

## Operations / Readiness Gate

进入“Rust 已可接管 / Python 可退休”判断前，不能只看容器是否 `healthy`。

至少需要确认：

1. release / compose 启动后，`GET /health` 的 JSON `status` 为 `ok`，而不只是 HTTP `200`。
2. `bootstrap.database`、`bootstrap.legacy_schema`、`bootstrap.preflight` 没有 `degraded` / `failed`。
3. runner preflight 真正能拉起镜像和执行命令，而不是只有构建通过。
4. 部署环境具备 Docker socket、runner image pull / run 能力，以及必要的 registry 网络连通性。

## Final Cutover Gate

在宣称“Python 已接近全退役”前，还必须过下面的最终门：

1. 至少一条 `agent-tasks` 真路径 smoke 通过。
2. 至少一条 `static-tasks` 真路径 smoke 通过，并覆盖当前 runner family。
3. `PYTHON_ALEMBIC_ENABLED`、legacy mirror/backfill、startup compat bridge 的退出条件被明确验证。
4. `backend_old/alembic`、`backend_old/scripts`、release preflight 这类 ops tail 有明确 owner 和删除/保留判定。

## 文档回写门

每次 slice 后，至少同步：

- [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
- [04-slices-and-progress-log.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-slices-and-progress-log.md)
- 如涉及 route ownership / contract：
  - [wait_correct/route-inventory/python-endpoints-summary.md](/home/xyf/audittool_personal/plan/wait_correct/route-inventory/python-endpoints-summary.md)
- 如涉及逐波次 raw 记录：
  - [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
