# VulHunter Backend

VulHunter backend is a FastAPI service that powers repository-scale auditing, including:

- HTTP APIs under `/api/v1/*`
- Server-Sent Events (SSE) streaming for Agent Audit events
- LLM (reasoning) + RAG (vector indexing / embeddings) configuration
- Optional Docker sandbox execution for PoC validation

## Run with Docker (recommended)

From the repository root:

```bash
docker compose up -d --build
```

Frontend is exposed at `http://localhost:3000`, backend at `http://localhost:8000`.

### Default seed projects (persistent)

On first startup (`docker compose up --build`), backend downloads the pinned GitHub archive snapshots for the demo user and stores them as persistent ZIP projects:

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
cd backend
cp env.example .env
```

Edit `.env` and set at least:

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
- `backend/env.example`
- `backend/pyproject.toml`
