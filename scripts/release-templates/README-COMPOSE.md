# Release Compose Guide

This release snapshot supports exactly two compose entrypoints.

## Default Cloud-Image Path

```bash
docker compose up
```

- `frontend`, `backend`, runner images, and sandbox use published cloud images.
- `nexus-web` and `nexus-itemDetail` still build locally from the bundled static runtime assets.
- `db` and `redis` use the standard public images referenced by `docker-compose.yml`.

## Hybrid Local-Build Path

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

- Only `frontend` and `backend` are built locally.
- `nexus-web` and `nexus-itemDetail` continue to use the base compose local-build exception.
- All runner, sandbox, and helper services continue to use cloud images.

## Nexus Runtime Assets

- `nexus-web` is served from the bundled `dist/**` files on port `5174`
- `nexus-itemDetail` is served from the bundled `dist/**` files on port `5175`
- The slim release flow does not restore legacy release artifact packaging or deploy overlays

## Backend Environment Bootstrap

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

Fill in at least:

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_MODEL`
