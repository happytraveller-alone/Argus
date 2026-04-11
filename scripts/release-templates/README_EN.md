# VulHunter Release

This branch is an auto-generated latest slim-source release snapshot from `main`.
It supports exactly three startup commands:

```bash
docker compose up --build
```

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

The release compose path is now unified as `Rust backend + TypeScript frontend`, and no longer includes the legacy Python backend service.

## Before You Start

Bootstrap the backend Docker env file before the first run:

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

Set at least:

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_MODEL`

## Supported Modes

- `docker compose up --build`: start the default compose stack and build whatever the base definition marks as buildable.
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`: on top of the default path, `frontend` and `backend` also switch to local builds.
- `docker compose -f docker-compose.yml -f docker-compose.full.yml up --build`: enable the full local-build overlay for end-to-end verification.

## Runtime Notes

- The slim release flow does not restore the legacy release artifact or deploy script pipeline
- The release snapshot no longer includes Nexus static runtime assets

## Endpoints

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
