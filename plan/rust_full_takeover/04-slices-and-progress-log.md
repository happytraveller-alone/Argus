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
  - runtime core `157`
  - alembic `21`
  - backend_old scripts `1`
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

### Package Source Selector Retirement (2026-04-18)

- `backend_old/scripts/package_source_selector.py` 已退役，`backend_old/scripts` Python 计数 `2 -> 1`。
- Rust `backend/src/runtime/bootstrap.rs` 原生接管 PyPI candidate probe / 排序，去掉了对 `/usr/local/bin/package_source_selector.py` 的 Python subprocess 依赖。
- `backend_old/scripts/dev-entrypoint.sh`、`docker/backend_old.Dockerfile` 与 `docker/flow-parser-runner.Dockerfile` 改为 shell 内按配置顺序去重选择镜像源，不再引用 Python selector。
- 新增 `backend_old/tests/test_package_source_selector_retired.py` guard，要求脚本物理不存在，且 dev entrypoint / Dockerfile 不再保留任何 `package_source_selector.py` 文本引用。

### DB Package Shell Retirement (2026-04-18)

- `backend_old/app/db/__init__.py` 已退役，`backend_old/app` runtime core 计数 `167 -> 166`，`db / schema snapshot gate` 分组计数 `3 -> 2`。
- `backend_old/app/services/bandit_rules_snapshot.py` 与 `backend_old/app/services/pmd_rulesets.py` 直接读取 Rust-owned `backend/assets/scan_rule_assets/*`，不再经过 `app.db` package shell bridge。
- 新增 `backend_old/tests/test_db_package_shell_retired.py` guard，要求 `app/db/__init__.py` 物理不存在，且 live Python 路径不再保留 `from app.db import ...` importer。
- 验证结果：`test_db_package_shell_retired.py`、`test_bandit_rules_snapshot.py`、`test_pmd_rules_service.py` 通过；`test_alembic_project.py` 中与本切片直接相关的 squashed-baseline/snapshot 用例通过，另有 revision-head 旧断言失败，属于现存 alembic baseline debt。

### Flow Caller Cutover + Service Package Shell Retirement (2026-04-18)

- live caller 已从旧 `app.services.agent.flow` 路径切到 `app.services.agent.core.flow`；相关 agent/tool/test import 与 monkeypatch target 已全部同步。
- `backend_old/app/services/llm/__init__.py` 与 `backend_old/app/services/agent/agents/__init__.py` 已退役，`backend_old/app` runtime core 计数 `166 -> 164`，`agent orchestration / state / payload` 计数 `25 -> 24`，`llm` 计数 `15 -> 14`。
- 新增 `backend_old/tests/test_service_package_shells_retired.py` guard，要求 `app.services.llm` 与 `app.services.agent.agents` package shell 物理不存在，且 live importer 改为 direct-module 路径。
- 验证结果：
  - `tests/test_service_package_shells_retired.py`
  - `tests/test_llm_tokenizer_runtime.py`
  - `tests/agent/test_agents.py`
  - `tests/test_agent_prompt_contracts.py`
  - `tests/test_code2flow_runtime.py -k 'not unavailable'`
  - `tests/test_function_locator_tree_sitter.py -k tries_runner_before_local_tree_sitter`
  - `tests/test_ast_index_definition_provider.py`
  - `tests/test_flow_parser_runner_client.py`
  - `tests/test_function_locator_cli.py`
  - `tests/test_config_internal_callers_use_service_layer.py -k 'retired_agent_subpackage_shell and flow'`

### Top-Level Package Shell Retirement (2026-04-18)

- `backend_old/app/core/__init__.py` 与 `backend_old/app/models/__init__.py` 已退役，`backend_old/app` runtime core 计数 `164 -> 162`，`app root / core / config / security` 计数 `5 -> 4`，`models / persistence mirror` 计数 `18 -> 17`。
- `backend_old/alembic/env.py` 改为显式导入各 model module，metadata 注册不再依赖 `app.models` package shell。
- 新增 `backend_old/tests/test_top_level_package_shells_retired.py` guard，要求 `app.core` 与 `app.models` package shell 物理不存在，且 live importer 不再通过它们取模块。
- 验证结果：`tests/test_top_level_package_shells_retired.py` 通过；`tests/test_alembic_project.py` 中与本切片直接相关的 squashed-baseline/snapshot 用例继续通过，另有 revision-head 旧断言失败，属于现存 alembic baseline debt。

### Residual Namespace Shell Retirement (2026-04-18)

- `backend_old/app/__init__.py`、`backend_old/app/db/schema_snapshots/__init__.py`、`backend_old/app/services/agent/core/flow/lightweight/__init__.py`、`backend_old/app/services/llm/adapters/__init__.py` 已退役，`backend_old/app` runtime core 计数 `162 -> 158`。
- `backend_old/app/services/llm/factory.py` 与 `tests/test_llm_stream_empty_handling.py` 改为 direct-module imports，不再通过 `app.services.llm.adapters` package shell 取 adapter 模块。
- 新增 `backend_old/tests/test_namespace_package_shells_retired.py` guard，要求 residual namespace/package shell 物理不存在，且 live importer 不再经过它们。
- 验证结果：
  - `tests/test_namespace_package_shells_retired.py`
  - `tests/test_llm_stream_empty_handling.py`
  - `uv run --project . python` import smoke:
    `app.services.llm.factory`
    `app.services.llm.adapters.litellm_adapter`
    `app.services.agent.core.flow.lightweight.function_locator`
    `app.db.schema_snapshots.baseline_5b0f3c9a6d7e`

### Rule Contracts Retirement (2026-04-18)

- `backend_old/app/services/rule_contracts.py` 已退役，`backend_old/app` runtime core 计数 `158 -> 157`，`shared helpers` 计数 `7 -> 6`。
- `OpengrepRuleCreateRequest` 已直接内联到 `backend_old/app/services/rule.py`，live caller 不再跨文件依赖 contract shim。
- 新增 `backend_old/tests/test_rule_contracts_retired.py` guard，要求 `rule_contracts.py` 物理不存在，且 live importer 不再指向旧模块。
- 验证结果：
  - `tests/test_rule_contracts_retired.py`
  - `tests/test_generic_rule_yaml_validation.py`

## 详细历史

完整逐条 slice 历史保留在：

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
