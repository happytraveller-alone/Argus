# Rust Full Takeover

`plan/rust_full_takeover/` 是当前唯一的迁移主入口。

目标已经统一为：Rust 接管迁移范围内所有 Python 代码，而不是只接管 API 表面或部分 non-API 辅助模块。

## 阅读顺序

1. [01-overview-and-end-state.md](/home/xyf/audittool_personal/plan/rust_full_takeover/01-overview-and-end-state.md)
2. [02-roadmap-and-phases.md](/home/xyf/audittool_personal/plan/rust_full_takeover/02-roadmap-and-phases.md)
3. [03-current-state-and-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/03-current-state-and-ledger.md)
4. [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
5. [06-open-risks-and-bridges.md](/home/xyf/audittool_personal/plan/rust_full_takeover/06-open-risks-and-bridges.md)
6. [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
7. [04-slices-and-progress-log.md](/home/xyf/audittool_personal/plan/rust_full_takeover/04-slices-and-progress-log.md)

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

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app` 非 API Python：`172`

## 兼容说明

- `plan/wait_correct/` 暂时保留为 raw ledger / CSV / wave 记录路径。
- `plan/backend_old_python_migration/` 与 `plan/skill_manage/` 现在只保留跳转说明；原长账本已归档。

## 归档入口

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [archive/skill-runtime/unified-skill-runtime-plan.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/skill-runtime/unified-skill-runtime-plan.md)
- [archive/skill-runtime/unified-skill-runtime-execution.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/skill-runtime/unified-skill-runtime-execution.md)
- [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
