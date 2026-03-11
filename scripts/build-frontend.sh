#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ARCH_RAW="${BUILD_ARCH:-$(uname -m)}"
case "$ARCH_RAW" in
  arm64|aarch64)
    BUILD_ARCH="arm64"
    ;;
  x86_64|amd64)
    BUILD_ARCH="amd64"
    ;;
  *)
    BUILD_ARCH="$ARCH_RAW"
    ;;
esac
export BUILD_ARCH

if docker buildx version >/dev/null 2>&1; then
  export DOCKER_BUILDKIT=1
  export FRONTEND_DOCKERFILE="${FRONTEND_DOCKERFILE:-Dockerfile}"
  echo "[INFO] BuildKit detected, using ${FRONTEND_DOCKERFILE}"
else
  export DOCKER_BUILDKIT=0
  export FRONTEND_DOCKERFILE="${FRONTEND_DOCKERFILE:-Dockerfile}"
  echo "[WARN] BuildKit unavailable, continuing with ${FRONTEND_DOCKERFILE}"
fi

echo "[INFO] building frontend image (arch=${BUILD_ARCH})..."
docker compose build frontend
