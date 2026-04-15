# Overview And End State

## 文档定位

- 类型：Explanation
- 目标读者：后续实现 Rust 全接管的开发者、主 agent、subagent

## 目标

当前迁移目标已经统一为：Rust 接管迁移范围内所有 Python 代码。

这里的“接管”包含 4 层含义：

1. Rust 成为对应能力的唯一 source of truth。
2. 运行主链路不再调用对应 Python 文件。
3. Python bridge、mirror、compat adapter 不再承担主读写职责。
4. 旧 Python 文件、死测试、package shell、retained helper 都被删除或显式归档。

## 范围

本路线图覆盖：

- `backend_old/` 下的 Python 后端代码
- 与 Python 后端迁移直接相关的 `plan/` 文档
- Rust 为兼容迁移而保留的 mirror / bridge / raw ledger

## 完成定义

只有同时满足下面条件，才算“Rust 全接管完成”：

1. `backend_old/` 不再包含 live Python runtime、service、model、workflow、tool runtime、knowledge、launcher、scanner orchestration。
2. Rust 路由不再依赖 Python legacy 表、legacy JSON 字段或旧 helper 作为主存储。
3. `backend-py`、Python upstream bridge、Python startup wrapper、Python runtime launcher 均已退出主链路。
4. `plan/` 下 canonical 文档只保留 Rust 全接管视角。

## 当前判断

当前还远未完成。

Rust 已拿到部分控制面和若干主存储边界，但 retained Python runtime 仍然存在于：

- agent core
- scanner / queue / workspace / tracking
- tool runtime core
- knowledge / llm / llm_rule
- db / alembic 兼容 gate
