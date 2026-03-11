# VulHunter - Intelligent Security & Compliance Auditing for Repositories

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

<div align="center">
  <img src="frontend/public/images/logo.png" alt="VulHunter Logo" width="420" />
</div>

<div align="center">

[![Version](https://img.shields.io/badge/version-3.0.4-blue.svg)](CHANGELOG.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178c6.svg)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab.svg)](https://www.python.org/)

</div>

VulHunter is an intelligent auditing platform for repository-scale projects. It is built on a **Multi-Agent** collaboration workflow (Orchestrator / Recon / Analysis / Verification) and combines:

- **LLM (Reasoning)**: vulnerability analysis, reasoning, and remediation suggestions
- **RAG (Vector Indexing / Code Embeddings)**: vector indexing of code to enable semantic retrieval and better context

Optionally, VulHunter can run PoC validation inside a Docker sandbox.

## Screenshots

<div align="center">

### Agent Audit Entry

<img src="frontend/public/images/README-show/Agent审计入口（首页）.png" alt="VulHunter Agent Audit Entry" width="90%">

</div>

<table>
<tr>
<td width="50%" align="center">
<strong>Event Logs</strong><br/><br/>
<img src="frontend/public/images/README-show/审计流日志.png" alt="Event Logs" width="95%"><br/>
<em>Watch agent reasoning and execution in real time</em>
</td>
<td width="50%" align="center">
<strong>Dashboard</strong><br/><br/>
<img src="frontend/public/images/README-show/仪表盘.png" alt="Dashboard" width="95%"><br/>
<em>Project security posture at a glance</em>
</td>
</tr>
<tr>
<td width="50%" align="center">
<strong>Instant Analysis</strong><br/><br/>
<img src="frontend/public/images/README-show/即时分析.png" alt="Instant Analysis" width="95%"><br/>
<em>Paste code or upload files, get results quickly</em>
</td>
<td width="50%" align="center">
<strong>Project Management</strong><br/><br/>
<img src="frontend/public/images/README-show/项目管理.png" alt="Project Management" width="95%"><br/>
<em>Import repos or upload ZIP, manage multiple projects</em>
</td>
</tr>
</table>

<div align="center">

### Report Export

<img src="frontend/public/images/README-show/审计报告示例.png" alt="Audit Report" width="90%">

<em>Export to PDF / Markdown / JSON</em>

</div>

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

To use the repository's default local Docker build path directly:

```bash
docker compose up -d --build
```

To explicitly enable local Joern / CodeBadger:

```bash
docker compose --profile joern up -d --build
```

If you want prebuilt-image deployment (production / quick bootstrap), use:

```bash
docker compose -f docker-compose.prod.yml up -d
# or (CN-accelerated variant)
docker compose -f docker-compose.prod.cn.yml up -d
```

### 4) Open

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (OpenAPI: http://localhost:8000/docs)
- If `3000` or `8000` is already in use, override them with `VULHUNTER_FRONTEND_PORT` / `VULHUNTER_BACKEND_PORT`, for example `VULHUNTER_BACKEND_PORT=18000 docker compose up -d --build`

### Notes

- The backend mounts `/var/run/docker.sock` for sandbox execution. Review security boundaries before using in production.
- The only repository-local image build path is the root default Compose flow: `docker compose up -d --build` (or `./scripts/compose-up-with-fallback.sh`). By default it does not start Joern / CodeBadger containers.
- To enable local Joern / CodeBadger, use `docker compose --profile joern up -d --build`, or `./scripts/compose-up-with-fallback.sh --profile joern up -d --build`.
- `docker-compose.prod.yml` / `docker-compose.prod.cn.yml` remain prebuilt-image deployment flows; they do not build CodeBadger inside this repository.
- `docker-compose.prod.yml` and `docker-compose.prod.cn.yml` use the Nanjing University GHCR mirror (`ghcr.nju.edu.cn/lintsinghua/*`) for faster pulls in CN regions. Replace with your own images/registry for production deployments if needed.
- The dev build flow defaults to `./scripts/compose-up-with-fallback.sh`: it probes candidate mirrors first, ranks by latency, then retries build phases in ranked order (instead of fixed CN->official phases).
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
- Default local Compose does not start the bundled CodeBadger services; when absent, Joern deep analysis degrades automatically to the lightweight flow path.
- `docker-compose.prod.yml` / `docker-compose.prod.cn.yml` require an explicitly configured external CodeBadger service if you want Joern deep analysis:
  - `MCP_CODEBADGER_ENABLED=true`
  - `MCP_CODEBADGER_BACKEND_URL=http://your-codebadger-host:4242/mcp`
  - `JOERN_MCP_ENABLED=true`
  - `JOERN_MCP_URL=http://your-codebadger-host:4242/mcp`

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

Example: external CodeBadger on the production flow

```bash
MCP_CODEBADGER_ENABLED=true \
MCP_CODEBADGER_BACKEND_URL=http://codebadger.example.internal:4242/mcp \
JOERN_MCP_ENABLED=true \
JOERN_MCP_URL=http://codebadger.example.internal:4242/mcp \
docker compose -f docker-compose.prod.yml up -d
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
