#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${DIST_DIR:-${ROOT_DIR}/dist/release}"
VERSION="${VERSION:-}"
SKIP_BUILD="false"
BUILD_SANDBOX="true"   # NEW: default build sandbox; can disable via --no-sandbox
DOCKER_BIN="${DOCKER_BIN:-docker}"
IMAGE_BACKEND="vulhunter/backend-local:latest"
IMAGE_FRONTEND="vulhunter/frontend-local:latest"
BUILD_RETRIES="${BUILD_RETRIES:-2}"
BUILD_RETRY_INTERVAL_SECONDS="${BUILD_RETRY_INTERVAL_SECONDS:-5}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Package VulHunter release artifacts for migration/deployment.

Options:
  --version <v>        Override version (default: frontend/package.json version)
  --dist <path>        Output directory (default: ./dist/release)
  --skip-build         Do not run build before packaging images/assets
  --no-sandbox         Do not build sandbox image (avoid network-heavy steps)
  -h, --help           Show this help message

Environment:
  DOCKER_BIN           Container runtime command (default: docker)
  BUILD_RETRIES        Build retry attempts for docker compose build (default: 2)
  BUILD_RETRY_INTERVAL_SECONDS
                       Interval between build retries in seconds (default: 5)

Outputs:
  checksums.txt
  vulhunter-backend-v<version>.tar.gz
  vulhunter-frontend-v<version>.tar.gz
  vulhunter-source-v<version>.tar.gz
  vulhunter-docker-v<version>.tar.gz
USAGE
}

log() {
  echo "[package-release] $*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_arg() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    echo "Option ${opt} requires a value" >&2
    usage
    exit 1
  fi
}

require_positive_int() {
  local name="$1"
  local value="${2:-}"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 )); then
    echo "${name} must be a positive integer, got: ${value}" >&2
    exit 1
  fi
}

require_container_cmd() {
  if ! command -v "$DOCKER_BIN" >/dev/null 2>&1; then
    echo "Missing required container runtime command: ${DOCKER_BIN}" >&2
    echo "Hint: install Docker (or set DOCKER_BIN to an available runtime command), then rerun." >&2
    echo "Example: DOCKER_BIN=nerdctl ./scripts/package-release-artifacts.sh --skip-build" >&2
    exit 1
  fi
}

require_image() {
  local image="$1"
  if ! "$DOCKER_BIN" image inspect "$image" >/dev/null 2>&1; then
    echo "Missing Docker image: ${image}" >&2
    echo "Hint: run without --skip-build, or build/pull the image before packaging." >&2
    exit 1
  fi
}

restore_artifact_owner() {
  if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
    log "restore artifact ownership to ${SUDO_UID}:${SUDO_GID}"
    chown -R "${SUDO_UID}:${SUDO_GID}" "$DIST_DIR"
  fi
}

pack_frontend_dist() {
  local pkg_path="$1"
  local tmp_root
  tmp_root="$(mktemp -d)"
  local cid
  cid="$($DOCKER_BIN create "$IMAGE_FRONTEND")"
  trap '$DOCKER_BIN rm -f "$cid" >/dev/null 2>&1 || true; rm -rf "$tmp_root"' RETURN
  "$DOCKER_BIN" cp "${cid}:/usr/share/nginx/html/." "$tmp_root/"
  tar -czf "$pkg_path" -C "$tmp_root" .
  "$DOCKER_BIN" rm -f "$cid" >/dev/null
  rm -rf "$tmp_root"
  trap - RETURN
}

pack_docker_layout() {
  local pkg_path="$1"
  local tmp_root
  tmp_root="$(mktemp -d)"
  mkdir -p \
    "$tmp_root/frontend"

  cp "$ROOT_DIR/.dockerignore" "$tmp_root/"
  cp "$ROOT_DIR/docker-compose.yml" "$tmp_root/"
  cp "$ROOT_DIR/docker-compose.full.yml" "$tmp_root/"
  cp -R "$ROOT_DIR/docker" "$tmp_root/"
  cp -R "$ROOT_DIR/frontend/yasa-engine-overrides" "$tmp_root/frontend/"
  rm -f "$tmp_root/docker/env/backend/.env" "$tmp_root/docker/env/frontend/.env"

  tar -czf "$pkg_path" -C "$tmp_root" .
  rm -rf "$tmp_root"
}

run_compose_build_with_retries() {
  local -a services=("$@")
  local attempt=1
  local -a compose_cmd=(
    "$DOCKER_BIN"
    compose
    -f "${ROOT_DIR}/docker-compose.yml"
    -f "${ROOT_DIR}/docker-compose.full.yml"
  )

  while true; do
    log "docker compose build attempt ${attempt}/${BUILD_RETRIES} for services: ${services[*]}"
    if "${compose_cmd[@]}" build "${services[@]}"; then
      return 0
    fi

    if (( attempt >= BUILD_RETRIES )); then
      return 1
    fi

    log "build failed, retrying in ${BUILD_RETRY_INTERVAL_SECONDS}s..."
    sleep "${BUILD_RETRY_INTERVAL_SECONDS}"
    attempt=$((attempt + 1))
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      require_arg "$1" "${2:-}"
      VERSION="$2"
      shift 2
      ;;
    --dist)
      require_arg "$1" "${2:-}"
      DIST_DIR="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD="true"
      shift
      ;;
    --no-sandbox)
      BUILD_SANDBOX="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd tar
require_cmd gzip
require_cmd sha256sum
require_container_cmd
require_cmd node
require_positive_int "BUILD_RETRIES" "$BUILD_RETRIES"
require_positive_int "BUILD_RETRY_INTERVAL_SECONDS" "$BUILD_RETRY_INTERVAL_SECONDS"

if [[ -z "$VERSION" ]]; then
  VERSION="$(node -p "require('${ROOT_DIR}/frontend/package.json').version")"
fi
VERSION="${VERSION#v}"

TAG_PREFIX="v${VERSION}"
mkdir -p "$DIST_DIR"

BACKEND_PKG="vulhunter-backend-${TAG_PREFIX}.tar.gz"
FRONTEND_PKG="vulhunter-frontend-${TAG_PREFIX}.tar.gz"
SOURCE_PKG="vulhunter-source-${TAG_PREFIX}.tar.gz"
DOCKER_PKG="vulhunter-docker-${TAG_PREFIX}.tar.gz"
CHECKSUM_FILE="checksums.txt"

log "version: ${VERSION}"
log "output: ${DIST_DIR}"

if [[ "$SKIP_BUILD" != "true" ]]; then
  if [[ "$BUILD_SANDBOX" == "true" ]]; then
    log "building runtime images with docker compose (backend, frontend, sandbox)"
    if ! run_compose_build_with_retries backend frontend sandbox; then
      echo "Docker build failed after ${BUILD_RETRIES} attempts (sandbox included)." >&2
      echo "Hint: check network/mirror availability, then rerun the packaging command." >&2
      echo "Temporary bypass (not recommended for complete release): bash scripts/package-release-artifacts.sh --no-sandbox" >&2
      exit 1
    fi
  else
    log "building runtime images with docker compose (backend, frontend) [--no-sandbox]"
    if ! run_compose_build_with_retries backend frontend; then
      echo "Docker build failed after ${BUILD_RETRIES} attempts." >&2
      echo "Hint: check network/mirror availability, then rerun the packaging command." >&2
      exit 1
    fi
  fi
else
  log "skip docker build"
fi

# Only backend/frontend images are required for packaging in this script
require_image "$IMAGE_BACKEND"
require_image "$IMAGE_FRONTEND"

log "pack backend"
tar -czf "${DIST_DIR}/${BACKEND_PKG}" -C "$ROOT_DIR" backend

log "pack frontend dist from image"
pack_frontend_dist "${DIST_DIR}/${FRONTEND_PKG}"

log "pack source"
tar \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='backend/.venv' \
  --exclude='dist' \
  -czf "${DIST_DIR}/${SOURCE_PKG}" -C "$ROOT_DIR" .

log "pack docker deployment layout"
pack_docker_layout "${DIST_DIR}/${DOCKER_PKG}"

log "write checksums"
(
  cd "$DIST_DIR"
  sha256sum \
    "$BACKEND_PKG" \
    "$DOCKER_PKG" \
    "$FRONTEND_PKG" \
    "$SOURCE_PKG" > "$CHECKSUM_FILE"
)

restore_artifact_owner

log "done"
log "artifacts:"
ls -lh "$DIST_DIR"
