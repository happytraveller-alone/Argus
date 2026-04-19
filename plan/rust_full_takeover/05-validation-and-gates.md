# Validation And Gates

## 文档定位

- 类型：How-to
- 目标读者：执行单个 takeover slice 的开发者

## Slice 规则

1. 先盘点 caller，再删文件。
2. 先让 Rust 拿到 source of truth，再删 Python bridge。
3. 先写或更新 guard，再删除目标。
4. 每个 slice 结束后都要回写 canonical 文档。
5. 未验证，不得宣称完成。

## Rust Backend Gate

如果改动触及 `backend/`：

```bash
cd /home/xyf/audittool_personal
cargo test --manifest-path backend/Cargo.toml
cargo build --manifest-path backend/Cargo.toml
```

## Python Retained Gate

如果改动触及 `backend_old/`：

```bash
cd /home/xyf/audittool_personal
uv run --project . pytest -s backend_old/tests/...
```

优先跑最小 guard：

- `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
- `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- 当前 slice 对应的 retirement guard / contract test

## Frontend / API Stability Gate

如果改动触及 Rust-owned route、contract、payload 或 Python route retire 判断，
至少确认下面几点：

1. `/api/v1` base path 不变。
2. 受影响接口的方法、路径、query 参数名、下载行为、header 与字段命名保持兼容。
3. SSE 接口继续保持 `text/event-stream` 与 `data: <json>\n\n` framing。
4. 把某条 route 标成 `retire` 之前，必须证明没有剩余 frontend / TS caller，或者已明确提供 compat stub。
5. 若 Rust 侧故意做 contract narrowing，必须同步把前端变更和验证结论写进计划。

## Operations / Readiness Gate

进入“Rust 已可接管 / Python 可退休”判断前，不能只看容器是否 `healthy`。

至少需要确认：

1. release / compose 启动后，`GET /health` 的 JSON `status` 为 `ok`，而不只是 HTTP `200`。
2. `bootstrap.database` 与 `bootstrap.preflight` 没有 `degraded` / `failed`。
3. runner preflight 真正能拉起镜像和执行命令，而不是只有构建通过。
4. 部署环境具备 Docker socket、runner image pull / run 能力，以及必要的 registry 网络连通性。

## Final Cutover Gate

在宣称“Python 已接近全退役”前，还必须过下面的最终门：

1. 至少一条 `agent-tasks` 真路径 smoke 通过。
2. 至少一条 `static-tasks` 真路径 smoke 通过，并覆盖当前 runner family。
3. legacy mirror / backfill / startup compat bridge 的退出条件被明确验证。
4. `backend_old/scripts`、release preflight 这类 ops tail 有明确 owner 和删除 / 保留判定。

## 文档回写门

每个 slice 结束后，至少同步：

- [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
- [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)

如涉及 route ownership / contract：

- [wait_correct/route-inventory/python-endpoints-summary.md](/home/xyf/audittool_personal/plan/wait_correct/route-inventory/python-endpoints-summary.md)

如涉及逐波次 raw 记录：

- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
