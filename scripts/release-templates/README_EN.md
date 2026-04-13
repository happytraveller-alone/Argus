# VulHunter User Guide

This release branch is intended for end users. You only need to configure the app and start the services.

## 1. Requirements

- Docker installed
- Docker Compose installed
- A working Docker daemon

## 2. First-Time Setup

Copy the backend environment file:

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

Open `docker/env/backend/.env` and set at least:

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`
- `SECRET_KEY`

Example:

```env
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini
SECRET_KEY=change-this-to-a-random-string
```

What these values mean:

- `LLM_PROVIDER`: the LLM provider you want to use
- `LLM_API_KEY`: your API key for that provider
- `LLM_MODEL`: the model name
- `SECRET_KEY`: replace this with your own random secret

## 3. Start the App

For normal use, run:

```bash
docker compose up --build
```

The first startup may take some time because images and dependencies need to be prepared.

To run in the background:

```bash
docker compose up -d --build
```

## 4. Access the App

After startup, open:

- Web UI: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

## 5. Common Commands

View logs:

```bash
docker compose logs -f
```

Stop the services:

```bash
docker compose down
```

Stop the services and remove volumes:

```bash
docker compose down -v
```

## 6. Other Compose Files

The repository also contains other compose override files, but most users do not need them. If your goal is simply to deploy and use the system, this is enough:

```bash
docker compose up --build
```
