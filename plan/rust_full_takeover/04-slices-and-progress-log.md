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
  - runtime core `167`
  - alembic `21`
  - backend_old scripts `2`
  - release preflight `1`
- canonical 文档补进 frontend / API invariants、retired route consumer debt、operations / readiness gate
- raw ledger 增加“历史快照、非 authoritative”提示，避免旧计数和旧入口误导后续开发者

### Rust Contract 收口

- `skills` 默认 contract 切到 prompt-effective unified surface
- external-tools compat 面保留
- prompt skill persistence boundary 切到 Rust-native store
- agent-task creation 开始写入 Rust-owned `prompt_skill_runtime` snapshot
- prompt_skill_runtime compat projection 对称退役（2026-04-18）：
  - Rust WIP 里未落地的 `legacy_python_config` 字段 / `LegacyPythonPromptSkillConfig` struct / `legacy_python_prompt_skill_config()` 投影 helper，以及 `task_routes_api.rs` 里 3 处相关测试断言统一撤销，代码回到 commit `0b2379cc` 状态。
  - Python 5 个 live agent（recon / analysis / verification / business_logic_recon / business_logic_analysis）删除 `use_prompt_skills` + `prompt_skills` 注入块及其在 initial_message 里的拼接段。
  - `backend_old/tests/agent/test_prompt_skills_injection.py` 整体删除。
  - 驱动：Rust bootstrap 只 `exec_backend_server()` 启动 Rust 二进制，Python `OrchestratorAgent` 只被测试引用，投影两端都无 live consumer。Rust mirror（`upsert_legacy_prompt_skill` / `compat_backfill_from_legacy_if_empty`）保留，服务于 alembic legacy 表。

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

### Tool Runtime Retained Core Retirement (2026-04-18)

- `tool_runtime/runtime.py`、`router.py`、`health_probe.py`、`write_scope.py`、`catalog.py` 整组退役，`backend_old/app` runtime core 计数 `172 -> 167`，`tools / tool_runtime` 分组计数 `32 -> 27`。
- `backend_old/app/services/agent/agents/base.py` 删除仅剩 dead reference 的 `TYPE_CHECKING` import，避免已退役模块通过类型引用回流。
- 新增 `backend_old/tests/test_tool_runtime_cluster_retired.py` guard，复用既有 AST import offender helper，要求 5 个文件物理不存在，且 `app/`、`scripts/`、`tests/`、`alembic/` 无 live Python importer。
- 验证结果：`backend_old` 下目标 pytest guard 通过，`backend` 下 `cargo test` 与 `cargo build --bin backend-rust` 通过，repo grep 只剩新 guard 中的断言/模块字符串。

## 详细历史

完整逐条 slice 历史保留在：

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
