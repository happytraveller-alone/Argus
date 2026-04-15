# Overview And End State

## 文档定位

- 类型：Explanation
- 目标读者：后续实现 Rust 全接管的开发者、主 agent、subagent

## 目标

当前迁移目标已经统一为：Rust 接管迁移范围内所有 Python 代码。

这里默认指的是：仓库中所有仍承担 live backend / scan / deploy 责任的 Python 代码。

这里的“接管”包含 4 层含义：

1. Rust 成为对应能力的唯一 source of truth。
2. 运行主链路不再调用对应 Python 文件。
3. Python bridge、mirror、compat adapter 不再承担主读写职责。
4. 旧 Python 文件、死测试、package shell、retained helper 都被删除或显式归档。

## 范围

本路线图覆盖：

- `backend_old/app` 下仍承担 live 责任的 Python 后端代码
- `backend_old/alembic`、`backend_old/scripts`、release preflight 这类仍影响运行/部署的 Python 尾巴
- 与 Python 后端迁移直接相关的 `plan/` 文档
- Rust 为兼容迁移而保留的 mirror / bridge / raw ledger

默认不把下面这些文件算入“runtime 主计数”，但它们仍需要在计划里保持可解释：

- `scripts/migration/*.py` 这类 inventory / diff tooling
- `plan/wait_correct/*` 这类历史账本
- `.venv/**` 或其它 vendored Python 依赖

## 完成定义

只有同时满足下面条件，才算“Rust 全接管完成”：

1. `backend_old/` 不再包含 live Python runtime、service、model、workflow、tool runtime、knowledge、launcher、scanner orchestration。
2. Rust 路由不再依赖 Python legacy 表、legacy JSON 字段或旧 helper 作为主存储。
3. `backend-py`、Python upstream bridge、Python startup wrapper、Python runtime launcher 均已退出主链路。
4. `plan/` 下 canonical 文档只保留 Rust 全接管视角。
5. 前端可见 contract 仍稳定，或已由显式的前端迁移条目同步改写：
   `/api/v1` base path、方法/路径、query 参数、SSE framing、下载行为、字段命名都不能被隐式改坏。
6. `backend_old/alembic`、`backend_old/scripts` 和 release preflight 这类运行/部署 Python 尾巴不再承担 live 责任。

## External API Invariants

Rust 接管是内部 ownership 迁移，不自动授权改变前端可见 contract。

在没有单独 frontend migration 条目之前，下面这些约束默认必须保持：

- 路径前缀仍为 `/api/v1`
- 路由形状、query 参数名、下载 URL 与 header 语义保持兼容
- SSE 端点继续输出 `text/event-stream`，并维持 `data: <json>\n\n` framing
- 各路由组现有字段命名风格保持不变，不把 camelCase / snake_case 混成一刀切
- 某条 Python route 被标记为 `retire` 之前，必须先证明 frontend / consumer 已清零或已有 compat stub

## 当前判断

当前还远未完成。

Rust 已拿到部分控制面和若干主存储边界，但 retained Python runtime 仍然存在于：

- agent core
- scanner / queue / workspace / tracking
- tool runtime core
- knowledge / llm / llm_rule
- db / alembic 兼容 gate
- runtime-adjacent scripts / deploy preflight
