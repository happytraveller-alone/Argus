# VulHunter Release

This branch is an auto-generated latest slim-source release snapshot from `main`.
It supports exactly two startup commands:

```bash
docker compose up
```

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

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

- `docker compose up`: `backend`, `frontend`, runner images, and sandbox use published cloud images; `nexus-web` and `nexus-itemDetail` still build locally from the bundled static runtime assets.
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`: on top of the default path, `frontend` and `backend` also switch to local builds; `nexus-web` and `nexus-itemDetail` keep using the base compose local-build exception.

## Nexus Runtime Assets

- The release snapshot keeps `nexus-web/dist/**`, `nexus-web/nginx.conf`, `nexus-itemDetail/dist/**`, and `nexus-itemDetail/nginx.conf`
- The slim release flow does not restore the legacy release artifact or deploy script pipeline
- `nexus-web` listens on `http://localhost:5174` by default
- `nexus-itemDetail` listens on `http://localhost:5175` by default

## Endpoints

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

See [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md) for compose details.
