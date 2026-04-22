# Next Targets

> 最后更新：2026-04-22

## 当前阶段判断

Rust 已完成 Phase A-C（基础设施 + DB + 路由 + 共享服务），Phase D 大部分完成（runtime 计算内核全部 Rust 化，Python 仅保留 subprocess bridge 调用层）。

剩余工作集中在 Phase E（Agent 智能层）和 Phase F（最终收口）。

## Phase E：Agent / Tool Runtime（主战场）

Python 66 个文件全部集中在 `app/services/agent/`，构成完整的 LLM 驱动审计 Agent 系统。这是最大也是最复杂的接管目标。

### 建议切片顺序

1. **ORM / Task Models**（2 个文件）— `orm_base.py` + `task_models.py`，纯数据结构，Rust DB 层已有对应 schema
2. **Event Manager / Streaming**（4 个文件）— `event_manager.py` + `streaming/*.py`，SSE 事件推送，Rust route 已有 stream 端点
3. **Config / Runtime Settings**（2 个文件）— `config.py` + `runtime_settings.py`，Agent 配置层
4. **JSON 工具**（2 个文件）— `json_parser.py` + `json_safe.py`，纯工具函数
5. **Tool Base + Runtime Coordinator**（6 个文件）— `tools/base.py` + `tools/runtime/*.py` + `tools/evidence_protocol.py`
6. **Queue / Recon Tools**（3 个文件）— 已调用 Rust queue，Python 层仅做 LLM tool schema 包装
7. **File / Code Analysis Tools**（4 个文件）— `file_tool.py` + `code_analysis_tool.py` + `control_flow_tool.py` + `pattern_tool.py`
8. **Flow / AST Pipeline**（11 个文件）— 流分析核心，依赖 Rust flow-parser/code2flow bridge
9. **Agent 框架 + 类型实现**（15 个文件）— BaseAgent + 5 个 Agent 类型 + react_parser + core/*
10. **Prompts / Skills / Memory / Logic**（8 个文件）— 提示词、skill 目录、记忆、授权逻辑

### 关键依赖

- Agent 框架依赖几乎所有其他模块，应最后接管
- Tool 系统是 Agent 的手脚，需要先于 Agent 框架接管
- Flow/AST pipeline 已有 Rust bridge，Python 层主要是胶水

## Phase F：最终收口

- `scripts/flow_parser_runner.py` — 需要 Rust 化或确认为永久保留的外部脚本
- `scripts/dev-entrypoint.sh` — 开发环境入口，非 Python
- 清空所有 `__init__.py` 空壳
- 删除 `backend_old/tests/` 剩余测试（随对应模块一起退役）
