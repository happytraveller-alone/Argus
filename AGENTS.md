# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

VulHunter (codenamed DeepAudit/AuditTool) is an AI-powered repository-level code security and compliance audit platform. It uses a Multi-Agent architecture (orchestration/recon/analysis/verification) with LLM reasoning and RAG (vector indexing) for vulnerability detection, and optional Docker sandbox PoC verification.

## Tech Stack

- **Frontend**: React 18 + TypeScript 5.7, Vite 5, Tailwind CSS 3, Radix UI, Biome (lint/format), ast-grep
- **Backend**: Python 3.11+ with FastAPI, SQLAlchemy 2 (async), Alembic migrations, LiteLLM, LangChain/LangGraph
- **Database**: PostgreSQL 15 + Redis 7 (task queue) + ChromaDB (vector store)
- **Package management**: pnpm (frontend), uv (backend)
- **Deployment**: Docker Compose

## Development Commands

### Frontend (`cd frontend`)
```bash
pnpm install          # Install dependencies
pnpm dev              # Dev server on port 5173, proxies /api to localhost:8000
pnpm build            # Production build
pnpm lint             # Lint with tsgo + biome + ast-grep
pnpm lint:fix         # Auto-fix with biome
pnpm format           # Format with biome
pnpm type-check       # TypeScript type checking (tsc --noEmit)
```

### Backend (`cd backend`)
```bash
uv sync                                    # Install dependencies
source .venv/bin/activate                  # Activate venv
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  # Dev server
alembic upgrade head                       # Run DB migrations
alembic revision --autogenerate -m "msg"   # Create new migration
```

### Backend Linting/Testing
```bash
ruff check app/                    # Lint (line-length=100)
ruff check --fix app/              # Auto-fix
black app/                         # Format (line-length=100)
pytest                             # Run all tests (testpaths=tests, asyncio_mode=auto)
pytest tests/test_specific.py      # Run single test file
pytest -k "test_name"              # Run test by name pattern
pytest -m "not integration"        # Skip integration tests
pytest --cov=app --cov-report=html # Run tests with coverage report
```

### Docker Compose (full stack)
```bash
./scripts/compose-up-with-fallback.sh   # Build & start all services (with mirror fallback)
docker compose up -d --build            # Direct start without mirror fallback
docker compose logs -f backend          # View backend logs
docker compose down                     # Stop all services
docker volume rm audittool_postgres_data  # Remove PostgreSQL data (WARNING: deletes all data)
```

**Production deployment options:**
```bash
docker compose -f docker-compose.prod.yml up -d      # Use pre-built images
docker compose -f docker-compose.prod.cn.yml up -d   # Use pre-built images (China mirrors)
```

### Environment Setup
```bash
cp backend/env.example backend/.env     # Backend config (fill LLM_API_KEY, LLM_PROVIDER, etc.)
cp frontend/.env.example frontend/.env  # Frontend config (optional)
```

## Architecture

### Three Parallel Audit Pipelines

The system runs three coexisting audit pipelines, all sharing the `Project` entity:

1. **Agent Audit (primary)** — Multi-agent with SSE streaming, agent tree, checkpoints, report export
   - API: `/api/v1/agent-tasks/*`
   - Models: `AgentTask`, `AgentEvent`, `AgentFinding`
   - Service: `backend/app/services/agent/`

2. **Traditional Audit (legacy)** — Direct LLM scanning
   - API: `/api/v1/tasks/*`, `/api/v1/scan/*`
   - Models: `AuditTask`, `AuditIssue`
   - Service: `backend/app/services/scanner.py`

3. **Static Rule Audit** — Opengrep + Gitleaks rule-based scanning
   - API: `/api/v1/static-tasks/*`
   - Models: `OpengrepScanTask`, `OpengrepFinding`, `GitleaksScanTask`, `GitleaksFinding`

### Backend Layers

```
backend/app/
├── main.py              # FastAPI app entry, lifespan management
├── api/v1/
│   ├── api.py           # Router aggregation (all routes mounted here)
│   └── endpoints/       # Route handlers by domain
├── services/
│   ├── agent/           # Multi-Agent core (agents, tools, streaming, MCP, knowledge, workflow)
│   ├── llm/             # LLM adapters, factory, cache (via LiteLLM)
│   ├── rag/             # Vector retrieval and indexing (ChromaDB)
│   ├── upload/          # File processing, language detection
│   ├── llm_rule/        # Rule-based LLM scanning
│   └── scanner.py       # Traditional audit scanning
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
├── core/                # Config, security, encryption
├── db/                  # Database session, init
└── utils/
```

**Key service responsibilities:**
- `services/agent/`: Multi-agent orchestration with LangGraph, SSE streaming, MCP tool integration
- `services/llm/`: LLM provider abstraction (supports OpenAI, Anthropic, Azure, etc. via LiteLLM)
- `services/rag/`: Code vectorization and semantic search using ChromaDB
- `services/upload/`: Repository ingestion, language detection, file parsing

### Frontend Layers

```
frontend/src/
├── app/
│   ├── App.tsx          # Root component
│   ├── main.tsx         # Entry point
│   └── routes.tsx       # Route definitions (lazy-loaded pages)
├── pages/               # Page components (AgentAudit, Dashboard, Projects, etc.)
├── features/            # Feature-specific logic (dashboard, projects, reports, tasks)
├── components/          # UI components (agent, audit, common, layout, system, ui)
├── shared/
│   ├── api/             # API client layer (axios-based, baseURL=/api/v1)
│   │   ├── serverClient.ts   # Axios instance
│   │   ├── agentTasks.ts      # Agent audit API
│   │   ├── agentStream.ts     # SSE streaming
│   │   ├── database.ts        # Legacy compat layer (projects, tasks, config)
│   │   ├── opengrep.ts        # Static scan API
│   │   └── gitleaks.ts        # Gitleaks API
│   ├── i18n/            # Internationalization (zh-CN / en-US)
│   ├── stores/          # State management
│   ├── types/           # Shared TypeScript types
│   └── hooks/           # Shared React hooks
└── hooks/               # App-level hooks
```

### Key Conventions

- **Path alias**: Frontend uses `@/` mapped to `frontend/src/`
- **API contract**: Backend schema is the source of truth; frontend consumes only via `shared/api/`
- **Severity levels in Chinese**: 严重 (Critical) / 高危 (High) / 中危 (Medium) / 低危 (Low)
- **Naming history**: Code may reference `deepaudit` / `AuditTool` — these are legacy names, the product is VulHunter
- **Backend line length**: 100 chars (both ruff and black)
- **Frontend lint**: Biome for correctness, ast-grep for custom rules (see `sgconfig.yml` + `rules/`)
- **MCP Integration**: Backend uses FastMCP for tool integration (CodeBadger for code analysis)
- **Docker socket**: Backend requires `/var/run/docker.sock` access for sandbox PoC verification

### Adding New CRUD Features

Backend: Model (`models/`) → Migration (`alembic/`) → Schema (`schemas/`) → Endpoint (`api/v1/endpoints/`) → Mount in `api/v1/api.py` → Tests (`tests/`)

Frontend: API functions in `shared/api/<domain>.ts` → Page/component → Route in `routes.tsx`

### Services & Ports

| Service    | Port  | Notes                          |
|------------|-------|--------------------------------|
| Frontend   | 3000  | Nginx (Docker) or 5173 (dev)   |
| Backend    | 8000  | FastAPI with OpenAPI at /docs   |
| PostgreSQL | 5432  | User/pass: postgres/postgres    |
| Redis      | 6379  | Agent task queue                |
| ChromaDB   | 8001  | Vector database (embedded in backend) |

## Troubleshooting

### Common Issues

**Alembic migration error: `Can't locate revision identified by 'xxx'`**

This occurs when the database volume has a different migration history than the current codebase (e.g., switching between pre-built images and local builds).

Solution:
```bash
# 1. Try rebuilding with local source first
./scripts/compose-up-with-fallback.sh

# 2. If still failing and you can discard test data:
docker compose down
docker volume rm audittool_postgres_data
./scripts/compose-up-with-fallback.sh
```

**Docker image pull failures**

The project uses automatic mirror fallback for China regions. If builds fail:
```bash
# Check which mirrors are being tested
./scripts/compose-up-with-fallback.sh

# Override with specific mirrors
DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library \
SANDBOX_IMAGE=ghcr.nju.edu.cn/lintsinghua/deepaudit-sandbox:latest \
./scripts/compose-up-with-fallback.sh
```

**Backend fails to start with MCP errors**

MCP (Model Context Protocol) sources are cached by default. To force refresh:
```bash
MCP_SOURCE_UPDATE_ON_STARTUP=true ./scripts/compose-up-with-fallback.sh
```

**Frontend dev server proxy errors**

The dev server proxies `/api` to `localhost:8000`. Ensure backend is running first:
```bash
# Terminal 1: Start backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2: Start frontend
cd frontend && pnpm dev
```
