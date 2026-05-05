# Spec: Opengrep Sandbox Auto-Destroy（彻底冷启动改造）

> 由 deep-dive 流水线生成（trace + interview）。本 spec 是后续 ralplan/autopilot 的输入。

## Goal

把 opengrep 的 OCI cubesandbox 模式从"warm pool 复用"**彻底改造为冷启动 + per-task 销毁**，与 codeql 保持一致：每个 opengrep 扫描任务现场创建独立沙箱实例、跑完即销毁。任何任务出口（成功 / 失败 / 取消 / 进程退出）都必须触发销毁；底层销毁失败不再被静默吞掉，而是结构化日志可观测，并由 reconcile 兜底回收。

## Constraints

1. **彻底删除 pool**：删除 `backend/src/runtime/cubesandbox/opengrep_pool.rs` 整个文件；删除 `bootstrap::warm_opengrep_pool` 与其所有调用点；删除 `AppState::opengrep_pool / set_opengrep_pool / get_opengrep_pool` 字段与方法；删除 `CUBESANDBOX_OPENGREP_POOL_SIZE` 环境变量分支与文档；删除 manifest 持久化路径相关代码与文件读写。
2. **统一冷启动入口**：`run_opengrep_scan` 内只保留 cold path（即调用 `prepare_client → create_sandbox → connect_sandbox → run_command → delete_sandbox`），逻辑结构与 `codeql_cubesandbox.rs` 对齐。
3. **销毁路径必须覆盖所有任务出口**：通过引入 `OpengrepSandboxSession` 的 `Drop` 替代品（async 兜底 cleanup helper），保证：
   - 成功路径：scan 完成后显式 `delete_sandbox`。
   - 错误路径：`run_scan?` 早返时仍能触发销毁（重构 `run_opengrep_scan` 为 `run + always-cleanup` 模式，使用 `let result = ...; cleanup(); result?` 或 `tokio::spawn` 兜底；不依赖 sync `Drop`）。
   - 取消路径：与现有 cancellation token 集成，cancel 触发后立即销毁实例。
   - 进程退出路径：见约束 4。
4. **Graceful shutdown**：在 `main.rs` 加入 SIGTERM / SIGINT / Ctrl+C 信号处理：收到信号后**拒绝新任务**（HTTP 层返回 503 或类似，对静态审计入口标记 shutting-down）+ **等待 in-flight 扫描完成**（含其各自的 `delete_sandbox`）→ 退出。无 pool 需要 drain。
5. **销毁失败 = 最大努力**：替换全部 3 处 `let _ = ...delete_sandbox(..).await`（分别在 `opengrep_pool.rs:299`（删除时随 pool 一起删）、`opengrep_cubesandbox.rs:161`、`codeql_cubesandbox.rs:148`）为带 `tracing::error!` 的结构化错误日志（字段：`sandbox_id`、`task_id`、`stage`、`error`），不重试，不上抛失败业务任务。codeql 的同等修复一并纳入本次工作（同一行为契约）。
6. **Reconcile 对 opengrep 可见**：在 `opengrep_cubesandbox.rs` 新增 `pub fn snapshot_active_sandbox_ids` 导出；在 `reconcile.rs` 新增 `read_active_opengrep_sandboxes` 并在所有现有调 `read_active_codeql_sandboxes` 的位置同时取并集（line ~601、~752）。`list_sandboxes` stub 是否启用不在本次范围内（保持现状），但 active-set 必须正确导出，为未来 stub 取消铺路。
7. **删除路径可逆性**：本次为破坏性改造（无回退分支），git 提交需要清晰 commit messages。manifest 文件残留 `/var/lib/argus/opengrep-pool-manifest.json`：启动时若存在直接删除（不解析、不报错），属一次性迁移。
8. **不引入 metrics**：本次仅靠结构化日志可观测，不加 Prometheus counter/gauge/histogram。

## Non-Goals

- **不**做模板（cubemaster template）/ containerd snapshot 层的 per-task 清理。模板层缺口（trace 已识别 + 项目记忆 obs 180/181/182）作为**独立后续任务**处理，与 codeql 模板层缺口同源。
- **不**给 opengrep 引入新的 metrics 导出器。
- **不**修改 codeql 的池化策略（codeql 当前已是冷启动模式，不需要改），仅顺手统一两处 `let _ =` 错误吞掉。
- **不**改动 reconcile 的 stub 启用状态（`orphan_sandbox_check_skipped = true` 维持现状）。
- **不**引入新的环境变量或配置项。`CUBESANDBOX_OPENGREP_POOL_SIZE` 直接移除。
- **不**承诺冷启动后的扫描延迟上限（已确认无硬性预算）。

## Acceptance Criteria

**AC1（核心销毁，集成测试）**：在 `backend/tests/` 下增加集成测试，对 opengrep 任务跑三条路径（happy / scan 失败 / cancel），每条路径任务终结后断言：
- `cubemastercli cubebox list`（或等价的 cubemaster client API mock）中**不含**该任务对应的 sandbox_id；
- `pool-manifest.json` 文件不再被读写（在彻底删除后该文件不应被 backend 创建或访问）；
- 任务结束后服务可立即接受下一个 opengrep 任务，新任务创建出**新的** sandbox_id（验证非池化语义）。

**AC2（错误吞掉转日志）**：注入一次模拟 `delete_sandbox` 失败（mock 返回 Err），断言日志中出现一条 `tracing::error!` 包含 `sandbox_id`、`task_id`、`error` 三个字段；任务返回原本的业务结果（不被销毁失败污染）。覆盖 opengrep happy-path 和 codeql happy-path 两个调用点。

**AC3（graceful shutdown）**：集成测试或专项测试：启动 backend，提交一个 opengrep 任务（足够慢的输入或 mock 长扫描），向进程发送 SIGTERM。断言：
- 信号到达后新提交的任务被拒（HTTP 5xx 或显式拒绝信号）；
- in-flight 任务被等待至完成；
- in-flight 任务的 sandbox 被销毁（cubebox list 不含其 sandbox_id）；
- 进程 0 退出码退出。

**AC4（reconcile 可见性）**：在 `reconcile.rs` 中调 `read_active_opengrep_sandboxes` 的位置加单元测试，断言：当 `snapshot_active_sandbox_ids` 返回 `{"opengrep-X"}` 时，reconcile 的 active-set 并集包含 `opengrep-X`；orphan 决策不会把这个 ID 当孤儿删除。

**AC5（pool 代码完全删除）**：
- `find backend/src -name 'opengrep_pool*'` 返回空；
- `rg 'OpengrepSandboxPool|opengrep_pool|warm_opengrep_pool|CUBESANDBOX_OPENGREP_POOL_SIZE|opengrep-pool-manifest' backend/`（除 tests/ 中可能的回归测试）返回空；
- `cargo build` 通过；`cargo test` 通过；
- `env.example` / `.env` / 文档中相关条目清理。

**AC6（manifest 一次性迁移）**：backend 启动时若 `/var/lib/argus/opengrep-pool-manifest.json` 存在则删除（最多打一条 info 日志），不解析；后续不再写入。

**AC7（API 兼容）**：static_tasks.rs 与 backend 对外 HTTP API 保持二进制兼容——任务请求/响应字段、状态枚举、错误码不因本次改造发生变化。

## Assumptions Exposed

1. **冷启动延迟可接受**：用户明确"几秒钟可接受"，不设硬上限，不加性能 AC。日后若延迟成为问题，可在不破坏 API 的前提下重新引入池化（按需求决策）。

   Observed cubemaster `create_sandbox` p50≈N/A; deferred to first CI run with live cubemaster (Q5 filed 2026-05-05).
   No SLO; recorded for regression detection only.
2. **codeql 的 `let _ = delete_sandbox` 等价处理可一并修**：trace 发现 codeql 也有同一缺陷，假设该顺手补丁不超出当前 scope。如果用户希望 codeql 单独走 PR，需要二次确认（但已默认纳入）。
3. **`cubemaster.delete_sandbox` 是同步删除底层资源**：假设其返回 Ok 即代表 cubebox 实例确实终止；containerd snapshot 是否同步删除是 cubemaster 内部约定。如果返回 Ok 而 snapshot 残留，那是 cubemaster 侧的 bug，不在本次范围。
4. **`run_opengrep_scan` 改写后仍是 `async fn`，可用 `try`/`finally` 等价模式**：通过提取 `cleanup_on_any_exit` 闭包或显式 match `Ok/Err` 后调 cleanup 实现"无论成功失败都销毁"，不依赖 sync `Drop` impl。
5. **graceful shutdown 信号处理在 main.rs 而非框架内**：`main.rs` 已是 backend 启动入口，使用 tokio `signal::ctrl_c()` + 自定义 broadcast channel 通知 router 拒新 + Drop AppState。
6. **现有 cold-path（`opengrep_cubesandbox.rs:131-260` 区间的 Direct 分支）功能正确**：trace 分析显示 cold path 在 happy 与显式 error 两条线上都已正确调 `delete_sandbox`，本次重构只需在错误传播路径上补"早返也清理"。
7. **manifest 文件路径默认是 `/var/lib/argus/opengrep-pool-manifest.json`**：以代码中 `OpengrepSandboxPool::manifest_path_from_env()` 的默认值为准，不读环境变量定制。

## Technical Context

### 关键文件与行号
- `backend/src/runtime/cubesandbox/opengrep_pool.rs` — **整体删除**
- `backend/src/scan/opengrep_cubesandbox.rs:131-260` — Pool 与 Direct 双分支，重构为只有 Direct
- `backend/src/scan/opengrep_cubesandbox.rs:161` — `let _ = delete_sandbox` 转结构化日志
- `backend/src/scan/opengrep_cubesandbox.rs:271-309` — `OpengrepSandboxSession::run_scan/cleanup` 重写为"早返也清理"
- `backend/src/scan/codeql_cubesandbox.rs:148` — `let _ = delete_sandbox` 转结构化日志
- `backend/src/runtime/cubesandbox/reconcile.rs:201-202, 601, 752` — 加 `read_active_opengrep_sandboxes`
- `backend/src/state.rs:254, 278, 302-308` — 删除 `opengrep_pool` 字段与 setter/getter
- `backend/src/bootstrap/mod.rs:152, 533-636` — 删除 `warm_opengrep_pool` 与所有调用
- `backend/src/main.rs` — 加 graceful shutdown signal handler
- `env.example` / `.env` — 移除 `CUBESANDBOX_OPENGREP_POOL_SIZE`
- `argus-shutdown.sh` — 不变（仍作终极兜底，但不再是常规清理路径）

### 依赖与并发模型
- 现有 cubemaster client（`CubemasterClient`）已是 async；销毁是 RPC 调用。
- 任务执行模型：每个 HTTP 任务请求在 tokio task 中执行 `run_opengrep_scan`，无共享可变状态（除 cubemaster client）。
- Graceful shutdown 推荐用 `tokio::sync::Notify` 或 `broadcast::channel` 广播 shutting-down 信号给 HTTP layer + 现有任务管理器。

### 项目记忆相关性
- 与 `argus-cubesandbox-state-layer-authority` 项目 skill 一致：本 spec 修的是 **Postgres + cubemaster 实例层**的清理对齐，**不动**模板层（独立任务）。
- 与 obs 180/181/182 一致：模板层 cleanup 缺口跨 codeql/opengrep 共享，但与本 spec 正交。

## Ontology

| 实体 | 含义（修订后） |
|------|----------------|
| **opengrep sandbox 实例** | 一个由 cubemaster 创建的 cubebox，绑定一个 opengrep 扫描任务的整个生命周期；任务结束即销毁 |
| **OpengrepSandboxSession** | Rust 内的 session 封装；新版只持有 client + sandbox_id + 若干元数据，没有 PoolGuard |
| **冷启动 (cold start)** | 任务到达 → cubemaster.create_sandbox → connect → run → delete 的完整路径；无预热 |
| **任务出口** | 任务终结的所有可能路径：成功完成 / scan 错误 / cancel / 进程优雅退出 / 进程异常崩溃（最后一种依赖 reconcile 兜底） |
| **graceful shutdown** | 进程收到 SIGTERM/SIGINT 后：拒新任务 + 等 in-flight + 各自销毁实例 + 进程退出 |
| **reconcile orphan check** | 后台周期任务，当前 stub（永跳过）；本次只补"opengrep active-set 可见"，不启用 stub |

## Ontology Convergence

`pool` / `warm pool` / `release` / `recycle` / `acquire` / `PoolGuard` / `manifest` 这些概念在新本体中**全部消失**。它们的旧含义不再有效，相关代码与文档应一并清除以避免读者困惑。

## Trace Findings

合成自三条并行 trace lane（详见 `.omc/specs/deep-dive-trace-opengrep-sandbox-auto-destroy.md`）。摘录与 spec 决策的对应关系：

- **H1（warm-pool 设计 + pool.shutdown 无调用方）→** 通过约束 1（删除 pool）彻底解决；无需 `pool.shutdown()` 接线，因为没有池。
- **H2（错误路径 session-drop 不清理）→** 通过约束 3（重写 `run_opengrep_scan` 为"无论成功失败都销毁"模式）解决；不依赖 sync `Drop`。
- **H3（模板层结构性缺口 + `let _ =` swallow）**：
  - swallow 部分 → 约束 5 解决（3 处全转结构化日志，含 codeql 的同源缺陷）；
  - 模板层 → 显式列入 Non-Goal，独立任务跟进。
- **H4（reconcile orphan 对 opengrep 不可见）→** 通过约束 6 解决（加 `read_active_opengrep_sandboxes` + `snapshot_active_sandbox_ids` 导出），但 stub 启用不在本次范围。
- **静态探针确认**：`pool.shutdown()` 在 main path 零调用方；main.rs 无 graceful hook；3 处 swallow（trace lane 3 漏算 1 处，已补正到 spec）。

## Interview Transcript

| Round | 维度焦点 | 问题摘要 | 用户决定 |
|-------|----------|----------|----------|
| 1 | Goal — destroy 语义 | 任务结束后销毁的具体语义是什么？ | （初选）保留池 + 任务后丢弃 + 后台补池 |
| 2 | Goal — 工作范围 | trace 找到 3 个独立缺陷，本次工作范围？ | 中等范围 + 补 reconcile orphan 对 opengrep 可见 |
| 3 | Constraints — 池溢出 + refill | 池=2 时第 3 个并发任务怎么处理？refill 何时启动？ | 冷路径兜底；refill 跟随策略自动选 |
| 4 | Constraints — 失败/优雅退出 | destroy 失败策略？SIGTERM 时语义？ | best-effort + 日志；拒新 + 等 in-flight + drain pool |
| 5 | Criteria — 验收形态 + metrics | 用什么证据验收？加几个 metric？ | 集成测试断言 sandbox_id 消失；**改主意：彻底冷启动，不要 warm pool** |
| 6 | Goal scope — 池代码处置 + 延迟预算 | pool 代码删除还是 disable？冷启动延迟有没有预算？ | 直接删除全部 pool 代码；无硬延迟预算 |

**Round 5 中段用户重定向**是关键转折：从"混合模式"切换到"彻底冷启动 + 与 codeql 对齐"。本 spec 的 Goal/约束 1/Non-Goals/AC 全部反映这次重定向后的最终决定。
