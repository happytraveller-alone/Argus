# Argus Slim Release

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

This release branch keeps only the slim-source files required to run Argus. Recommended startup:

```bash
./argus-bootstrap.sh --wait-exit -- default
```

## Before You Start

1. Make sure Docker Compose is installed and the Docker daemon is reachable.
2. Fill `.argus-intelligent-audit.env`, or let `./argus-bootstrap.sh` create it interactively on first run.

`argus-bootstrap.sh` calls `scripts/validate-llm-config.sh` before any Docker cleanup or startup action. If env/LLM validation fails, bootstrap exits and asks you to reconfigure.

By default, Compose publishes the frontend on host port `13000` and the backend on `18000` to avoid collisions with common local development services on `3000` / `8000`. Set `Argus_FRONTEND_PORT=3000 Argus_BACKEND_PORT=8000` when starting the stack if you need the old host ports.

The backend mounts `${DOCKER_SOCKET_PATH:-/var/run/docker.sock}` so it can launch scan runners. This workspace can override it to `/run/docker-local.sock` through the local `.env`; set `DOCKER_SOCKET_PATH` as needed in other environments.

## Repo-local Codex / OMX

- The repo-local Codex configuration lives at `.codex/config.toml`; start Codex/OMX for this project with `CODEX_HOME=$PWD/.codex` so the session does not fall back to the global `~/.codex`.
- On first use, bootstrap auth with `CODEX_HOME=$PWD/.codex codex login`, or manually copy `~/.codex/auth.json` to `.codex/auth.json` after accepting the risk.
- Project-level agent instructions are centralized in `AGENTS.md`; repo-local skills load from `.codex/skills/`. Use `neat-freak` at milestone end to reconcile project docs and agent knowledge.
- `.gitignore` ignores `.codex/`; reinstall a local skill or change version-control policy deliberately if another environment must reuse it.

## GHCR Image Naming

- GHCR image paths use `ghcr.io/<GitHub user or organization>/<image>:<tag>`.
- `audittool` is the repository name, not the GHCR owner; the default image namespace is the current repo owner `happytraveller-alone`.
- `.github/workflows/docker-publish.yml` now handles backend, frontend, OpenGrep runner, flow/parser runner, and sandbox runner image builds and publishing in one workflow.
- GitHub Actions defaults published GHCR packages to public and verifies anonymous pulls.
- Human-triggered multi-image publishing also goes through `.github/workflows/docker-publish.yml`, where you select the images to build.

## Supported Commands

### 1. Default startup

```bash
./argus-bootstrap.sh --wait-exit -- default
```

Use this to validate LLM env, build and start all services, then exit after frontend/backend readiness checks pass.

## Endpoints

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`
