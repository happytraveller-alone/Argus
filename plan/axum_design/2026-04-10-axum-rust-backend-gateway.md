# Axum Rust Backend Gateway Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增一个基于 Axum 的 Rust 后端网关，在不删除旧 Python 后端的前提下接管公开入口，并在首批直接实现 `health`、`system-config`、`projects` 的去用户化接口。

**Architecture:** Rust `backend` 服务作为唯一公开 API 入口，直接处理首批拥有的路由，其余 `/api/v1/*` 请求透明转发到内部 `backend-py`。Rust 使用独立 Postgres schema 和文件卷保存系统配置与 ZIP 项目，不复用 Python 的 `users`、`user_configs`、`projects.owner_id` 等历史结构；前端同步切换到新的无用户契约，并删除现有 `nexus-web` 第三页面服务及首页嵌入依赖。

**Tech Stack:** Rust, Axum, Tokio, SQLx, Reqwest, Tower HTTP, Serde, PostgreSQL, Docker Compose, React, TypeScript

---

### Task 1: Scaffold The Rust Gateway Workspace

**Files:**
- Create: `backend/Cargo.toml`
- Create: `backend/src/main.rs`
- Create: `backend/src/app.rs`
- Create: `backend/src/config.rs`
- Create: `backend/src/state.rs`
- Create: `backend/src/error.rs`
- Create: `backend/src/routes/mod.rs`

- [ ] **Step 1: Write the failing smoke test**

Create `backend/tests/http_smoke.rs` with a minimal startup test that boots the Axum app and asserts:

- `GET /health` returns `200`
- `GET /api/v1/unknown-route` is not handled locally yet

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend-rust && cargo test http_smoke -- --nocapture`

Expected: FAIL because the Rust service and route tree do not exist yet.

- [ ] **Step 3: Create the Cargo workspace and runtime shell**

Add dependencies in `backend/Cargo.toml` for:

- `axum`
- `tokio`
- `serde`
- `serde_json`
- `sqlx` with `postgres`, `runtime-tokio-rustls`, `uuid`, `time`, `json`
- `reqwest`
- `tower-http`
- `tracing`, `tracing-subscriber`
- `uuid`
- `time`
- `thiserror`
- `anyhow`

Create:

- `src/main.rs` to load config, create state, build router, and bind the server
- `src/app.rs` to compose the router
- `src/config.rs` to parse environment variables
- `src/state.rs` to hold shared DB pool, HTTP client, upload root, and Python upstream base URL
- `src/error.rs` for a unified API error type

- [ ] **Step 4: Re-run the smoke test**

Run: `cd backend-rust && cargo test http_smoke -- --nocapture`

Expected: PASS for app bootstrap and the health endpoint.

- [ ] **Step 5: Commit**

Run: `git add backend-rust && git commit -m "feat: scaffold axum backend gateway"`

If `.git` metadata is unavailable in the current workspace, skip the commit and keep the changes staged in the implementation session journal.

### Task 2: Add Reverse Proxy Fallback To Python

**Files:**
- Create: `backend/src/proxy.rs`
- Modify: `backend/src/app.rs`
- Create: `backend/tests/proxy_fallback.rs`

- [ ] **Step 1: Write the failing proxy contract test**

Create `backend/tests/proxy_fallback.rs` that spins up:

- a fake Python upstream server
- the Axum gateway

Assert that:

- an unmigrated `GET /api/v1/agent-tasks/demo` is forwarded upstream
- upstream status code, headers, and JSON body are preserved
- multipart and query strings are forwarded unchanged

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `cd backend-rust && cargo test proxy_fallback -- --nocapture`

Expected: FAIL because no fallback proxy exists yet.

- [ ] **Step 3: Implement the reverse proxy layer**

Create `src/proxy.rs` with a catch-all proxy handler that:

- matches unmigrated `/api/v1/*` paths
- rebuilds the upstream URL using `PYTHON_UPSTREAM_BASE_URL`
- forwards method, query string, headers, and body with `reqwest`
- streams the upstream response back to the client
- strips or rewrites only hop-by-hop headers

Wire the handler in `src/app.rs` so explicitly owned Rust routes are registered first, and proxy fallback is registered last.

- [ ] **Step 4: Re-run the proxy contract test**

Run: `cd backend-rust && cargo test proxy_fallback -- --nocapture`

Expected: PASS, proving the gateway is safe before it owns business logic.

- [ ] **Step 5: Commit**

Run: `git add backend/src/proxy.rs backend/src/app.rs backend/tests/proxy_fallback.rs && git commit -m "feat: add python fallback proxy for unmigrated routes"`

### Task 3: Add Rust-Owned System Config Storage And Endpoints

**Files:**
- Create: `backend/migrations/0001_system_configs.sql`
- Create: `backend/src/db/mod.rs`
- Create: `backend/src/db/system_config.rs`
- Create: `backend/src/routes/system_config.rs`
- Create: `backend/tests/system_config_api.rs`
- Modify: `backend/src/routes/mod.rs`
- Modify: `backend/src/app.rs`

- [ ] **Step 1: Write the failing system-config API tests**

Create `backend/tests/system_config_api.rs` covering:

- `GET /api/v1/system-config/defaults`
- `GET /api/v1/system-config`
- `PUT /api/v1/system-config`
- `DELETE /api/v1/system-config`
- `GET /api/v1/system-config/llm-providers`

Assert that:

- config responses contain `llmConfig` and `otherConfig`
- responses do not contain `id` or `user_id`
- saving and clearing config works without user context

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend-rust && cargo test system_config_api -- --nocapture`

Expected: FAIL because neither schema nor handlers exist.

- [ ] **Step 3: Create the new schema**

Add `backend/migrations/0001_system_configs.sql` with a table shaped like:

```sql
create table if not exists system_configs (
    id text primary key,
    llm_config_json jsonb not null default '{}'::jsonb,
    other_config_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
```

Use a fixed singleton key such as `default`.

- [ ] **Step 4: Implement the DB layer and handlers**

In `src/db/system_config.rs` implement:

- `load_defaults()`
- `load_current()`
- `save_current()`
- `clear_current()`

In `src/routes/system_config.rs` implement the public handlers and payload structs. Keep payloads de-userized:

```json
{
  "llmConfig": {},
  "otherConfig": {}
}
```

Do not return fake `id` or `user_id`.

- [ ] **Step 5: Add LLM support helper endpoints**

Implement these Rust-owned endpoints in the same route module:

- `GET /api/v1/system-config/llm-providers`
- `POST /api/v1/system-config/test-llm`
- `POST /api/v1/system-config/fetch-llm-models`
- `POST /api/v1/system-config/agent-preflight`

Rules:

- keep provider metadata static or Rust-local, not Python-coupled
- `test-llm` and `fetch-llm-models` call external providers directly from Rust
- `agent-preflight` checks only system-config completeness and connectivity; it must not depend on Python `AgentTask`

- [ ] **Step 6: Re-run the system-config tests**

Run: `cd backend-rust && cargo test system_config_api -- --nocapture`

Expected: PASS for CRUD plus the public config helpers.

- [ ] **Step 7: Commit**

Run: `git add backend/migrations/0001_system_configs.sql backend/src/db backend/src/routes/system_config.rs backend/tests/system_config_api.rs backend/src/app.rs backend/src/routes/mod.rs && git commit -m "feat: add rust system-config api"`

### Task 4: Add Rust-Owned Project Schema And ZIP CRUD

**Files:**
- Create: `backend/migrations/0002_rust_projects.sql`
- Create: `backend/src/db/projects.rs`
- Create: `backend/src/routes/projects.rs`
- Create: `backend/tests/projects_api.rs`
- Modify: `backend/src/routes/mod.rs`
- Modify: `backend/src/app.rs`

- [ ] **Step 1: Write the failing project API tests**

Create `backend/tests/projects_api.rs` covering:

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `PUT /api/v1/projects/{id}`
- `GET /api/v1/projects/info/{id}`
- `POST /api/v1/projects/create-with-zip`
- `GET /api/v1/projects/{id}/zip`
- `POST /api/v1/projects/{id}/zip`
- `DELETE /api/v1/projects/{id}/zip`

Assert that:

- project responses do not contain `owner_id`
- only `zip` source type is accepted
- ZIP metadata is persisted and returned consistently

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend-rust && cargo test projects_api -- --nocapture`

Expected: FAIL because project schema and routes do not exist.

- [ ] **Step 3: Create the new project tables**

Add `backend/migrations/0002_rust_projects.sql` with:

- `rust_projects`
- `rust_project_archives`

Minimum shape:

```sql
create table if not exists rust_projects (
    id uuid primary key,
    name text not null,
    description text,
    source_type text not null default 'zip',
    repository_type text not null default 'other',
    default_branch text not null default 'main',
    programming_languages_json jsonb not null default '[]'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
```

and a separate archive table keyed by `project_id`.

- [ ] **Step 4: Implement project CRUD and ZIP storage**

In `src/db/projects.rs` implement repository functions for:

- create/list/get/update project
- save/load/delete archive metadata

In `src/routes/projects.rs` implement:

- CRUD handlers
- multipart upload handling for `create-with-zip` and `/{id}/zip`
- archive metadata lookup
- ZIP delete

Store ZIP files under a dedicated upload root such as `uploads/rust-projects/<project-id>/source.zip`.

- [ ] **Step 5: Keep unsupported project routes out of scope**

Do not implement in this task:

- `/files`
- `/files-tree`
- file content streaming
- stats
- dashboard snapshot
- export/import
- members

Those paths must continue to proxy to Python.

- [ ] **Step 6: Re-run the project API tests**

Run: `cd backend-rust && cargo test projects_api -- --nocapture`

Expected: PASS for the Rust-owned project subset.

- [ ] **Step 7: Commit**

Run: `git add backend/migrations/0002_rust_projects.sql backend/src/db/projects.rs backend/src/routes/projects.rs backend/tests/projects_api.rs backend/src/app.rs backend/src/routes/mod.rs && git commit -m "feat: add rust project zip crud api"`

### Task 5: Switch Frontend To The New De-Userized Contract

**Files:**
- Modify: `frontend/src/shared/api/database.ts`
- Modify: `frontend/src/shared/types/index.ts`
- Modify: `frontend/src/components/system/SystemConfig.tsx`
- Modify: `frontend/src/pages/projects/data/createApiProjectsPageDataSource.ts`
- Modify: `frontend/src/pages/projects/data/projectsPageWorkflows.ts`
- Test: `frontend/tests/projectDescriptionApi.test.ts`
- Test: `frontend/tests/projectsPageDataSource.test.ts`

- [ ] **Step 1: Write or update frontend contract tests**

Add or update tests to assert:

- config API uses `/system-config` instead of `/config/me`
- config payloads no longer require `user_id`
- project payload mapping no longer requires `owner_id`
- project create/update flows still work for ZIP-only projects

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `cd frontend && npm test -- projectsPageDataSource projectDescriptionApi`

Expected: FAIL because the client still targets old config routes and old payloads.

- [ ] **Step 3: Update the API client and types**

In `frontend/src/shared/api/database.ts`:

- replace `/config/defaults` and `/config/me*` usage with `/system-config*`
- rename `UserConfigPayload` to a de-userized shape
- remove `user_id`
- keep `llmConfig` and `otherConfig`

In `frontend/src/shared/types/index.ts`:

- remove `owner_id` from the primary `Project` type used by Rust-owned flows
- remove or isolate member-management assumptions from migrated views

- [ ] **Step 4: Update UI consumers**

Adjust:

- `SystemConfig.tsx` to read and write the new system config payload
- project page data source and workflows to work without `owner_id`

Do not rewrite unrelated project detail, code browser, or agent-task pages in this task.

- [ ] **Step 5: Re-run the frontend tests**

Run: `cd frontend && npm test -- projectsPageDataSource projectDescriptionApi`

Expected: PASS for the new API contract.

- [ ] **Step 6: Commit**

Run: `git add frontend/src/shared/api/database.ts frontend/src/shared/types/index.ts frontend/src/components/system/SystemConfig.tsx frontend/src/pages/projects/data/createApiProjectsPageDataSource.ts frontend/src/pages/projects/data/projectsPageWorkflows.ts frontend/tests/projectsPageDataSource.test.ts frontend/tests/projectDescriptionApi.test.ts && git commit -m "refactor: switch frontend to rust gateway contracts"`

### Task 6: Wire Docker Compose So Rust Is The Public Backend

**Files:**
- Create: `backend/docker/backend-rust.Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `frontend/scripts/dev-entrypoint.sh`
- Modify: `frontend/src/shared/api/serverClient.ts`
- Create: `backend/.sqlx/` metadata only if the implementation uses offline SQLx checks

- [ ] **Step 1: Write a failing compose contract test or checklist**

Add a lightweight contract test or scripted check that validates:

- public `backend` service is Rust
- Python service becomes `backend-py`
- Rust proxies to `http://backend-py:8001`
- frontend still targets `http://backend:8000`

- [ ] **Step 2: Run the contract check to verify it fails**

Run: `docker compose config`

Expected: the current compose output still exposes Python directly as `backend`.

- [ ] **Step 3: Create the Rust backend image**

Add `backend/docker/backend-rust.Dockerfile` that:

- builds the Rust binary in a builder stage
- copies the binary into a slim runtime image
- exposes port `8000`
- mounts the shared uploads volume

- [ ] **Step 4: Rewire compose topology**

Update `docker-compose.yml` so that:

- `backend` is the Rust gateway
- `backend-py` is the old FastAPI service
- `backend-py` listens on internal `8001`
- `backend` receives `PYTHON_UPSTREAM_BASE_URL=http://backend-py:8001`
- frontend keeps using `backend` as its only API target

- [ ] **Step 5: Re-run the contract check**

Run: `docker compose config`

Expected: Rust is the public backend and Python is internal only.

- [ ] **Step 6: Commit**

Run: `git add backend/docker/backend-rust.Dockerfile docker-compose.yml frontend/scripts/dev-entrypoint.sh frontend/src/shared/api/serverClient.ts && git commit -m "chore: make rust gateway the public backend"`

### Task 7: End-To-End Verification Before Expanding Scope

**Files:**
- Verify only

- [ ] **Step 1: Run Rust test suite**

Run: `cd backend-rust && cargo test -- --nocapture`

Expected: PASS

- [ ] **Step 2: Run focused frontend tests**

Run: `cd frontend && npm test -- projectsPageDataSource projectDescriptionApi`

Expected: PASS

- [ ] **Step 3: Run compose config validation**

Run: `docker compose config`

Expected: PASS with Rust as public backend and Python as upstream only.

- [ ] **Step 4: Manual smoke test**

Run the stack and verify:

- `GET /health` returns Rust health payload
- `GET /api/v1/system-config` is served by Rust
- `POST /api/v1/projects/create-with-zip` is served by Rust
- `GET /api/v1/agent-tasks/...` is transparently proxied to Python

- [ ] **Step 5: Review the diff for scope discipline**

Run: `git diff -- backend-rust docker-compose.yml frontend/src/shared/api/database.ts frontend/src/shared/types/index.ts frontend/src/components/system/SystemConfig.tsx frontend/src/pages/projects/data`

Expected: only gateway scaffolding, new Rust-owned APIs, compose rewiring, and frontend contract updates are included.

- [ ] **Step 6: Final commit**

Run: `git add backend-rust backend/docker/backend-rust.Dockerfile docker-compose.yml frontend/src/shared/api/database.ts frontend/src/shared/types/index.ts frontend/src/components/system/SystemConfig.tsx frontend/src/pages/projects/data && git commit -m "feat: introduce axum backend gateway for config and projects"`
