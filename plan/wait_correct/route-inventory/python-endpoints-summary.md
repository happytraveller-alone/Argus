# Python Endpoint Inventory Summary

- Total routes: `195`
- Migrate: `155`
- Retire: `33`
- Defer: `7`
- Proxy: `0`

- Task route groups (`/api/v1/agent-tasks/*` + `/api/v1/agent-test/*` + `/api/v1/static-tasks/*`) in Python inventory:
  - Total: `117`
  - Proxy: `0`

- Rust gateway status snapshot:
  - `backend/src/routes/mod.rs` 已显式 `nest` 三个路由组：
    - `/api/v1/agent-tasks`
    - `/api/v1/agent-test`
    - `/api/v1/static-tasks`
  - `/api/v1/static-tasks/gitleaks/*` 已标记为 Rust-owned（Python endpoint surface retired）
  - `/api/v1/static-tasks/bandit/*` 已标记为 Rust-owned（Python endpoint surface retired）
  - `/api/v1/static-tasks/phpstan/*` 已标记为 Rust-owned（Python endpoint surface retired）
  - `/api/v1/static-tasks/pmd/*` 已标记为 Rust-owned（Python endpoint surface retired）
  - `/api/v1/static-tasks/rules*` 已标记为 Rust-owned（Python opengrep-rules endpoint surface retired）
  - `/api/v1/static-tasks/tasks*` 与 `/api/v1/static-tasks/findings/{finding_id}/status` 已标记为 Rust-owned（Python opengrep-tasks endpoint surface retired）
  - `/api/v1/static-tasks/cache/*` 已标记为 Rust-owned（Python static-tasks-cache endpoint surface retired）
  - `/api/v1/agent-test/*` 已标记为 Rust-owned（Python agent_test endpoint surface retired）
  - `/api/v1/agent-tasks/{task_id}/report` 与 `/api/v1/agent-tasks/{task_id}/findings/{finding_id}/report` 已标记为 Rust-owned（Python agent_tasks_reporting endpoint surface retired）
  - `/api/v1/agent-tasks/{task_id}/findings*`、`/summary`、`/agent-tree`、`/checkpoints*` 已标记为 Rust-owned（Python agent_tasks_routes_results endpoint surface retired）
  - `/api/v1/agent-tasks`、`/{task_id}`、`/{task_id}/cancel`、`/{task_id}/events*` 已标记为 Rust-owned（Python agent_tasks_routes_tasks endpoint surface retired）
  - legacy `/api/v1/findings/search`、`/api/v1/tasks/search` 已标记为 retired（Rust search 使用 `/api/v1/search/*`）
  - legacy `/api/v1/rules*` 已标记为 retired（规则管理统一使用 `/api/v1/static-tasks/rules*`）
  - `backend/src/proxy.rs` 不存在，gateway 不再提供 Python catch-all proxy 文件入口

- Deployment gate snapshot:
  - `backend-py` 在 `docker-compose.yml`、`docker-compose.hybrid.yml`、`docker-compose.full.yml` 无命中
  - `PYTHON_UPSTREAM_BASE_URL` 在 `docker-compose.yml`、`docker-compose.hybrid.yml`、`docker-compose.full.yml` 无命中
  - compose 变量层已满足“移除 Python backend bridge” gate，后续重点转向清理 Python runtime live surface

- Source inventory: `/Users/apple/Project/AuditTool_private/plan/wait_correct/route-inventory/python-endpoints-inventory.csv`
