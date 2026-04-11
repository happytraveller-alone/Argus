# Python Endpoint Inventory Summary

- Total routes: `179`
- Migrate: `120`
- Retire: `20`
- Defer: `7`
- Proxy: `32`

- Task route groups (`/api/v1/agent-tasks/*` + `/api/v1/agent-test/*` + `/api/v1/static-tasks/*`) in Python inventory:
  - Total: `101`
  - Proxy: `19`

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
  - `backend/src/proxy.rs` 不存在，gateway 不再提供 Python catch-all proxy 文件入口

- Deployment gate snapshot:
  - `backend-py` 在 `docker-compose.yml`、`docker-compose.hybrid.yml`、`docker-compose.full.yml` 无命中
  - `PYTHON_UPSTREAM_BASE_URL` 在 `docker-compose.yml`、`docker-compose.hybrid.yml`、`docker-compose.full.yml` 无命中
  - compose 变量层已满足“移除 Python backend bridge” gate，后续重点转向清理 Python runtime live surface

- Source inventory: `/Users/apple/Project/AuditTool_private/plan/wait_correct/route-inventory/python-endpoints-inventory.csv`
