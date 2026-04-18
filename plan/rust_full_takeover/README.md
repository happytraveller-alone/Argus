# Rust Full Takeover

`plan/rust_full_takeover/` 是当前唯一的迁移主入口。

目标已经统一为：Rust 接管迁移范围内所有仍承担 live backend / scan / deploy 责任的 Python 代码，而不是只接管 API 表面或部分 non-API 辅助模块。

## 阅读顺序

1. [01-overview-and-end-state.md](/home/xyf/audittool_personal/plan/rust_full_takeover/01-overview-and-end-state.md)
2. [02-roadmap-and-phases.md](/home/xyf/audittool_personal/plan/rust_full_takeover/02-roadmap-and-phases.md)
3. [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
4. [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
5. [06-open-risks-and-bridges.md](/home/xyf/audittool_personal/plan/rust_full_takeover/06-open-risks-and-bridges.md)
6. [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
7. [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
8. [04-slices-and-progress-log.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-slices-and-progress-log.md)

## 文档分工

- [01-overview-and-end-state.md](/home/xyf/audittool_personal/plan/rust_full_takeover/01-overview-and-end-state.md)
  解释为什么目标是 Rust 全接管，以及什么叫“完成”。
- [02-roadmap-and-phases.md](/home/xyf/audittool_personal/plan/rust_full_takeover/02-roadmap-and-phases.md)
  描述阶段划分、阶段目标、当前所处阶段。
- [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
  给出当前工作树事实、Rust 已接管面、仍保留的 Python cluster。
- [04-slices-and-progress-log.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-slices-and-progress-log.md)
  汇总最近完成的 slice，并指向原始详细 ledger。
- [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
  统一迁移门禁、验证命令和通过标准。
- [06-open-risks-and-bridges.md](/home/xyf/audittool_personal/plan/rust_full_takeover/06-open-risks-and-bridges.md)
  列出尚存的 compat bridge、风险和删除前置条件。
- [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
  给后续开发者一个可直接接手的短目标列表。
- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
  统一列出当前仍待 Rust 接管的 Python 功能块、文件和推荐 Rust 落点。

## 统计口径

当前 canonical 文档默认区分两层范围：

- runtime core：`backend_old/app` 下仍承担 live 责任的 Python 代码
- retirement tail：`backend_old/alembic`、`backend_old/scripts`、release preflight 等不在 `app` 内、但仍阻止“Python 全退役”的运行/运维 Python 面

不计入 runtime 退役主计数、但仍需保持同步的内容：

- `scripts/migration/*.py` 这类 inventory / diff tooling
- `plan/wait_correct/*` raw ledger
- `.venv/**` 或其它 vendored Python 文件

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`164`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`1`
- `scripts/release-templates` 运行相关 Python：`1`

## 兼容说明

- `plan/wait_correct/` 仅保留最小 raw reference：route inventory、contract diff 输出目录、wave log。
- 旧的 `backend_old_python_migration` / `skill_manage` 长账本已并入 `plan/rust_full_takeover/`，不再作为独立 canonical 入口。
- `wait_correct/*` 中的个别数字、路径和镜像入口说明可能是历史快照；当前真相以本目录下 canonical 文档为准。

## 保留参考

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)

专门的 `skill-runtime` 长计划已视为历史重复文档，不再单独保留；相关结论已经收敛进当前 canonical 文档。
