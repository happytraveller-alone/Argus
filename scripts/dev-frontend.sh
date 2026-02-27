#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker not found"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] docker compose plugin not found"
  exit 1
fi

echo "[INFO] starting backend dependencies..."
docker compose up -d db redis backend

echo "[INFO] starting frontend-dev (hot reload)..."
docker compose -f docker-compose.yml -f docker-compose.frontend-dev.yml up -d frontend-dev

echo "[INFO] frontend dev ready: http://localhost:5173"
echo "[INFO] backend api docs: http://localhost:8000/docs"
