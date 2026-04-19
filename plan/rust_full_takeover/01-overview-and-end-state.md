# Overview And End State

## 文档定位

- 类型：Explanation
- 目标读者：继续执行 Rust 全接管的开发者 / agent

## 目标

当前迁移目标已经统一为：
Rust 接管迁移范围内所有仍承担 live backend / scan / deploy 责任的 Python 代码。

这里的“接管”包含 4 层含义：

1. Rust 成为对应能力的唯一 source of truth。
2. 主运行链不再依赖对应 Python 模块。
3. Python bridge、mirror、compat adapter 不再承担主读写职责。
4. Python 文件、旧测试和文档入口要么删除，要么被明确降级为 archive / tooling。

## 范围

本路线图覆盖：

- `backend_old/app` 下仍承担 live 责任的 Python 运行时
- `backend_old/scripts`、`scripts/release-templates/runner_preflight.py` 这类运行 / 部署尾巴
- 与上述迁移直接相关的 canonical 计划文档

默认不计入 runtime 主计数、但需要保持可解释的内容：

- `scripts/migration/*.py` 这类 inventory / diff tooling
- `plan/wait_correct/*` 这类 raw ledger
- vendored Python 文件和缓存目录

## 完成定义

只有同时满足下面条件，才算“Rust 全接管完成”：

1. `backend_old/app` 不再包含 live Python runtime、service、workflow、tool runtime、knowledge、launcher、scanner orchestration。
2. Rust 路由和后台主链不再依赖 Python legacy 表、legacy JSON 字段或旧 helper 作为主存储。
3. 剩余的 Python 代码不再承担运行 / 部署责任，只能是 archive、tooling 或已明确保留的外部脚本。
4. `backend_old/scripts`、release preflight 等尾巴完成删除，或被明确降级为非运行时资产。
5. canonical 文档只描述 Rust takeover 的当前事实，不再混杂历史性流水账。

## External API Invariants

Rust 接管默认是 ownership 迁移，不自动授权改动前端可见 contract。

在没有单独 frontend migration 条目之前，下面这些约束必须保持：

- 路径前缀仍为 `/api/v1`
- 方法、路径、query 参数名、下载 URL 与 header 语义保持兼容
- SSE 端点继续输出 `text/event-stream`，并维持 `data: <json>\n\n` framing
- 字段命名保持现有 contract，不做隐式 snake_case / camelCase 统一
- 某条 Python route 被标记为 `retire` 之前，必须先证明 frontend / consumer 已清零，或已有 compat stub

## 当前状态

按当前 inventory 和剩余功能组来看，迁移仍处于 retained Python runtime 大量存在的阶段。

当前可以直接确认的是：Rust 已承担一部分外层 route surface，但 retained Python runtime 仍集中存在于：

- scanner / queue / runner
- agent orchestration / state / payload
- flow / logic / graph analysis
- knowledge / tool runtime / LLM
- script host / release preflight 尾巴
