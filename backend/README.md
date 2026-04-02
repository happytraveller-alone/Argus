# VulHunter Backend

VulHunter backend is a FastAPI service that powers repository-scale auditing, including:

- HTTP APIs under `/api/v1/*`
- Server-Sent Events (SSE) streaming for Agent Audit events
- LLM (reasoning) + RAG (vector indexing / embeddings) configuration
- Optional Docker sandbox execution for PoC validation

## Run with Docker (recommended)

Backend Docker deployment now has two explicit modes:

- `dev-with-source-mount`: local development, backend mounts host source tree
- `self-contained-image`: deployment mode, backend runs without mounting host source code

From the repository root:

```bash
# dev-with-source-mount
docker compose up

# self-contained-image
docker compose -f docker-compose.yml -f docker-compose.self-contained.yml up -d

# full local build
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

Frontend is exposed at `http://localhost:3000`, backend at `http://localhost:8000`.
On Windows, use Docker Desktop with Linux containers.
If `docker/env/backend/.env` is missing on first startup, Compose now bootstraps it automatically from `docker/env/backend/env.example`.
If either host port is already in use, start Compose with `VULHUNTER_FRONTEND_PORT` / `VULHUNTER_BACKEND_PORT`, for example `VULHUNTER_BACKEND_PORT=18000 docker compose up`.
For the full local build path, run `./scripts/compose-up-local-build.sh` or `docker compose -f docker-compose.yml -f docker-compose.full.yml up --build`.
For source-free deployment, use `docker compose -f docker-compose.yml -f docker-compose.self-contained.yml up -d`.
The default compose startup now only brings up the long-lived services.
Instead, backend runs the configured runner preflight during startup to verify the images and commands behind `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE`.
Those compose services are not the runtime scan workers. During actual scans, backend uses the Docker SDK and `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` to start temporary runner containers on demand.

### Default seed projects (persistent)

On first startup (`docker compose up` or `docker compose -f docker-compose.yml -f docker-compose.self-contained.yml up -d`), backend downloads the pinned GitHub archive snapshots for the demo user and stores them as persistent ZIP projects:

- `libplist`
- `DVWA`
- `DSVW`
- `WebGoat`
- `JavaSecLab`
- `govwa`
- `fastjson`

The installer probes configured GitHub mirror candidates plus the official GitHub source, sorts them by latency, and downloads from the fastest reachable source first.

Project ZIPs are installed once and persisted in Docker volumes (`postgres_data` + `backend_uploads`), so subsequent restarts/rebuilds reuse them directly.

If all candidates fail during first startup, backend still starts successfully and retries the missing project archives on the next startup.

## Local Development

### 1) Environment

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

If you start from the repository root with `./scripts/compose-up-local-build.sh` or `./scripts/compose-up-with-fallback.sh`, those Docker entrypoints now auto-create `docker/env/backend/.env` from `docker/env/backend/env.example` on first use.

Edit `docker/env/backend/.env` and set at least:

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL` (optional)
- `LLM_BASE_URL` (optional)

Do not commit real API keys.

### 2) Install dependencies (uv)

```bash
uv sync
source .venv/bin/activate
```

### 3) Run API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: `http://localhost:8000/docs`.

## Configuration Reference

See:

- `docs/CONFIGURATION.md`
- `docker/env/backend/env.example`
- `backend/pyproject.toml`
