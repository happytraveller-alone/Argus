# Slices And Progress Log

## 最近完成的工作类型

### 文档树裁剪 / 历史遗留清理

- `wait_correct` 收缩为最小 raw reference 集：
  - `README.md`
  - `api-contract/README.md`
  - `route-inventory/*`
  - `waves/wave-a-log.md`
- 已删除只剩模板说明、没有实际沉淀内容的占位文档：
  - `behavior-diff/README.md`
  - `perf/README.md`
  - `stability/README.md`
  - `tooling/README.md`
  - `non-api-python/*`
  - `api-contract/contract-diff-template.md`
  - `route-inventory/route-inventory-template.csv`
  - `waves/wave-template.md`
- `rust_full_takeover/archive/skill-runtime/*` 这组专门 skill-runtime 长计划已删除，避免和 canonical 文档重复
- `reference/README.md`、`wait_correct/README.md`、`05-validation-and-gates.md` 已同步改成新入口和新回写规则

### Canonical 文档重构 / 剩余功能台账刷新

- `rust_full_takeover` 文档明确区分：
  - `backend_old/app` runtime core
  - `alembic / scripts / release preflight` retirement tail
- `08-remaining-python-function-inventory.md` 改成按功能分组的自洽清单：
  - runtime core `172`
  - alembic `21`
  - backend_old scripts `2`
  - release preflight `1`
- canonical 文档补进 frontend / API invariants、retired route consumer debt、operations / readiness gate
- raw ledger 增加“历史快照、非 authoritative”提示，避免旧计数和旧入口误导后续开发者

### Rust Contract 收口

- `skills` 默认 contract 切到 prompt-effective unified surface
- external-tools compat 面保留
- prompt skill persistence boundary 切到 Rust-native store

### Dead Shell / Convenience Package 清理

已退休：

- `agent/__init__.py`
- `agent/skills/__init__.py`
- `agent/workflow/__init__.py`
- `agent/bootstrap/__init__.py`
- `agent/tools/runtime/__init__.py`
- `agent/tools/__init__.py`
- `agent/telemetry/*`
- 多个 zero-caller subpackage shell

### Test-Only / Orphan Cluster 清理

已退休：

- workflow retained test-only cluster
- business-logic-scan retained pair
- `knowledge/tools.py`
- `tool_runtime` orphan edge cluster

## 详细历史

完整逐条 slice 历史保留在：

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
