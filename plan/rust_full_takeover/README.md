# Rust Full Takeover

`plan/rust_full_takeover/` 是当前唯一 authoritative 入口，用来描述
Python -> Rust 全接管的现状、顺序和验证门。

## 文档定位

- 类型：Reference index
- 目标读者：继续执行迁移的开发者 / agent
- 目标：快速回答 3 个问题
  - 现在还剩哪些 Python 运行时责任
  - 下一步应该先接管哪一块
  - 走到什么程度才可以退休对应 Python 代码

## 当前范围

- runtime core：`backend_old/app` 中仍承担 live backend / scan / agent / llm / tool 责任的 Python
- retirement tail：`backend_old/alembic`、`backend_old/scripts`、`scripts/release-templates/runner_preflight.py`
- 不计入 runtime 主计数、但仍保留参考的内容：
  - `scripts/migration/*.py`
  - `plan/wait_correct/*`
  - vendored / cache / `.venv/**`

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`130`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

## 推荐阅读顺序

1. [01-overview-and-end-state.md](/home/xyf/audittool_personal/plan/rust_full_takeover/01-overview-and-end-state.md)
2. [02-roadmap-and-phases.md](/home/xyf/audittool_personal/plan/rust_full_takeover/02-roadmap-and-phases.md)
3. [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
4. [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
5. [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
6. [06-open-risks-and-bridges.md](/home/xyf/audittool_personal/plan/rust_full_takeover/06-open-risks-and-bridges.md)
7. [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
8. [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)

## 文档分工

- [01-overview-and-end-state.md](/home/xyf/audittool_personal/plan/rust_full_takeover/01-overview-and-end-state.md)
  解释为什么目标是 Rust 全接管，以及什么叫“完成”。
- [02-roadmap-and-phases.md](/home/xyf/audittool_personal/plan/rust_full_takeover/02-roadmap-and-phases.md)
  给出阶段划分、当前执行顺序和单个 slice 的标准动作。
- [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
  记录当前工作树事实、剩余功能组和活跃 blocker。
- [04-history-policy.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-history-policy.md)
  说明为什么 canonical 文档不再维护逐次进度日志，以及哪些原始材料仍保留。
- [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
  定义 Rust 接管每个 slice 时必须过的验证门。
- [06-open-risks-and-bridges.md](/home/xyf/audittool_personal/plan/rust_full_takeover/06-open-risks-and-bridges.md)
  记录仍在主链周围存活的 compat bridge 和误判风险。
- [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
  给后续开发者一个可直接执行的优先级列表。
- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
  按当前文件面列出所有仍待 Rust 接管的 Python 功能块。

## 使用原则

- canonical 文档只写当前状态、当前顺序和当前 blocker。
- 逐次操作流水账、过期计数变化、已完成但不再影响决策的历史，不再保留在本目录 canonical 文档中。
- 当文档和旧聊天摘要冲突时，以当前工作树和本目录 canonical 文档为准。

## Raw Reference

- [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
