# Wave A Log

## Completed in this turn

- 新增 Rust 迁移控制面：
  - 路由 inventory 生成脚本
  - Python vs Rust 合同对比脚本
  - `plan/wait_correct/` 基础目录和模板
- Rust control-plane 从 `MemoryStore` 切到真实持久化路径：
  - `system-config`
  - `projects`
- Rust 已接管 `search`：
  - global search
  - projects search
  - tasks search
  - findings search
- Rust 已接管 `skills`：
  - catalog
  - prompt-skills CRUD
  - builtin prompt toggle
  - resources
  - skill detail
  - skill test / tool-test SSE
- `projects` 全域已补齐首批 owned 路由：
  - files / file-content / files-tree
  - upload preview / directory upload
  - stats / dashboard snapshot / static scan overview
  - export / import
  - cache stats / clear / invalidate
- 兼容过渡保留 Python mirror 同步：
  - `system-config`
  - `projects`
- `backend-migration-smoke.yml` 改为 Rust 主导的 smoke

## Wait Correct Entries

### 1. Project metadata persistence falls back to files only when no database pool is configured

- endpoint / feature: `/api/v1/projects/*`
- Python 旧行为: FastAPI + Postgres 持久化
- Rust 当前行为: `DATABASE_URL` 存在时写 `rust_projects` / `rust_project_archives`，缺省时退回文件持久化用于本地测试与迁移期收口
- 是否影响前端: 否，当前 HTTP 契约保持可用
- 后续修复波次: Wave A 后续 / Slice 1
- owner: Rust backend

### 2. Python compatibility mirror is transitional and must be deleted after task engines migrate

- endpoint / feature: `/api/v1/system-config/*`, `/api/v1/projects/*`
- Python 旧行为: Python 直接处理并读自己的表
- Rust 当前行为: Rust 为 source of truth，同时向 Python 旧表做 shadow write，确保代理到 Python 的扫描/任务链路还能读到配置和项目元数据
- 是否影响前端: 否
- 后续修复波次: Wave B / C
- owner: Rust migration

### 3. Static tasks and agent tasks are still not Rust-owned

- endpoint / feature: `/api/v1/static-tasks/*`, `/api/v1/agent-tasks/*`
- Python 旧行为: Python 直接处理
- Rust 当前行为: 仍通过 proxy 回退到 Python
- 是否影响前端: 否，迁移期依然可用
- 后续修复波次: Wave A/B/C
- owner: Rust migration

### 4. Search 和 skills 当前是最小可用契约，不是 Python 旧行为的逐字段复刻

- endpoint / feature: `/api/v1/search/*`, `/api/v1/skills/*`
- Python 旧行为: 依赖旧搜索服务、scan-core 元数据和复杂 DB 关联
- Rust 当前行为: 先提供前端主路径所需最小契约，部分统计和 skill test 结果为迁移期占位输出
- 是否影响前端: 当前主路径不受影响
- 后续修复波次: Wave A 后续 / Wave B
- owner: Rust migration

### 5. non-api python inventory is not yet migrated

- endpoint / feature: `backend_old/*.py`, `backend_old/app/**` except `backend_old/app/api/**`
- Python 旧行为: Python 直接承载 bootstrap、db/model/schema、runtime、upload、scan orchestration、llm、agent 主链路
- Rust 当前行为: Rust 只接管了控制面的一部分，核心 non-API runtime 仍主要由 Python 承担
- 是否影响前端: 当前主路径可用，但迁移目标未完成，mirror 和 proxy 仍必须保留
- 后续修复波次: Wave B / C / D / E / F
- owner: Rust migration
