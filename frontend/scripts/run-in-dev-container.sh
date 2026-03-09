#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$FRONTEND_DIR/.." && pwd)"
COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.yml" -f "$REPO_ROOT/docker-compose.frontend-dev.yml")
SERVICE="frontend-dev"

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ 未找到 docker，无法使用容器前端环境。" >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  set -- sh
fi

CONTAINER_ID="$(${COMPOSE[@]} ps -q "$SERVICE" 2>/dev/null || true)"
if [ -z "$CONTAINER_ID" ] || ! docker ps --filter "id=$CONTAINER_ID" --format '{{.ID}}' | grep -q .; then
  echo "ℹ️ frontend-dev 容器未运行，正在启动..."
  "${COMPOSE[@]}" up -d "$SERVICE"
  CONTAINER_ID="$(${COMPOSE[@]} ps -q "$SERVICE")"
fi

ESCAPED_CMD="$(printf '%q ' "$@")"
docker exec "$CONTAINER_ID" sh -lc "cd /app && ${ESCAPED_CMD}"
