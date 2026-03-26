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
cp backend/env.example backend/.env
```

At minimum, set your model-related configuration such as `LLM_API_KEY`, `LLM_PROVIDER`, and `LLM_MODEL`. Do not commit real secrets into the repository.

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

The default `docker compose up --build` path also builds and runs a set of runner preflight / warmup containers so local scanner images and commands are verified before backend starts.
Those runner preflight / warmup containers are expected to stop after the check; exiting after the check is expected, and actual scan execution still happens in temporary runner containers started on demand by backend.

For optional legacy wrapper helpers, see [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md).

### 4. Open the application

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

Related docs:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/AGENT_AUDIT.md`](docs/AGENT_AUDIT.md) ·
[`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)
