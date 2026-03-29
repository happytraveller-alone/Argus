# VulHunter - Repository-Scale Vulnerability Hunting and Security Auditing

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

VulHunter is built for repository-scale security auditing and vulnerability hunting. It combines Multi-Agent orchestration, rule-based scanning, RAG-powered semantic retrieval, and LLM reasoning to connect the full path from suspicious code discovery to optional vulnerability validation.

## Use Cases

- Run a focused security audit before release, delivery, or open-source publication.
- Re-scan existing repositories on a regular basis for leaked secrets, dependency risks, and dangerous code patterns.
- Perform fast triage on third-party repositories, outsourced code, or legacy projects before deeper manual review.
- Give security and engineering teams one place to review findings, inspect evidence, and export audit results.

## How It Finds Vulnerabilities

VulHunter follows a workflow of orchestration -> triage -> deep analysis -> validation:

1. **Multi-Agent orchestration**: an orchestrator coordinates recon, analysis, and verification stages.
2. **Static scanning for first-pass triage**: rule scans, dependency audits, and secret detection surface risky entry points quickly.
3. **RAG-based semantic retrieval**: repository code is indexed for semantic search so related context and similar patterns can be recalled.
4. **LLM-driven deep analysis**: suspicious code paths are examined with code context, data-flow clues, and security reasoning.
5. **Optional PoC sandbox validation**: verification scripts can run in Docker isolation to confirm real issues and reduce false positives.

This workflow is designed for repository-wide audits where both coverage and analysis depth matter.

## Quick Deployment

### 1. Clone the repository

```bash
git clone https://github.com/unbengable12/AuditTool.git
cd AuditTool
```

### 2. Configure backend environment variables

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

At minimum, set your model-related configuration such as `LLM_API_KEY`, `LLM_PROVIDER`, and `LLM_MODEL`. Do not commit real secrets into the repository.

All Dockerfiles, runner image build files, and Docker-specific environment files now live under `docker/`.

### 3. Start the services

The default recommended entrypoint is plain Docker Compose:

```bash
docker compose up --build
```

On Windows, use Docker Desktop with Linux containers.

For the full local build path, add the `docker-compose.full.yml` overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

The default `docker compose up --build` path now only brings up the long-lived compose services and no longer declares one-shot compose runner warmup services.
Instead, backend runs runner preflight during startup to verify the images and commands behind `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE`, and actual scan execution still happens in temporary runner containers started on demand by backend through the Docker SDK.

For optional legacy wrapper helpers, see [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md).

### 4. Open the application

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

Related docs:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/AGENT_AUDIT.md`](docs/AGENT_AUDIT.md) ·
[`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)

## Linux One-Click Deployment (Ubuntu / Debian)

For Ubuntu / Debian systems, the repository ships a unified deployment entry point at [`scripts/deploy-linux.sh`](scripts/deploy-linux.sh) with two modes:

| Mode | Description |
|------|-------------|
| **docker** | Full-featured default — all services run inside Docker Compose containers (recommended) |
| **local** | Frontend, backend, and nexus-web run on the host; PostgreSQL/Redis use local system services; scan runners, flow parser, and PoC sandbox **still require the Docker daemon** |

> **Note:** `local` mode is not "Docker-free". Scan-related containers still need a working Docker Engine on the host.

### Usage

```bash
# Interactive menu (no arguments)
./scripts/deploy-linux.sh

# Non-interactive mode
./scripts/deploy-linux.sh docker   # Start in Docker mode
./scripts/deploy-linux.sh local    # Start in Local mode

# Status (covers both docker and local)
./scripts/deploy-linux.sh status

# Stop all services
./scripts/deploy-linux.sh stop
```

### Local Mode Details

- Auto-installs: `git`, `curl`, `python3`, `uv`, `nodejs ≥20`, `pnpm`, `postgresql`, `redis-server`, `docker.io`
- Auto-generates `backend/.env.local` with localhost overrides for database/Redis
- Runs `alembic upgrade head` for database migrations
- Frontend uses the build-then-preview path (`pnpm build` → `vite preview`) on port 3000
- nexus-web is automatically cloned to `nexus-web/src` on first run; subsequent runs run `git fetch`
- PIDs are written to `.deploy/pids/`, logs to `.deploy/logs/`

### Troubleshooting

| Problem | Solution |
|---------|---------|
| Port already in use | Run `./scripts/deploy-linux.sh stop` then retry, or free the port manually |
| `docker: permission denied` | Run `newgrp docker` or log out and back in to apply the docker group |
| nexus-web clone timeout | Set `NEXUS_WEB_GIT_MIRROR_PREFIX=` (empty) to bypass the mirror and connect directly, or configure a proxy |
| Backend migration fails | Check PostgreSQL status: `sudo systemctl status postgresql` |
