#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/compose-env.sh"
COMPOSE=(
  docker compose
  -f "$REPO_ROOT/docker-compose.yml"
  -f "$REPO_ROOT/docker-compose.full.yml"
)

export DOCKERHUB_LIBRARY_MIRROR="${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}"
export DOCKER_CLI_IMAGE="${DOCKER_CLI_IMAGE:-docker:cli}"
export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"

ensure_backend_docker_env_file "$REPO_ROOT"

echo "[INFO] Explicit local-build mode"
echo "[INFO] REPO_ROOT=$REPO_ROOT"
echo "[INFO] DOCKERHUB_LIBRARY_MIRROR=$DOCKERHUB_LIBRARY_MIRROR"
echo "[INFO] DOCKER_CLI_IMAGE=$DOCKER_CLI_IMAGE"
echo "[INFO] COMPOSE_BAKE=$COMPOSE_BAKE"
echo "[INFO] COMPOSE_PARALLEL_LIMIT=$COMPOSE_PARALLEL_LIMIT"

"${COMPOSE[@]}" build backend
"${COMPOSE[@]}" build frontend
"${COMPOSE[@]}" build nexus-web
"${COMPOSE[@]}" build nexus-itemDetail
"${COMPOSE[@]}" up -d

echo "[INFO] Local-build services started."
