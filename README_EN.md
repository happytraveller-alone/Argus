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

### 3) Build and run

```bash
docker compose up -d --build
```

### 4) Open

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (OpenAPI: http://localhost:8000/docs)

### Notes

- The backend mounts `/var/run/docker.sock` for sandbox execution. Review security boundaries before using in production.
- `docker-compose.prod.yml` currently references upstream GHCR images (`ghcr.io/lintsinghua/*`). Replace them with your own images/registry for production deployments.

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
