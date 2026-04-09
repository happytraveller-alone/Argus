# Release Compose Guide

This release snapshot supports exactly two compose entrypoints.

## Default Cloud-Image Path

```bash
docker compose up
```

- `frontend`, `backend`, runner images, and sandbox use published cloud images.
- `db` and `redis` use the standard public images referenced by `docker-compose.yml`.

## Hybrid Local-Build Path

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

- Only `frontend` and `backend` are built locally.
- All runner, sandbox, and helper services continue to use cloud images.

## Backend Environment Bootstrap

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

Fill in at least:

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_MODEL`
