# VulHunter Slim Release

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

This release branch keeps only the slim-source files required to run VulHunter. It supports exactly three entrypoints:

```bash
docker compose up --build
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

## Before You Start

1. Copy the backend environment file:

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

2. Fill in at least:
   `LLM_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`

3. Make sure Docker Compose is installed and the Docker daemon is reachable.

## Supported Commands

### 1. Default startup

```bash
docker compose up --build
```

Use this when you want the default compose stack to start and build whatever the base definition marks as buildable.

### 2. Local frontend/backend rebuild

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

Use this when you want to rebuild only the `frontend` and `backend` sources shipped in this branch while keeping database, Redis, runners, and sandbox image-based.

### 3. Full local build

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

Use this when you want the full local-build overlay for end-to-end local compose verification.

## Endpoints

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
