# VulHunter Slim Release

<p align="center">
  <a href="README.md">简体中文</a> | <strong>English</strong>
</p>

This release branch keeps only the slim-source files required to run VulHunter:

```bash
docker compose up --build
```

## Before You Start

1. Copy the backend environment file:

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

2. Fill in at least:
   `LLM_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`

3. Make sure Docker Compose is installed and the Docker daemon is reachable.

## GHCR Image Naming

- GHCR image paths use `ghcr.io/<GitHub user or organization>/<image>:<tag>`.
- `audittool` is the repository name, not the GHCR owner; the default image namespace is the current repo owner `happytraveller-alone`.
- `.github/workflows/docker-publish.yml` remains the reusable leaf builder; it defaults to the current repository owner as the GHCR namespace and still accepts `image_namespace` and `package_visibility`.
- To override the namespace, pass `image_namespace` when calling `.github/workflows/docker-publish.yml`. If it points to a different user or organization, you must also provide `GHCR_USERNAME` and `GHCR_TOKEN`.
- GitHub Actions defaults published GHCR packages to public and verifies anonymous pulls; when `package_visibility` is not `public`, the workflow skips anonymous pull validation.
- Human-triggered multi-image publishing now goes only through `.github/workflows/docker-publish-runtime-images.yml`.

## Supported Commands

### 1. Default startup

```bash
docker compose up --build
```

Use this to build and start all services locally.

## Endpoints

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
