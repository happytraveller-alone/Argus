# VulHunter - Intelligent Security & Compliance Auditing for Repositories

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>





VulHunter is an intelligent auditing platform for repository-scale projects. It is built on a **Multi-Agent** collaboration workflow (Orchestrator / Recon / Analysis / Verification) and combines:

- **LLM (Reasoning)**: vulnerability analysis, reasoning, and remediation suggestions
- **RAG (Vector Indexing / Code Embeddings)**: vector indexing of code to enable semantic retrieval and better context

Optionally, VulHunter can run PoC validation inside a Docker sandbox.


## Key Capabilities

- **Agent Audit**: Multi-Agent collaboration and orchestration
- **Potential Findings**: unified findings list with severity shown in Chinese tiers (严重 / 高危 / 中危 / 低危)
- **Split LLM and RAG configuration**: LLM for reasoning, RAG for vector indexing and retrieval
- **Docker Sandbox PoC validation (optional)**: requires Docker socket mounting
- **Rule-based scanning**: aggregation of static rule tool outputs (e.g., Opengrep, Gitleaks)
- **Report export**: PDF / Markdown / JSON

## Architecture (High Level)

```text
React + TypeScript (frontend)
        |
        |  HTTP / SSE (/api/v1/*)
        v
FastAPI (backend)
        |
        v
PostgreSQL + Redis + Docker Sandbox(optional)
```

For details: `docs/ARCHITECTURE.md`.

## Quick Start (Docker Compose)

### 1) Clone

```bash
git clone https://github.com/unbengable12/AuditTool.git
cd AuditTool
```

### 2) Configure backend env

```bash
cp backend/env.example backend/.env
# Edit backend/.env and set your LLM_API_KEY / LLM_PROVIDER / LLM_MODEL, etc.
```

Do not commit real API keys into the repository.

### 3) Run (default: local source build)

```bash
./scripts/compose-up-with-fallback.sh
```

To use the default day-to-day incremental development flow directly (recommended, containerized hot reload for both frontend and backend):

```bash
docker compose up -d --build
```

To run the explicit full local build path:

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d --build
```

To run the full local build path through the mirror-probing fallback script:

```bash
./scripts/compose-up-with-fallback.sh -f docker-compose.yml -f docker-compose.full.yml up -d --build
```

If you want attached-mode debugging on WSL/Linux, explicitly disable the Compose interactive menu to avoid `watch` shortcut crashes on affected Compose builds:

```bash
COMPOSE_MENU=false docker compose up --build
# or
docker compose up --build --menu=false
```

If you want the Bash/WSL/Linux wrapper to auto-open the app after readiness is confirmed, opt in explicitly:

```bash
VULHUNTER_OPEN_BROWSER=1 ./scripts/compose-up-with-fallback.sh
```

If you want prebuilt-image deployment (production / quick bootstrap), use:

```bash
docker compose -f deploy/compose/docker-compose.prod.yml up -d
# or (CN-accelerated variant)
docker compose -f deploy/compose/docker-compose.prod.cn.yml up -d
```

### 4) Open

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (OpenAPI: http://localhost:8000/docs)
- If `3000` or `8000` is already in use, override them with `VULHUNTER_FRONTEND_PORT` / `VULHUNTER_BACKEND_PORT`, for example `VULHUNTER_BACKEND_PORT=18000 docker compose up -d --build`

### Notes

- The backend mounts `/var/run/docker.sock` for sandbox execution. Review security boundaries before using in production.
- The root Compose default now targets day-to-day incremental development: `docker compose up -d --build`. This path switches frontend/backend to bind-mounted source + hot reload and disables heavyweight startup defaults such as `MCP_REQUIRE_ALL_READY_ON_STARTUP` and `SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP`.
- The default dev Compose now waits for backend `/health` before starting the frontend; on the first `docker compose up --build`, expect a 1-2 minute delay while seed projects and rules initialize.
- Once cold start actually finishes, both the frontend dev container and `./scripts/compose-up-with-fallback.sh` print a ready banner with `http://localhost:3000` and the backend docs URL.
- For the explicit full local build path, add `docker-compose.full.yml`: `docker compose -f docker-compose.yml -f docker-compose.full.yml up -d --build`.
- The fallback-script variant of the full local build path is `./scripts/compose-up-with-fallback.sh -f docker-compose.yml -f docker-compose.full.yml up -d --build`.
- Bare `docker compose up --build` only prints the ready hint; it does not auto-open a browser. Use `VULHUNTER_OPEN_BROWSER=1 ./scripts/compose-up-with-fallback.sh` if you want that behavior.
- Local Compose startup, including the `docker-compose.full.yml` overlay, now disables Codex skills preinstallation by default so remote skill sync cannot block the backend.
- To temporarily restore that preinstall step, run: `CODEX_SKILLS_AUTO_INSTALL=true docker compose -f docker-compose.yml -f docker-compose.full.yml up --build --menu=false`.
- To install Codex skills manually after the container is up, run: `docker compose -f docker-compose.yml -f docker-compose.full.yml exec backend /app/scripts/install_codex_skills.sh`.
- If you run attached `docker compose up` on WSL/Linux, use `COMPOSE_MENU=false docker compose up --build` or `docker compose up --build --menu=false`; after upgrading to Docker Compose `>= 2.37.2`, the default menu behavior is safe again.
- Adminer is now an on-demand tools profile: `docker compose --profile tools up -d adminer`.
- If you only need the default frontend dev container, use `./scripts/dev-frontend.sh` or `frontend/scripts/run-in-dev-container.sh`.
- Prebuilt-image deployment templates now live at `deploy/compose/docker-compose.prod.yml` and `deploy/compose/docker-compose.prod.cn.yml`.
- Those production templates use the Nanjing University GHCR mirror (`ghcr.nju.edu.cn/lintsinghua/*`) for faster pulls in CN regions. Replace with your own images/registry for production deployments if needed.
- The dev build flow defaults to `./scripts/compose-up-with-fallback.sh`: it probes candidate mirrors first, ranks by latency, then retries build phases in ranked order (instead of fixed CN->official phases).
- For `up` and `up -d`, `./scripts/compose-up-with-fallback.sh` waits until both the frontend and backend `/health` are reachable before printing a unified `services ready` banner. Override the wait budget with `VULHUNTER_READY_TIMEOUT_SECONDS`; the default is `900`.
- Docker image source probing (DockerHub/GHCR) now runs in parallel; failed candidates are downgraded to the tail instead of blocking other sources.
- Default DockerHub candidates: `docker.m.daocloud.io/library,docker.1ms.run/library,docker.io/library`; default GHCR candidates: `ghcr.nju.edu.cn,ghcr.m.daocloud.io,ghcr.io`.
- DockerHub official probing uses `registry-1.docker.io` to avoid inaccurate checks against `docker.io`.
- The script enables BuildKit by default (`DOCKER_BUILDKIT=1`, `COMPOSE_DOCKER_CLI_BUILD=1`), and you can override both.
- You can override mirror endpoints with `DOCKERHUB_LIBRARY_MIRROR` and `SANDBOX_IMAGE`.
- DockerHub/GHCR candidate priority is: `*_CANDIDATES` > plural `CN_*` vars (`CN_DOCKERHUB_LIBRARY_MIRRORS` / `CN_GHCR_REGISTRIES`) > legacy singular vars (`CN_DOCKERHUB_LIBRARY_MIRROR` / `CN_GHCR_REGISTRY`) > built-in defaults.
- You can extend probe pools via comma-separated `*_CANDIDATES`, or explicitly set `*_PRIMARY` / `*_FALLBACK` to skip probing for that category.
- Backend Node/pnpm build now supports mirror-first + official fallback; override with `BACKEND_NPM_REGISTRY_PRIMARY`, `BACKEND_NPM_REGISTRY_FALLBACK`, and `BACKEND_PNPM_VERSION`.
- Local Compose now disables pnpm optional dependencies by default (`BACKEND_PNPM_INSTALL_OPTIONAL=0`) to avoid long `node-llama-cpp` retry loops; set it to `1` if you require full optional dependencies.
- Local Compose now skips CJK font installation by default (`BACKEND_INSTALL_CJK_FONTS=0`) to speed up builds; set it to `1` if you need Chinese font rendering.
- Running `docker compose up -d --build` directly does not include automatic mirror fallback logic.
- GitHub source sync and task repo download/clone now use a two-step proxy chain by default: `https://gh-proxy.org` -> `https://v6.gh-proxy.org`.
- Fallback to origin GitHub is disabled by default (`GIT_MIRROR_FALLBACK_TO_ORIGIN=false`); enable it only for troubleshooting.
Example:

```bash
DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library \
SANDBOX_IMAGE=ghcr.nju.edu.cn/lintsinghua/vulhunter-sandbox:latest \
./scripts/compose-up-with-fallback.sh
```

Custom DockerHub/GHCR CN candidate pools:

```bash
CN_DOCKERHUB_LIBRARY_MIRRORS=docker.m.daocloud.io/library,docker.1ms.run/library \
CN_GHCR_REGISTRIES=ghcr.nju.edu.cn,ghcr.m.daocloud.io \
./scripts/compose-up-with-fallback.sh
```

Backend Node/pnpm mirror fallback example:

```bash
BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com \
BACKEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org \
BACKEND_PNPM_VERSION=9.15.4 \
BACKEND_PNPM_INSTALL_OPTIONAL=0 \
BACKEND_INSTALL_CJK_FONTS=0 \
./scripts/compose-up-with-fallback.sh
```

GitHub proxy chain example:

```bash
GIT_MIRROR_PREFIXES=https://gh-proxy.org,https://v6.gh-proxy.org \
GIT_MIRROR_FALLBACK_TO_ORIGIN=false \
./scripts/compose-up-with-fallback.sh
```

### Common startup error: `Can't locate revision identified by 'xxx'`

This usually means the Alembic revision stored in the DB volume does not match the migration files in the current backend image (for example, after switching from prebuilt images to local source builds).

Recommended recovery order:

1. Ensure startup uses local source build:

```bash
./scripts/compose-up-with-fallback.sh
```

2. If it still fails and you can discard local test data, do a one-time PostgreSQL volume reset and rebuild:

```bash
docker compose down
docker volume rm audittool_postgres_data
./scripts/compose-up-with-fallback.sh
```

⚠️ This removes local DB data. Back up important data first.

## Development

### Frontend (Vite)

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev
```

### Backend (uv + FastAPI)

```bash
cd backend
cp env.example .env
uv sync
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Sandbox (optional)

- For development, the sandbox image is typically built/used via `docker compose`. See `docker/sandbox/`.

## Documentation Index

- `docs/ARCHITECTURE.md`
- `docs/CONFIGURATION.md`
- `docs/DEPLOYMENT.md`
- `docs/AGENT_AUDIT.md`

Note: `docs/` may still contain historical names like `AuditTool` / `deepaudit` (deployment/code-level legacy naming), which do not represent the product brand.

## Contributing

- `CONTRIBUTING.md`
- `SECURITY.md`
- Issues: `https://github.com/unbengable12/AuditTool/issues`

## License

This project is licensed under the [AGPL-3.0 License](LICENSE).

## Security & Compliance Notice

- Do not run security testing against targets you do not own or have explicit authorization for.
- For details, see: `DISCLAIMER.md` and `SECURITY.md`.

## Known Gaps

- `backend/pyproject.toml` currently declares `license = MIT` while the repository root `LICENSE` is AGPL-3.0. This README update does not change code or licensing files; the mismatch should be resolved separately.

## Naming History

Some internal identifiers may keep historical naming (e.g., `deepaudit`). This is legacy naming and does not affect VulHunter usage.
